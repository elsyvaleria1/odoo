import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class VehicleCatalog extends Interaction {
    static selector = ".m-vehicles-catalog";
    dynamicContent = {
        ".m-vehicle-filter": {
            "t-on-click": this.onFilterClick,
            "t-att-class": (el) => ({
                "m-vehicle-filter--active": el.dataset.mFilter === this.filter,
            }),
        },
        ".m-vehicle-card": {
            "t-att-style": (el) => ({
                display: this.isShown(el) ? "" : "none",
            }),
        },
    };

    setup() {
        this.filter = "all";
    }

    /**
     * @param {MouseEvent} ev
     */
    onFilterClick(ev) {
        this.filter = ev.currentTarget.dataset.mFilter;
    }

    /**
     * @param {HTMLElement} card
     * @returns {boolean}
     */
    isShown(card) {
        const tags = (card.dataset.mTags || "").split(" ");
        return this.filter === "all" || tags.includes(this.filter);
    }
}

registry
    .category("public.interactions")
    .add("asset_ledger_website_sale.vehicle_catalog", VehicleCatalog);
