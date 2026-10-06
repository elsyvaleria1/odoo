/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/ui/dialog";

class IssuingTermsViewDialog extends Component {
    static template = "hr_expense_stripe.issuingTermsViewDialog";
    static components = { Dialog };

    static props = { action: t.object(), close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.close = this.props.close;
    }
}

export function IssuingTermsAction(env, action) {
    return new Promise((resolve) => {
        env.services.dialog.add(
            IssuingTermsViewDialog,
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
    .add("hr_expense_stripe.expense_stripe_issuing_terms", IssuingTermsAction);
