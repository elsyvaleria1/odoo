/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class AccountReportDebugPopover extends Component {
    static template = "report_formula.AccountReportDebugPopover";
    static props = {
        close: t.function(),
        expressionsDetail: t.array(),
        onClose: t.function(),
    };
    props = useProps(this.constructor.props);
}
