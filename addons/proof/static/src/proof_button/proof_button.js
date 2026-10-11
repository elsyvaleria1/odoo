// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

export class ProofButton extends Component {
    static template = "proof.ProofButton";
    static props = {
        ...standardWidgetProps,
        issue: t.string(),
        submit: t.string(),
        string: t.string(),
        highlight: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.proof = useService("proof");
        this.action = useService("action");
    }

    async onClick() {
        const record = this.props.record;
        if (!(await record.save())) {
            return;
        }
        const { resModel, resId } = record;
        const params = await this.orm.call(resModel, this.props.issue, [[resId]]);
        if (!params) {
            return;
        }
        const outcome = await this.proof.request({
            params,
            submit: async (/** @type {any} */ proof) => ({
                action: await this.orm.call(resModel, this.props.submit, [
                    [resId],
                    proof,
                ]),
            }),
        });
        if (outcome?.action) {
            await this.action.doAction(outcome.action);
        }
        if (outcome) {
            await record.load();
        }
    }
}

registry.category("view_widgets").add("proof_button", {
    component: ProofButton,
    extractProps: ({ attrs }) => ({
        issue: attrs.issue,
        submit: attrs.submit,
        string: attrs.string,
        highlight: attrs.highlight === "1" || attrs.highlight === "True",
    }),
});
