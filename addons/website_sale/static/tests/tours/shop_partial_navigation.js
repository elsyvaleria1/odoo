import { registry } from "@web/core/registry";
import * as wsTourUtils from "@website_sale/js/tours/tour_utils";

registry.category("web_tour.tours").add("shop_partial_navigation", {
    url: "/shop",
    steps: () => [
        {
            content: "both products are listed",
            trigger: ".oe_product_cart a:text(PN Chair)",
            run() {
                window.shopPartialNavigationMarker = true;
            },
        },
        ...wsTourUtils.searchProduct("PN Lamp"),
        {
            content: "the search narrowed the grid in place and the URL says so",
            trigger:
                "#products_grid:not(:has(a:text(PN Chair))) .oe_product_cart a:text(PN Lamp)",
            run() {
                if (!window.shopPartialNavigationMarker) {
                    throw new Error("the shop page was reloaded");
                }
                if (!window.location.search.includes("search=PN")) {
                    throw new Error("the search URL was not pushed");
                }
            },
        },
        {
            content: "go back",
            trigger: ".o_wsale_category_title_is_search",
            run() {
                window.history.back();
            },
        },
        {
            content: "going back restores the whole shop in place",
            trigger: ".oe_product_cart a:text(PN Chair)",
            run() {
                if (!window.shopPartialNavigationMarker) {
                    throw new Error("going back reloaded the shop page");
                }
            },
        },
    ],
});
