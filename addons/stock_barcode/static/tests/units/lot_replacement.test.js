import { describe, expect, test } from "@odoo/hoot";
import BarcodeModel from "@stock_barcode/models/barcode_model";

describe.current.tags("headless");

const line = { product_id: { display_name: "Apples" }, trace_id: { name: "OLD" } };

function makeModel(overrides = {}) {
    const shown = [];
    const model = Object.assign(Object.create(BarcodeModel.prototype), {
        cache: { getRecord: (model, id) => ({ id, name: `LOT-${id}` }) },
        notification: (message, options) => shown.push([message, options.type]),
        ...overrides,
    });
    return { model, shown };
}

test("a scan that keeps the lot is no replacement", () => {
    const { model } = makeModel();
    expect(model._lotReplacement(line, { lot_name: "OLD" })).toBe(null);
    expect(model._lotReplacement(line, { qty_done: 1 })).toBe(null);
    expect(
        model._lotReplacement({ ...line, trace_id: false }, { lot_name: "NEW" }),
    ).toBe(null, { message: "a first lot on the line replaces nothing" });
});

test("the replacing lot is read from a name, an id or a record", () => {
    const { model } = makeModel();
    expect(model._lotReplacement(line, { lot_name: "NEW" })?.to).toBe("NEW");
    expect(model._lotReplacement(line, { trace_id: 7 })?.to).toBe("LOT-7");
    expect(model._lotReplacement(line, { trace_id: { name: "REC" } })?.to).toBe("REC");
});

test("a replacement nobody announces stays silent", () => {
    const { model, shown } = makeModel();
    model._notifyLotReplaced({ ...model._lotReplacement(line, { lot_name: "NEW" }) });
    expect(shown).toEqual([]);
});

test("every contribution to a replacement ends up in one notification", () => {
    const { model, shown } = makeModel({
        _onLotReplaced(lotReplacement) {
            lotReplacement.announce = true;
            lotReplacement.instructions.push("Scan it again.");
            lotReplacement.type = "warning";
        },
    });
    model._notifyLotReplaced(model._lotReplacement(line, { lot_name: "NEW" }));
    expect(shown).toEqual([
        ["Apples: lot OLD replaced by NEW. Scan it again.", "warning"],
    ]);
});
