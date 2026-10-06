/** @odoo-module native */
import { aiSearchSpec } from "@ai/core/web/search_model_patch";
import { useBus, useEventBus } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@web/search/search_bar/search_bar";

function isDefined(value) {
    return value !== undefined && value !== null;
}

patch(SearchBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.bus = useEventBus();
        useBus(this.bus, "APPLY_AI_ADJUST_SEARCH", async ({ detail }) => {
            const searchModel = this.searchModel;
            for (const facetGroupId of detail.removeFacets) {
                searchModel.deactivateGroup(facetGroupId);
            }
            const {
                toggleFilters,
                toggleGroupBys,
                applySearches,
                customDomain,
                measures,
                mode,
                order,
                stacked,
                cumulated,
            } = detail;
            await searchModel.applySearchSpec(
                aiSearchSpec({
                    filters: toggleFilters,
                    groupBys: toggleGroupBys,
                    fieldSearches: applySearches,
                    customDomain,
                }),
            );
            if (
                (measures && measures.length) ||
                [mode, order, stacked, cumulated].some(isDefined)
            ) {
                this.bus.trigger("APPLY_AI_ADJUST_MODEL", {
                    measures: measures ?? [],
                    mode,
                    order,
                    stacked,
                    cumulated,
                });
            }
            const chatboxInput = document.querySelector(".o-mail-Composer-input");
            if (chatboxInput) {
                chatboxInput.focus();
            }
        });
    },
});
