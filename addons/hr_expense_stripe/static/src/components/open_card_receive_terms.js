/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { Dialog } from "@web/ui/dialog";

class CardReceiveTermsViewDialog extends Component {
    static template = "hr_expense_stripe.cardReceiveTermsViewDialog";
    static components = { Dialog };

    static props = { action: t.object(), close: t.function() };
    props = useProps(this.constructor.props);
}

export function CardReceiveTermsAction(env, action) {
    env.services.dialog.add(CardReceiveTermsViewDialog, { action });
}

registry
    .category("actions")
    .add("hr_expense_stripe.expense_stripe_card_receive_terms", CardReceiveTermsAction);
