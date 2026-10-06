/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { useSearchModel } from "@web/search/search_model";
import { ListRenderer, listView } from "@web/views/list";
import { useActionLinks } from "@web/views/view_hook";

export class StockActionHelper extends Component {
    static template = "stock.StockActionHelper";
    static props = { noContentHelp: t.any() };
    props = useProps(this.constructor.props);
    setup() {
        this.appContext = useAppContext();
        this.searchModel = useSearchModel();
        const resModel =
            "searchModel" in this.appContext ? this.searchModel.resModel : undefined;
        this.handler = useActionLinks({ resModel });
    }
}

export class StockListRenderer extends ListRenderer {
    static template = "stock.StockListRenderer";
    static components = {
        ...ListRenderer.components,
        StockActionHelper,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }
}

export const StockListView = {
    ...listView,
    Renderer: StockListRenderer,
};

registry.category("views").add("stock_list_view", StockListView);
