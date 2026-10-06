/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

export class CloseConfirmation extends Component {
    static template = "im_livechat.CloseConfirmation";
    static props = {
        onCloseConfirmationDialog: t.any(),
        onClickLeaveConversation: t.any(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.confirmRef = elementRef();
        useAutofocus({ ref: this.confirmRef });
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.props.onCloseConfirmationDialog();
        } else if (ev.key === "Enter") {
            this.props.onClickLeaveConversation();
        }
    }
}
