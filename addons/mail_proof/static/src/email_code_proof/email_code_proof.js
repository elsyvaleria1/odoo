// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { proofMethodRegistry } from "@proof/proof_dialog/proof_dialog";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

export class EmailCodeProof extends Component {
    static template = "mail_proof.EmailCodeProof";
    static props = {
        options: t.object(),
        busy: t.boolean(),
        prove: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ code: "" });
        this.inputRef = /** @type {any} */ (elementRef());
        useAutofocus({ ref: this.inputRef });
    }

    get isComplete() {
        return this.state.code.length === this.props.options.digits;
    }

    /** @param {Event} ev */
    onInput(ev) {
        this.state.code = /** @type {HTMLInputElement} */ (ev.target).value.replace(
            /\D/g,
            "",
        );
    }

    /** @param {Event} ev */
    onSubmit(ev) {
        ev.preventDefault();
        if (this.isComplete) {
            this.props.prove({ code: this.state.code });
        }
    }
}

proofMethodRegistry.add("email_code", { Component: EmailCodeProof });
