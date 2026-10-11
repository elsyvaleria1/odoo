/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form";

const PROVEN_BUTTONS = {
    "approval.request": { action_approve: ["approve", "action_approve_with_proof"] },
    "wizard.approval.request.decide": {
        action_confirm_refuse: ["refuse", "action_confirm_refuse_with_proof"],
    },
};

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.approvalProof = {
            action: useService("action"),
            orm: useService("orm"),
            proof: useService("proof"),
        };
    },

    async beforeExecuteActionButton(clickParams) {
        const proven =
            clickParams.type === "object" && this.getProvenButton(clickParams.name);
        if (proven) {
            const [decision, method] = proven;
            const record = this.model.root;
            const requestId =
                this.props.resModel === "approval.request"
                    ? record.resId
                    : record.data.request_id?.id;
            const { orm, proof, action } = this.approvalProof;
            const params =
                requestId &&
                (await orm.call("approval.request", "action_issue_decision_proof", [
                    [requestId],
                    decision,
                ]));
            if (params) {
                if (!(await record.save())) {
                    return false;
                }
                const outcome = await proof.request({
                    params,
                    submit: async (/** @type {any} */ approvalProof) => ({
                        action: await orm.call(this.props.resModel, method, [
                            [record.resId],
                            approvalProof,
                        ]),
                    }),
                });
                if (outcome?.action) {
                    await action.doAction(outcome.action);
                }
                if (outcome && this.props.resModel === "approval.request") {
                    await record.load();
                }
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    },

    /** @param {string | undefined} name */
    getProvenButton(name) {
        const proven = PROVEN_BUTTONS[this.props.resModel]?.[name || ""];
        if (
            proven &&
            this.props.resModel === "wizard.approval.request.decide" &&
            this.model.root.data.request_ids?.records?.length
        ) {
            return null;
        }
        return proven;
    },
});
