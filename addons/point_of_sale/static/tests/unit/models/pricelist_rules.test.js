import { expect, test } from "@odoo/hoot";

import { definePosModels } from "../data/generate_model_definitions.js";
import { setupPosEnv } from "../utils.js";

definePosModels();

test("a rule based on another pricelist keeps the attribute extra", async () => {
    const store = await setupPosEnv();
    const template = store.models["product.template"].get(5);
    const variant = template.product_variant_ids[0];
    const pricelists = store.models["product.pricelist"];
    const items = store.models["product.pricelist.item"];
    const basePricelist = pricelists.create({ id: 980 });
    const viaBase = pricelists.create({ id: 990 });
    const viaList = pricelists.create({ id: 970 });
    const discount = { compute_price: "formula", price_discount: 10 };
    items.create({
        id: 991,
        pricelist_id: viaBase,
        base: "pricelist",
        base_pricelist_id: basePricelist,
        ...discount,
    });
    items.create({ id: 971, pricelist_id: viaList, base: "list_price", ...discount });

    const expected = (variant.lst_price + 5) * 0.9;
    expect(template.getPrice(viaList, 1, 5, false, variant)).toBe(expected);
    expect(template.getPrice(viaBase, 1, 5, false, variant)).toBe(expected);
});

test("the deepest category rule wins even when its parent has the higher id", async () => {
    const store = await setupPosEnv();
    const template = store.models["product.template"].get(5);
    const variant = template.product_variant_ids[0];
    const categories = store.models["product.category"];
    const parent = categories.create({ id: 900, name: "Parent" });
    const child = categories.create({ id: 800, name: "Child", parent_id: parent });
    template.categ_id = child;
    const pricelist = store.models["product.pricelist"].create({ id: 990 });
    const items = store.models["product.pricelist.item"];
    const fixed = (id, categ_id, fixed_price) =>
        items.create({
            id,
            pricelist_id: pricelist,
            categ_id,
            compute_price: "fixed",
            fixed_price,
        });
    fixed(991, parent, 1);
    fixed(992, child, 2);

    expect(pricelist.getGeneralRulesIdsByCategories(template.parentCategories)).toEqual(
        [992, 991],
    );
    expect(template.getPrice(pricelist, 1, 0, false, variant)).toBe(2);
});

test("a single-variant template is priced by its variant's rules", async () => {
    const store = await setupPosEnv();
    const template = store.models["product.template"].get(5);
    const variant = template.product_variant_ids[0];
    const pricelist = store.models["product.pricelist"].create({ id: 990 });
    store.models["product.pricelist.item"].create({
        id: 991,
        pricelist_id: pricelist,
        product_id: variant,
        product_tmpl_id: template,
        compute_price: "fixed",
        fixed_price: 7,
    });

    expect(template.product_variant_ids).toHaveLength(1);
    expect(template.getPrice(pricelist, 1)).toBe(7);
    expect(template.getPrice(pricelist, 1, 0, false, variant)).toBe(7);

    store.models["product.product"].create({
        id: 9901,
        product_tmpl_id: template,
        lst_price: template.list_price,
    });
    expect(template.product_variant_ids).toHaveLength(2);
    expect(template.getPrice(pricelist, 1)).toBe(template.list_price);
});
