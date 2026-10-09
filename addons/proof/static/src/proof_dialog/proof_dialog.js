// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { RPCError } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog/dialog";

export const proofMethodRegistry = registry.category("proof_methods");

export class ProofDialog extends Component {
    static template = "proof.ProofDialog";
    static components = { Dialog };
    static props = {
        close: t.function(),
        params: t.object(),
        submit: t.function(),
        onProved: t.function(),
        onFailed: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.methods = this.props.params.methods.filter((/** @type {any} */ method) =>
            proofMethodRegistry.contains(method.code),
        );
        this.state = proxy({
            code: this.methods[0]?.code,
            error: "",
            busy: false,
        });
    }

    get title() {
        return _t("Confirm it is you");
    }

    get method() {
        return this.methods.find(
            (/** @type {any} */ method) => method.code === this.state.code,
        );
    }

    get methodComponent() {
        return proofMethodRegistry.get(this.state.code).Component;
    }

    /** @param {string} code */
    selectMethod(code) {
        this.state.code = code;
        this.state.error = "";
    }

    /** @param {Object} payload */
    async prove(payload) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        let result;
        try {
            result = await this.props.submit({
                token: this.props.params.token,
                method: this.state.code,
                payload,
            });
        } catch (error) {
            this.state.busy = false;
            if (
                error instanceof RPCError &&
                error.exceptionName === "odoo.exceptions.UserError"
            ) {
                this.state.error = error.data?.message || error.message;
                return;
            }
            this.props.onFailed(error);
            this.props.close();
            return;
        }
        this.props.onProved(result);
        this.props.close();
    }
}
