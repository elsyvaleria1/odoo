/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";
import { requestNavigation } from "@web/public/partial_navigation";

export class PriceRange extends Interaction {
    static selector = "#o_wsale_price_range_option";
    dynamicContent = {
        'input[type="range"]': { "t-on-newRangeValue": this.onPriceRangeSelected },
    };

    /**
     * @param {Event} ev
     */
    onPriceRangeSelected(ev) {
        const range = ev.currentTarget;
        const url = new URL(range.dataset.url, window.location.origin);
        const searchParams = url.searchParams;
        if (parseFloat(range.min) !== range.valueLow) {
            searchParams.set("min_price", range.valueLow);
        }
        if (parseFloat(range.max) !== range.valueHigh) {
            searchParams.set("max_price", range.valueHigh);
        }
        const product_list_div = document.querySelector(
            ".o_wsale_products_grid_table_wrapper",
        );
        if (product_list_div) {
            product_list_div.classList.add("opacity-50");
        }
        requestNavigation(range, `${url.pathname}?${searchParams.toString()}`);
    }
}

registry.category("public.interactions").add("website_sale.price_range", PriceRange);
