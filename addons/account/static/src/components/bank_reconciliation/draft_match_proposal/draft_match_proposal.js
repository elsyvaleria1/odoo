/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";

export class BankRecDraftMatchProposal extends Component {
    static template = "account.BankRecDraftMatchProposal";
    static props = {
        label: t.string(),
        onConfirm: t.function(),
        onDismiss: t.function(),
    };
    props = useProps(this.constructor.props);
}
