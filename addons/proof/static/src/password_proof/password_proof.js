// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

import { proofMethodRegistry } from "../proof_dialog/proof_dialog.js";

export class PasswordProof extends Component {
    static template = "proof.PasswordProof";
    static props = {
        options: t.object(),
        busy: t.boolean(),
        prove: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ password: "" });
        this.inputRef = /** @type {any} */ (elementRef());
        useAutofocus({ ref: this.inputRef });
    }

    /** @param {Event} ev */
    onInput(ev) {
        this.state.password = /** @type {HTMLInputElement} */ (ev.target).value;
    }

    /** @param {Event} ev */
    onSubmit(ev) {
        ev.preventDefault();
        if (this.state.password) {
            this.props.prove({ password: this.state.password });
        }
    }
}

proofMethodRegistry.add("password", { Component: PasswordProof });
