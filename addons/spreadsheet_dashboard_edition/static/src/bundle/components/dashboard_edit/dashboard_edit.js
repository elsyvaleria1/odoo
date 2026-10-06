/** @odoo-module native */
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { dashboardActionRegistry } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_action";
import { useDebugMode } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

export class DashboardEdit extends Component {
    static template = "spreadsheet_dashboard_edition.DashboardEdit";
    static props = { onClick: t.function(), dashboardId: t.number(), data: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        this.debug = useDebugMode();
        this.isDashboardAdmin = false;
        onWillStart(async () => {
            if (this.debug) {
                this.isDashboardAdmin = await user.hasGroup(
                    "spreadsheet_dashboard.group_dashboard_manager",
                );
            }
        });
    }
    onClick() {
        return this.props.onClick(this.props.dashboardId);
    }

    get tooltip() {
        return this.props.data.is_from_data
            ? _t(
                  "Editing standard dashboards is not recommended. Changes will be lost on Odoo upgrades.",
              )
            : _t("Edit");
    }
}

dashboardActionRegistry.add("dashboard_edit", DashboardEdit);
