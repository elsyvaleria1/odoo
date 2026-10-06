/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { useSearchModel } from "@web/search/search_model";

patch(ControlPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.searchModel = useSearchModel();
    },

    switchView() {
        const searchModel = this.searchModel;
        const filterNamesToDisable = ["kanban_date_filter", "kanban_hour_filter"];
        const filtersToDisable = Object.values(searchModel.searchItems).filter(
            (sm) =>
                filterNamesToDisable.includes(sm.name) &&
                searchModel.query.some((q) => q.searchItemId === sm.id),
        );
        for (const filter of filtersToDisable) {
            searchModel.toggleSearchItem(filter.id);
        }
        super.switchView(...arguments);
    },
});
