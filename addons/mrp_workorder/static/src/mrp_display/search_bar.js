/** @odoo-module native */
import { onWillDestroy } from "@odoo/owl";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { SearchBar } from "@web/search/search_bar/search_bar";

export class MrpDisplaySearchBar extends SearchBar {
    setup() {
        super.setup();
        let timeoutId;
        useLayoutEffect(
            (isOpen) => {
                clearTimeout(timeoutId);
                if (!isOpen) {
                    timeoutId = setTimeout(() => this.inputRef.el?.blur(), 100);
                }
            },
            () => [this.inputDropdownState.isOpen],
        );
        onWillDestroy(() => clearTimeout(timeoutId));
    }

    removeFacet(facet) {
        if (facet.color === "info") {
            this.searchModel.state.workorderFilters.forEach((f) => {
                f.isActive = false;
            });
            return;
        } else if (facet.type === "favorite" && this.searchModel.workorders) {
            for (const filter of this.searchModel.state.workorderFilters) {
                filter.isActive = false;
            }
        }
        return super.removeFacet(facet);
    }
}
MrpDisplaySearchBar.template = "mrp_workorder.MrpDisplaySearchBar";
