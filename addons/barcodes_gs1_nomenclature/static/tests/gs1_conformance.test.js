/** @odoo-module native */

import { BarcodeParser } from "@barcodes/js/barcode_parser";
import { GS1_VECTORS as vectors } from "@barcodes_gs1_nomenclature/../tests/gs1_conformance_vectors";
import { GS1BarcodeError } from "@barcodes_gs1_nomenclature/js/barcode_parser";
import { expect, test } from "@odoo/hoot";

function isoDay(date) {
    const pad = (number) => String(number).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function decompose(testCase) {
    const parser = new BarcodeParser({
        nomenclature: {
            is_gs1_nomenclature: true,
            gs1_separator_fnc1: testCase.separator ?? "",
            upc_ean_conv: "none",
            rules: vectors.rule_sets[testCase.rules].map((rule) => ({
                encoding: "gs1-128",
                gs1_decimal_usage: false,
                ...rule,
            })),
        },
    });
    try {
        return parser.parseBarcode(testCase.barcode).map((part) => ({
            type: part.type,
            ai: part.ai,
            value: part.value instanceof Date ? isoDay(part.value) : part.value,
        }));
    } catch (error) {
        if (error instanceof GS1BarcodeError) {
            return null;
        }
        throw error;
    }
}

test.tags("headless");
test("conformance: GS1 vectors", async () => {
    for (const testCase of vectors.cases) {
        expect(decompose(testCase)).toEqual(testCase.expected, {
            message: `${testCase._why}: ${JSON.stringify(testCase.barcode)}`,
        });
    }
});
