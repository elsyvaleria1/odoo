/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { formatMonetary } from "@web/core/formatters";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";

export class ExpenseDashboard extends Component {
    static template = "hr_expense.ExpenseDashboard";
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.config = useViewConfig();
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.state = proxy({
            expenses: {},
        });

        onWillStart(async () => {
            const expense_states = await this.orm.call(
                "hr.expense",
                "get_expense_dashboard",
                [],
            );
            this.state.expenses = expense_states;
        });
    }

    renderMonetaryField(value, currency_id) {
        return formatMonetary(value, { currencyId: currency_id });
    }

    async applyFilter(filterName) {
        const { actionId } = this.config;
        const action = actionId ? await this.actionService.loadAction(actionId) : {};

        action["context"] = {
            [`search_default_${filterName}`]: 1,
            [`search_default_my_open_expenses`]: 1,
        };
        return this.actionService.doAction(action, { clearBreadcrumbs: true });
    }
}
