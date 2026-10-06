/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { isSafeUrlScheme } from "@web/core/utils/urls";
import { Interaction } from "@web/public/interaction";

const OWN_ACTION_SELECTOR =
    "a[href], button, input, select, textarea, label, summary, [role='button'], [data-o-href]";

export class HrefLink extends Interaction {
    static selector = "[data-o-href]";
    dynamicContent = {
        _root: { "t-on-click": this.onClick },
    };

    /**
     * @param {MouseEvent} ev
     */
    onClick(ev) {
        const actionEl = /** @type {HTMLElement} */ (ev.target).closest(
            OWN_ACTION_SELECTOR,
        );
        if (actionEl && actionEl !== this.el && this.el.contains(actionEl)) {
            return;
        }
        ev.preventDefault();
        const href = this.el.dataset.oHref;
        if (href && isSafeUrlScheme(href)) {
            browser.location.href = href;
        }
    }
}

registry.category("public.interactions").add("portal.href_link", HrefLink);
