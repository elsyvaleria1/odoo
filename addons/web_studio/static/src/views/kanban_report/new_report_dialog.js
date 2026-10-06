/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { Dialog } from "@web/ui/dialog";

export class NewReportDialog extends Component {
    static template = "web_studio.NewReportDialog";
    static components = { Dialog };
    static props = { resModel: t.any(), onReportCreated: t.any(), close: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.layouts = [
            {
                name: "web.external_layout",
                label: _t("External"),
                description: _t("Business header/footer"),
            },
            {
                name: "web.internal_layout",
                label: _t("Internal"),
                description: _t("Minimal header/footer"),
            },
            {
                name: "web.basic_layout",
                label: _t("Blank"),
                description: _t("No header/footer"),
            },
        ];
    }

    async createNewReport(layout) {
        const report = await rpc("/web_studio/create_new_report", {
            model_name: this.props.resModel,
            layout,
            context: user.context,
        });
        this.props.onReportCreated(report);
        this.props.close();
    }
}
