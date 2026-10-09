/** @odoo-module native */
import { registry } from "@web/core/registry";
import { isSafeUrlScheme } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";
import { requestNavigation } from "@web/public/partial_navigation";

export class SelectNavigate extends Interaction {
    static selector = "select[data-o-navigate]";
    dynamicContent = {
        _root: { "t-on-change": this.onChange },
    };

    onChange() {
        const url = /** @type {HTMLSelectElement} */ (this.el).value;
        if (url && isSafeUrlScheme(url)) {
            requestNavigation(this.el, url);
        }
    }
}

registry.category("public.interactions").add("portal.select_navigate", SelectNavigate);
