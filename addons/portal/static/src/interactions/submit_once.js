/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SubmitOnce extends Interaction {
    static selector = "form[data-o-submit-once]";
    dynamicContent = {
        _root: { "t-on-submit": this.onSubmit },
    };

    onSubmit() {
        for (const buttonEl of this.el.querySelectorAll("button[type=submit]")) {
            /** @type {HTMLButtonElement} */ (buttonEl).disabled = true;
        }
    }
}

registry.category("public.interactions").add("portal.submit_once", SubmitOnce);
