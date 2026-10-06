/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { isSafeUrlScheme } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";

export class SelectNavigate extends Interaction {
    static selector = "select[data-o-navigate]";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        const url = /** @type {HTMLSelectElement} */ (this.el).value;
        if (url && isSafeUrlScheme(url)) {
            browser.location.href = url;
        }
    }
}

registry.category("public.interactions").add("portal.select_navigate", SelectNavigate);
