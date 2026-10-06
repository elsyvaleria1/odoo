// @ts-check
/** @odoo-module native */

import { Component, onWillUnmount, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { elementRef } from "@web/core/utils/element_ref";
import { faIconClass } from "@web/core/utils/icons";
import { usePopover } from "@web/ui/popover/popover_hook";
import { Tooltip } from "@web/ui/tooltip/tooltip";

export class CopyButton extends Component {
    static template = "web.CopyButton";
    static props = {
        className: t.string().optional(),
        copyText: t.string().optional(),
        disabled: t.boolean().optional(),
        successText: t.string().optional(),
        icon: t.string().optional(),
        content: t.or([t.string(), t.object(), t.function()]).optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("@odoo/owl").Ref<HTMLButtonElement>} */
    button;
    /** @type {any} */
    popover;

    /** @type {number | undefined} */
    tooltipCloseTimer;

    get iconClass() {
        return faIconClass(this.props.icon || "fa-clipboard");
    }

    setup() {
        /** @type {import("@odoo/owl").Ref<HTMLButtonElement>} */
        this.button = elementRef();
        this.popover = usePopover(Tooltip);
        onWillUnmount(() => browser.clearTimeout(this.tooltipCloseTimer));
    }

    showTooltip() {
        const target = this.button.el;
        if (!target) {
            return;
        }
        this.popover.open(target, {
            tooltip: this.props.successText,
        });
        browser.clearTimeout(this.tooltipCloseTimer);
        this.tooltipCloseTimer = browser.setTimeout(this.popover.close, 800);
    }

    async onClick() {
        let write, content;
        if (typeof this.props.content === "function") {
            content = await this.props.content();
        } else {
            content = this.props.content;
        }
        if (content === undefined || content === null) {
            return;
        }
        if (typeof content === "string" || content instanceof String) {
            write = (/** @type {string} */ value) =>
                browser.navigator.clipboard.writeText(value);
        } else {
            write = (/** @type {ClipboardItems} */ value) =>
                browser.navigator.clipboard.write(value);
        }
        try {
            await write(content);
        } catch (error) {
            return browser.console.warn(error);
        }
        this.showTooltip();
    }
}
