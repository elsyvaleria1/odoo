/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class PayslipActionHelper extends Component {
    static template = "hr_payroll.PayslipActionHelper";
    static props = {
        payrunId: t.number().optional(),
        onClickCreate: t.function(),
        onClickGenerate: t.function(),
    };
    props = useProps(this.constructor.props);
}
