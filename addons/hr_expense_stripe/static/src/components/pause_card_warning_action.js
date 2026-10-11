/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

class PauseCardWarning extends Component {
    static template = "hr_expense_stripe.pauseCardWarningDialog";
    static components = { Dialog };

    static props = { action: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.card_id = this.props.action.params.res_id;

        this.dialog = useService("dialog");
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.close = this.props.close;
    }

    async actionPauseCard() {
        await this.orm.call("hr.expense.stripe.card", "action_pause_card", [
            this.card_id,
        ]);
        this.close();
    }
}

export function PauseCardAction(env, action) {
    return new Promise((resolve) => {
        env.services.dialog.add(
            PauseCardWarning,
            {
                action,
            },
            {
                onClose: () => {
                    resolve({ type: "ir.actions.act_window_close" });
                },
            },
        );
    });
}

registry
    .category("actions")
    .add("hr_expense_stripe.pause_card_warning_action", PauseCardAction);
