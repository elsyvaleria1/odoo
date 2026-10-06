/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

export class ApprovalButtonPopover extends Component {
    static template = "approval.ApprovalButtonPopover";
    static props = { gate: t.object(), close: t.function().optional() };
    props = useProps(this.constructor.props);

    get result() {
        return this.props.gate.result;
    }

    get isRefused() {
        return this.result.request?.state === "refused";
    }

    get canAct() {
        return !this.props.gate.syncing && this.props.gate.hasRecord();
    }

    approvedCount(step) {
        return step.decisions.filter((decision) => decision.state === "approved")
            .length;
    }

    formatDate(date) {
        return formatDateTime(deserializeDateTime(date));
    }

    decide(approve, stepId) {
        return this.props.gate.decide(approve, stepId);
    }

    withdraw(approverId, stepId) {
        return this.props.gate.withdraw(approverId, stepId);
    }
}
