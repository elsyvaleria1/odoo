/** @odoo-module native */
import { Approval } from "@approval/web/approval";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(Approval.prototype, {
    setup() {
        super.setup();
        this.proof = useService("proof");
    },

    async onClickApprove() {
        const approver = this.props.activity.approver_id.id;
        const params = await this.orm.call(
            "approval.approver",
            "action_issue_decision_proof",
            [[approver], "approve"],
        );
        if (!params) {
            return super.onClickApprove();
        }
        const proven = await this.proof.request({
            params,
            submit: async (/** @type {any} */ proof) => {
                await this.orm.call("approval.approver", "action_approve_with_proof", [
                    [approver],
                    proof,
                ]);
                return true;
            },
        });
        if (proven) {
            this.props.activity.remove();
        }
        this.props.onChange();
    },
});
