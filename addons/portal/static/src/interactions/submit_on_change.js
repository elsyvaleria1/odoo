/** @odoo-module native */
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SubmitOnChange extends Interaction {
    static selector = "input[data-o-submit-on-change]";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        /** @type {HTMLInputElement} */ (this.el).form?.submit();
    }
}

registry.category("public.interactions").add("portal.submit_on_change", SubmitOnChange);
