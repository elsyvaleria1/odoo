/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class AccountReportCarryoverPopover extends Component {
    static template = "account.AccountReportCarryoverPopover";
    static props = {
        close: t.function(),
        carryoverData: t.object(),
        options: t.object(),
        context: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.actionService = useService("action");
        this.orm = useService("orm");
    }

    async viewCarryoverLinesAction(expressionId, columnGroupKey) {
        const viewCarryoverLinesAction = await this.orm.call(
            "report.formula.expression",
            "action_view_carryover_lines",
            [expressionId, this.props.options, columnGroupKey],
            {
                context: this.props.context,
            },
        );
        this.props.close();
        return this.actionService.doAction(viewCarryoverLinesAction);
    }
}
