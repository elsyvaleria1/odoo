/** @odoo-module native */
import { onMounted, onWillUnmount, proxy, t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { NavBar } from "@web/webclient/navbar/navbar";

import { SpreadsheetName } from "../../actions/control_panel/spreadsheet_name.js";

export class SpreadsheetNavbar extends NavBar {
    static template = "spreadsheet_edition.SpreadsheetNavbar";
    static components = { ...NavBar.components, SpreadsheetName };
    static props = {
        spreadsheetName: t.string(),
        isReadonly: t.boolean().optional(),
        onSpreadsheetNameChanged: t.function().optional(),
        slots: t.object().optional(),
        model: t.object().optional(),
    };
    render = useRender();

    setup() {
        super.setup();
        this.config = useViewConfig();
        this.ui = useService("ui");
        this.actionService = useService("action");
        this.breadcrumbs = proxy(this.config.breadcrumbs);

        if (this.props.model) {
            onMounted(() => {
                this.props.model.on("update", this, () => this.render(true));
            });
            onWillUnmount(() => {
                this.props.model.off("update", this);
            });
        }
    }

    get breadcrumbTitle() {
        if (this.breadcrumbs.length > 1) {
            return this.breadcrumbs.at(-2).name;
        }
        return "";
    }

    onBreadcrumbClicked() {
        if (this.breadcrumbs.length > 1) {
            this.actionService.restore(this.breadcrumbs.at(-2).id);
        }
    }

    get isSynced() {
        return this.props.model && this.props.model.getters.isFullySynchronized();
    }
}
