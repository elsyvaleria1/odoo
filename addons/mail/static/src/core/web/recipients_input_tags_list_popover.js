// @ts-check
/** @odoo-module native */
import { parseEmail } from "@mail/utils/common/format";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { elementRef } from "@web/core/utils/element_ref";
import { isEmail } from "@web/core/utils/format/strings";
import { useMountedListener, useService } from "@web/core/utils/hooks";
export class RecipientsInputTagsListPopover extends Component {
    static props = {
        tagToUpdate: t.object(),
        onUpdateTag: t.function(),
        close: t.function(),
    };
    static template = "mail.RecipientsInputTagsListPopover";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.state = proxy({ value: "", error: false });
        this.popoverRef = elementRef();
        useMountedListener(
            window,
            "click",
            /** @param {MouseEvent} ev */ (ev) => {
                if (
                    this.popoverRef.el &&
                    !this.popoverRef.el.contains(/** @type {Node} */ (ev.target))
                ) {
                    this.discardTag();
                }
            },
        );
    }

    /** @param {KeyboardEvent} ev */
    onKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        this.state.error = false;
        if (hotkey === "enter") {
            this.updateTag();
        }
        if (hotkey === "escape") {
            this.discardTag();
        }
    }

    updateTag() {
        if (!this.isValidEmail) {
            this.state.error = true;
            return;
        }
        this.props.onUpdateTag(this.state.value);
        this.props.close();
    }

    discardTag() {
        this.props.tagToUpdate.onDelete();
        this.props.close();
    }

    get isValidEmail() {
        const value = parseEmail(this.state.value);
        const name = value ? value[0] : "";
        return isEmail(name);
    }
}
