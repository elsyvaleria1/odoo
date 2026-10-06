/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export const projectProfitabilityProps = {
    data: t.object(),
    labels: t.object(),
    formatMonetary: t.function(),
    onProjectActionClick: t.function(),
    onClick: t.function(),
};

export class ProjectProfitability extends Component {
    static props = projectProfitabilityProps;
    static template = "project.ProjectProfitability";
    props = useProps(this.constructor.props);

    get revenues() {
        return this.props.data.revenues;
    }

    get costs() {
        return this.props.data.costs;
    }

    get margin() {
        const invoiced_billed = this.revenues.total.invoiced + this.costs.total.billed;
        const to_invoice_to_bill =
            this.revenues.total.to_invoice + this.costs.total.to_bill;
        return {
            invoiced_billed,
            to_invoice_to_bill,
            total: invoiced_billed + to_invoice_to_bill,
        };
    }
}
