import { expect, test } from "@odoo/hoot";
import { freezeTime, mockDate } from "@odoo/hoot-mock";
import { dateTime } from "@web/core/l10n/dates";

import { definePosModels } from "../data/generate_model_definitions.js";
import { setupPosEnv } from "../utils.js";

definePosModels();

for (const scope of ["global", "template", "variant", "category"]) {
    test(`scheduled ${scope} prices activate and expire without a reload`, async () => {
        const store = await setupPosEnv();
        const template = store.models["product.template"].get(5);
        template.categ_id = store.models["product.category"].get(4);
        const variant = template.product_variant_ids[0];
        const pricelist = store.models["product.pricelist"].create({ id: 990 });
        const start = dateTime({ year: 2026, month: 3, day: 8, hour: 7 }, "UTC");
        const end = start.add({ hours: 1 });
        store.models["product.pricelist.item"].create({
            id: 991,
            pricelist_id: pricelist,
            product_tmpl_id: scope === "template" ? template : false,
            product_id: scope === "variant" ? variant : false,
            categ_id: scope === "category" ? template.categ_id : false,
            date_start: start,
            date_end: end,
            compute_price: "fixed",
            fixed_price: 7,
        });
        const setNow = (value) => mockDate(value.toPlainDateTime().toString(), 0);
        freezeTime();
        setNow(start.subtract({ seconds: 1 }));
        const price = () => template.getPrice(pricelist, 1, 0, false, variant);
        const base = variant.lst_price;
        expect(price()).toBe(base);
        setNow(start);
        expect(price()).toBe(7);
        setNow(end);
        expect(price()).toBe(7);
        setNow(end.add({ seconds: 1 }));
        expect(price()).toBe(base);
    });
}

test("general rules follow additions, category changes and deletion", async () => {
    const store = await setupPosEnv();
    const template = store.models["product.template"].get(5);
    template.categ_id = store.models["product.category"].get(4);
    const pricelist = store.models["product.pricelist"].create({ id: 990 });
    expect(pricelist.getGeneralRulesIdsByCategories([])).toEqual([]);
    const rule = store.models["product.pricelist.item"].create({
        id: 991,
        pricelist_id: pricelist,
        compute_price: "fixed",
        fixed_price: 7,
    });
    expect(pricelist.getGeneralRulesIdsByCategories([])).toEqual([991]);
    rule.categ_id = template.categ_id;
    expect(pricelist.getGeneralRulesIdsByCategories([])).toEqual([]);
    expect(pricelist.getGeneralRulesIdsByCategories([template.categ_id.id])).toEqual([
        991,
    ]);
    rule.delete();
    expect(pricelist.getGeneralRulesIdsByCategories([template.categ_id.id])).toEqual(
        [],
    );
});

test("incremental general rules retain server pricing precedence", async () => {
    const store = await setupPosEnv();
    const pricelist = store.models["product.pricelist"].create({ id: 990 });
    const category = store.models["product.category"].get(4);
    const items = store.models["product.pricelist.item"];
    const createRule = (id, min_quantity, categ_id = false) =>
        items.create({
            id,
            min_quantity,
            categ_id,
            pricelist_id: pricelist,
            compute_price: "fixed",
            fixed_price: id,
        });
    createRule(991, 1);
    createRule(992, 10);
    createRule(993, 1, category);
    createRule(994, 10);
    expect(pricelist.getGeneralRulesIdsByCategories([category.id])).toEqual([
        993, 994, 992, 991,
    ]);
    expect(pricelist.getGeneralRulesIdsByCategories([])).toEqual([994, 992, 991]);
});
