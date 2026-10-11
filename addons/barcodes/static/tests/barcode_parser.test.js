/** @odoo-module native */

import { BarcodeParser } from "@barcodes/js/barcode_parser";
import { expect, test } from "@odoo/hoot";
import { Deferred } from "@odoo/hoot-mock";
import {
    defineModels,
    fields,
    getService,
    makeMockEnv,
    models,
    onRpc,
} from "@web/../tests/web_test_helpers";

class BarcodeNomenclature extends models.Model {
    _name = "barcode.nomenclature";
    name = fields.Char();
    upc_ean_conv = fields.Char();
    rule_ids = fields.One2many({
        relation: "barcode.rule",
        relation_field: "barcode_nomenclature_id",
    });
    _records = [{ id: 1, name: "Nomenclature", upc_ean_conv: "none" }];
}

class BarcodeRule extends models.Model {
    _name = "barcode.rule";
    _order = "sequence, id";
    name = fields.Char();
    sequence = fields.Integer();
    type = fields.Char();
    encoding = fields.Char();
    pattern = fields.Char();
    alias = fields.Char();
    barcode_nomenclature_id = fields.Many2one({ relation: "barcode.nomenclature" });
    _records = [
        { id: 1, name: "second", sequence: 20, barcode_nomenclature_id: 1 },
        { id: 2, name: "first", sequence: 10, barcode_nomenclature_id: 1 },
    ];
}

defineModels([BarcodeNomenclature, BarcodeRule]);

test.tags("headless");
test("fetchNomenclature reads the rules in match order, beside the nomenclature", async () => {
    const nomenclatureRead = new Deferred();
    onRpc("barcode.nomenclature", "read", async () => {
        expect.step("nomenclature requested");
        await nomenclatureRead;
    });
    onRpc("barcode.rule", "search_read", () => {
        expect.step("rules requested");
        nomenclatureRead.resolve();
    });
    await makeMockEnv();

    const nomenclature = await BarcodeParser.fetchNomenclature(getService("orm"), 1);

    expect.verifySteps(["nomenclature requested", "rules requested"]);
    expect(nomenclature.name).toBe("Nomenclature");
    expect(nomenclature.rules.map((rule) => rule.name)).toEqual(["first", "second"]);
});

test.tags("headless");
test("Test check digit", async () => {
    const nomenclature = {
        id: 1,
        name: "normal",
        upc_ean_conv: "always",
        rules: [
            {
                id: 1,
                name: "Product Barcodes",
                barcode_nomenclature_id: 1,
                sequence: 90,
                type: "product",
                encoding: "any",
                pattern: ".*",
            },
        ],
    };
    const barcodeNomenclature = new BarcodeParser({ nomenclature });

    let ean8 = "87111125";
    expect(barcodeNomenclature.getBarcodeCheckDigit(ean8)).toEqual(
        +ean8[ean8.length - 1],
    );
    ean8 = "4725992";
    expect(barcodeNomenclature.getBarcodeCheckDigit(ean8 + "0")).toEqual(8);
    let ean13 = "1234567891231";
    expect(barcodeNomenclature.getBarcodeCheckDigit(ean13)).toEqual(
        +ean13[ean13.length - 1],
    );
    ean13 = "962434754318";
    expect(barcodeNomenclature.getBarcodeCheckDigit(ean13 + "0")).toEqual(4);
    let utca = "692771981161";
    expect(barcodeNomenclature.getBarcodeCheckDigit(utca)).toEqual(
        +utca[utca.length - 1],
    );
    utca = "71679131569";
    expect(barcodeNomenclature.getBarcodeCheckDigit(utca + "0")).toEqual(7);
});
