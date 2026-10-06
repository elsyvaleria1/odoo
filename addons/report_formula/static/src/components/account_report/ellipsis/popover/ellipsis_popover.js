/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class AccountReportEllipsisPopover extends Component {
    static template = "report_formula.AccountReportEllipsisPopover";
    static props = {
        close: t.function(),
        name: t.string(),
        copyEllipsisText: t.function(),
    };
    props = useProps(this.constructor.props);
}
