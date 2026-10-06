// @ts-check
/** @odoo-module native */
import { attClassObjectToString } from "@mail/utils/common/format";
import { provideMailContext, useMailContext } from "@mail/utils/common/mail_context";
import { Component, t, useProps } from "@odoo/owl";
import { ResizablePanel } from "@web/components/resizable_panel";
import { elementRef } from "@web/core/utils/element_ref";
import { useForwardRefToParent, useService } from "@web/core/utils/hooks";
/**
 * @typedef {Object} Props
 * @prop {string} [title]
 * @prop {boolean} [resizable]
 * @prop {number} [initialWidth]
 * @prop {number} [minWidth]
 * @prop {Object} [slots]
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ActionPanel extends Component {
    static template = "mail.ActionPanel";
    static components = { ResizablePanel };
    static props = {
        contentRef: t.any().optional(),
        icon: t.any().optional(),
        title: t.any().optional(),
        resizable: t.any().optional(true),
        slots: t.any().optional(),
        initialWidth: t.any().optional(),
        minWidth: t.any().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.ui = useService("ui");
        this.contentRefRef = elementRef();
        useForwardRefToParent("contentRef", this.contentRefRef);
        provideMailContext({ inDiscussActionPanel: true });
        this.mailContext = useMailContext();
    }

    get classNames() {
        return attClassObjectToString({
            "o-mail-ActionPanel overflow-auto o-scrollbar-thin d-flex flex-column flex-shrink-0 position-relative py-2 pt-0 h-100 bg-inherit": true,
            "o-mail-ActionPanel-chatter": this.mailContext.inChatter,
            "o-chatWindow": this.mailContext.inChatWindow,
            "px-2": !this.mailContext.inChatter && !this.mailContext.inMeetingChat,
            rounded: !this.props.resizable,
        });
    }

    get minWidth() {
        return this.props.minWidth;
    }

    get initialWidth() {
        return this.props.initialWidth;
    }
}
