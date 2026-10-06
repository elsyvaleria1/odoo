/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { registries } from "@spreadsheet/o_spreadsheet/o_spreadsheet";
import { CheckBox } from "@web/components/checkbox";

const { topbarComponentRegistry } = registries;

export class DashboardPublish extends Component {
    static template = "spreadsheet_edition.DashboardPublish";
    static components = { CheckBox };
    static props = {};
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        this.state = proxy({ isPublished: this.env.isDashboardPublished() });
    }

    get isReadonly() {
        return this.env.isRecordReadonly();
    }

    toggleDashboardPublished(checked) {
        if (this.isReadonly || this.state.isPublished === checked) {
            return;
        }
        this.state.isPublished = checked;
        this.env.toggleDashboardPublished(checked);
    }
}

topbarComponentRegistry.add("dashboard_publish", {
    component: DashboardPublish,
    isVisible: (env) => env.isDashboardPublished,
    sequence: 15,
});
