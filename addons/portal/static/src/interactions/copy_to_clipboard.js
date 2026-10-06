/** @odoo-module native */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class CopyToClipboard extends Interaction {
    static selector = "button[data-clipboard-text]";
    dynamicContent = {
        _root: { "t-on-click": this.onClick },
    };

    async onClick() {
        await this.waitFor(
            browser.navigator.clipboard.writeText(this.el.dataset.clipboardText),
        );
    }
}

registry
    .category("public.interactions")
    .add("portal.copy_to_clipboard", CopyToClipboard);
