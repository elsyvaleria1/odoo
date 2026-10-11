/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";

import { Base } from "./related_models/index.js";
const log = makeLogger("pos.pricelist");

function categoryDepth(category) {
    let depth = 0;
    for (let parent = category?.parent_id; parent; parent = parent.parent_id) {
        depth++;
    }
    return depth;
}

export class ProductPricelist extends Base {
    static pythonModel = "product.pricelist";

    getGeneralRulesIdsByCategories(categoryIds) {
        const categories = new Set(categoryIds);
        const rules = this.item_ids.filter(
            (item) =>
                !item.product_id &&
                !item.product_tmpl_id &&
                (!item.categ_id || categories.has(item.categ_id.id)),
        );
        log.logic("getGeneralRulesIdsByCategories", () => ({
            pricelist: this.id,
            items: this.item_ids.length,
            applicable: rules.length,
        }));
        const depths = new Map(
            rules.map((rule) => [rule, categoryDepth(rule.categ_id)]),
        );
        return rules
            .toSorted(
                (a, b) =>
                    Number(Boolean(b.categ_id)) - Number(Boolean(a.categ_id)) ||
                    (b.min_quantity || 0) - (a.min_quantity || 0) ||
                    depths.get(b) - depths.get(a) ||
                    b.id - a.id,
            )
            .map((rule) => rule.id);
    }
}

registry
    .category("pos_available_models")
    .add(ProductPricelist.pythonModel, ProductPricelist);
