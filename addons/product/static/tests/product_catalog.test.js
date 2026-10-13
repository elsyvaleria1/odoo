import { expect, test } from "@odoo/hoot";
import { ProductCatalogKanbanModel } from "@product/product_catalog/kanban_model";
import { ProductCatalogKanbanRecord } from "@product/product_catalog/kanban_record";
import { ProductCatalogOrderLine } from "@product/product_catalog/order_line/order_line";
import { ProductCatalogSearchPanel } from "@product/product_catalog/search/search_panel";

const sampleInfoFor = (ids) =>
    ProductCatalogKanbanModel.prototype._getSampleOrderLineInfo.call({}, ids);

test("sample order line info answers for every id it is given", () => {
    const ids = [1, 2, 7, 11, 16, 23, 40];
    const info = sampleInfoFor(ids);
    expect(ids.filter((id) => !info[id]).join(",")).toBe("");
});

test("sample order line info only emits props the order line declares", () => {
    const declared = new Set(Object.keys(ProductCatalogOrderLine.props));
    const undeclared = Object.keys(sampleInfoFor([1])[1]).filter(
        (key) => !declared.has(key),
    );
    expect(undeclared.join(",")).toBe("");
});

test("sample order line info is reproducible", () => {
    expect(sampleInfoFor([1, 2, 3])).toEqual(sampleInfoFor([1, 2, 3]));
});

test("grouped records are collected from every opened subgroup", () => {
    const collect = ProductCatalogKanbanModel.prototype._collectGroupedRecords;
    const groups = [
        { records: [{ id: 1 }] },
        { groups: [{ records: [{ id: 2 }, { id: 3 }] }, { records: [{ id: 4 }] }] },
    ];
    expect(
        collect
            .call({}, groups)
            .map((r) => r.id)
            .sort((a, b) => a - b),
    ).toEqual([1, 2, 3, 4]);
});

/** @param {Record<string, any>} self */
function dropOn(self, target, moved) {
    ProductCatalogSearchPanel.prototype.onDrop.call(self, target, {
        preventDefault() {},
        dataTransfer: { getData: () => moved },
    });
}

test("a section dropped onto or from No Section moves nothing", () => {
    const moves = [];
    const panel = { reorderSections: (...args) => moves.push(args) };
    dropOn(panel, false, "4");
    dropOn(panel, 4, "false");
    dropOn(panel, 4, "4");
    expect(moves).toEqual([]);
    dropOn(panel, 4, "7");
    expect(moves).toEqual([[7, 4]]);
});

test("an emptied catalog quantity is a quantity of zero", () => {
    const updates = [];
    const record = { updateQuantity: (quantity) => updates.push(quantity) };
    for (const value of ["", "5"]) {
        ProductCatalogKanbanRecord.prototype.setQuantity.call(record, {
            target: { value },
        });
    }
    expect(updates).toEqual([0, 5]);
});
