import { expect, test } from "@odoo/hoot";
import { definePosPrepDisplayModels } from "@pos_enterprise/../tests/unit/data/generate_model_definitions";
import {
    createPrepDisplayTicket,
    setupPosPrepDisplayEnv,
} from "@pos_enterprise/../tests/unit/utils";
import { Category } from "@pos_enterprise/app/components/category/category";
import { computeFontColor } from "@pos_enterprise/app/utils/utils";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";

definePosPrepDisplayModels();

test("category text contrast accepts both stored and shorthand hex colors", () => {
    expect(computeFontColor(false)).toBe("black");
    expect(computeFontColor("#ffffff")).toBe("black");
    expect(computeFontColor("#fff")).toBe("black");
    expect(computeFontColor("#000")).toBe("white");
    expect(computeFontColor("#ff0000")).toBe("white");
    expect(computeFontColor("#00ff00")).toBe("black");
});

test("shouldShowCategory", async () => {
    const store = await setupPosPrepDisplayEnv();
    await createPrepDisplayTicket(store);
    const category = store.data.models["pos.category"].getAll()[0];
    const comp = await mountWithCleanup(Category, { props: { category: category } });
    const result = comp.shouldShowCategory;
    expect(result).toBe(1);
    expect(comp.products.length).toBe(1);
});

test("preparation_display_service.toggleCategory", async () => {
    const store = await setupPosPrepDisplayEnv();
    await createPrepDisplayTicket(store);
    const category = store.data.models["pos.category"].getAll()[0];
    await mountWithCleanup(Category, { props: { category: category } });
    store.toggleCategory(category);
    expect(store.selectedCategoryIds.has(category.id)).toBe(true);
    expect(store.selectedProductIds.size).toBe(0);
    store.toggleCategory(category);
    expect(store.selectedCategoryIds.has(category.id)).toBe(false);
});

test("preparation_display_service.toggleProduct", async () => {
    const store = await setupPosPrepDisplayEnv();
    await createPrepDisplayTicket(store);
    const category = store.data.models["pos.category"].getAll()[0];
    const comp = await mountWithCleanup(Category, { props: { category: category } });
    const product = comp.products[0];
    store.toggleProduct(product);
    expect(store.selectedProductIds.has(product.id)).toBe(true);
    expect(store.selectedCategoryIds.size).toBe(0);
    store.toggleProduct(product);
    expect(store.selectedProductIds.has(product.id)).toBe(false);
});
