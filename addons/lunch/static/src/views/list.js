/** @odoo-module native */
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { useSearchModel } from "@web/search/search_model";
import { ListController, ListRenderer, listView } from "@web/views/list";

import { LunchDashboard } from "../components/lunch_dashboard.js";
import { LunchRendererMixin } from "../mixins/lunch_renderer_mixin.js";
import { LunchSearchModel } from "./search_model.js";
import { LunchSearchPanel } from "./search_panel.js";

export class LunchListRenderer extends LunchRendererMixin(ListRenderer) {
    static template = "lunch.ListRenderer";
    static components = {
        ...LunchListRenderer.components,
        LunchDashboard,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.searchModel = useSearchModel();
        const { locationId } = this.searchModel.lunchState;
        if (!locationId) {
            this.props.list.records = [];
        }
    }

    onCellClicked(record) {
        this.openOrderLine(record.resId);
    }
}

class LunchListController extends ListController {
    get modelOptions() {
        return {
            ...super.modelOptions,
            lazy: false,
        };
    }
}

registry.category("views").add("lunch_list", {
    ...listView,
    Controller: LunchListController,
    Renderer: LunchListRenderer,
    SearchModel: LunchSearchModel,
    SearchPanel: LunchSearchPanel,
});
