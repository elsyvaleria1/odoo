// @ts-check
/** @odoo-module native */
import { CountryFlag } from "@mail/core/common/country_flag";
import { ImStatus } from "@mail/core/common/im_status";
import { baseImStatus } from "@mail/core/common/presence_status";
import { useHover } from "@mail/utils/common/hooks";
import { provideMailContext, useMailContext } from "@mail/utils/common/mail_context";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { makeLogger } from "@web/core/debug/debug_logger";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useChildRef, useEventBus, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { usePopover } from "@web/ui/popover";

const log = makeLogger("mail.chat_hub");
class ChatBubblePreview extends Component {
    static props = { chatWindow: t.any(), close: t.any() };
    static template = "mail.ChatBubblePreview";
    props = useProps(this.constructor.props);

    /** @returns {import("models").Thread} */
    get thread() {
        return this.props.chatWindow.thread;
    }

    get previewText() {
        const lastMessage = this.thread?.newestPersistentOfAllMessage;
        if (!lastMessage) {
            return false;
        }
        return lastMessage.previewText;
    }
}

export const BOUNCE_DURATION_MS = 4000;

/**
 * @typedef {Object} Props
 * @extends {Component<Props, import("@web/env").OdooEnv>}
 */
export class ChatBubble extends Component {
    static components = { CountryFlag, ImStatus };
    static props = { chatWindow: t.any() };
    static template = "mail.ChatBubble";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
        this.store = useService("mail.store");
        const popoverRef = useChildRef();
        this.isMobileOS = isMobileOS();
        this.popover = usePopover(ChatBubblePreview, {
            animation: false,
            position: "left-middle",
            class: "dropdown-menu bg-view border-0 p-0 overflow-visible o-rounded-bubble mx-1",
            ref: popoverRef,
        });
        useBus(
            this.bus,
            "ChatBubble:preview-will-open",
            /** @param {CustomEvent<ChatBubble>} ev */
            ({ detail }) => {
                if (detail === this) {
                    return;
                }
                this.popover.close();
            },
        );
        this.rootRef = elementRef();
        this.hover = useHover([this.rootRef, popoverRef], {
            onHover: () => {
                log.logic("preview open", () => ({ thread: this.thread?.localId }));
                this.bus.trigger("ChatBubble:preview-will-open", this);
                this.popover.open(this.rootRef.el, {
                    chatWindow: this.props.chatWindow,
                });
            },
            onAway: () => this.popover.close(),
        });
        this.state = proxy({ bouncing: false });
        this.bounceDeadline = 0;
        let previousCounter = this.thread?.importantCounter ?? 0;
        useLayoutEffect(
            /** @param {number|undefined} importantCounter */
            (importantCounter = 0) => {
                if (importantCounter > previousCounter) {
                    this.startBouncing();
                } else if (importantCounter === 0) {
                    this.state.bouncing = false;
                }
                previousCounter = importantCounter;
            },
            () => [this.thread?.importantCounter],
        );
        provideMailContext({ inChatBubble: true });
        this.mailContext = useMailContext();
    }

    /** @returns {import("models").Thread} */
    get thread() {
        return this.props.chatWindow.thread;
    }

    startBouncing() {
        this.bounceDeadline = Date.now() + BOUNCE_DURATION_MS;
        this.state.bouncing = true;
    }

    onBounceEnd() {
        if (Date.now() >= this.bounceDeadline) {
            this.state.bouncing = false;
        }
    }

    get showImStatus() {
        return (
            this.thread?.channel?.correspondent?.im_status &&
            baseImStatus(this.thread.channel.correspondent.im_status) !== "offline"
        );
    }
}
