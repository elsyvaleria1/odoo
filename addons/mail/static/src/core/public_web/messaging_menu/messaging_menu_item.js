// @ts-check
/** @odoo-module native */
import { ActionList } from "@mail/core/common/action_list";
import { useMessageActions } from "@mail/core/common/message_actions";
import { IsolatedDropdown } from "@mail/core/public_web/messaging_menu/isolated_dropdown";
import { NotificationItem } from "@mail/core/public_web/notification_item";
import { useLongPress } from "@mail/utils/common/hooks";
import { Component, t, useProps } from "@odoo/owl";
import { useDropdownState } from "@web/components/dropdown";
import { hasTouch, isMobileOS } from "@web/core/browser/feature_detection";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

export const messagingMenuItemProps = {
    isActive: t.any().optional(),
    message: t.any().optional(),
    onClick: t.any(),
    tab: t.any(),
};

export class MessagingMenuItem extends Component {
    static components = { ActionList, IsolatedDropdown, NotificationItem };
    static props = messagingMenuItemProps;
    static template = "mail.MessagingMenuItem";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.hasTouch = hasTouch;
        this.isMobileOS = isMobileOS();
        this.rootRef = elementRef();
        this.actionsDropdown = useDropdownState();
        this.messageActions = this.props.message
            ? useMessageActions({
                  owner: this,
                  message: () => this.message,
                  thread: () => this.message?.thread,
              })
            : undefined;
        useLongPress(this.rootRef, {
            action: () => this.actionsDropdown.open(),
            predicate: () => this.isMobileOS && this.hasActions,
        });
    }

    /** @param {MouseEvent} ev */
    onContextMenu(ev) {
        if (this.isMobileOS || !this.hasActions) {
            return;
        }
        ev.preventDefault();
        this.actionsDropdown.open();
    }

    get hasActions() {
        return this.messageActionLists.some((actions) => actions.length > 0);
    }

    get actionsTitle() {
        return _t("Message Actions");
    }

    /** @returns {import("@mail/core/common/message_actions").MessageAction[][]} */
    get messageActionLists() {
        const allowedIds = this.props.tab?.messageActionIds;
        if (!this.messageActions || !allowedIds?.length) {
            return [];
        }
        const { quick, other, group } = this.messageActions.partition;
        return [quick, other, ...group]
            .map((actions) =>
                actions.filter((action) => allowedIds.includes(action.id)),
            )
            .filter((actions) => actions.length > 0);
    }

    /** @returns {import("models").Message|undefined} */
    get message() {
        return this.props.message;
    }

    get itemName() {
        return this.message?.thread?.displayName ?? this.message?.authorName;
    }

    get itemPreviewText() {
        if (!this.message) {
            return _t("This is the start of your conversation");
        }
        return this.message.previewText;
    }

    get isOpenInDiscuss() {
        const thread = this.message?.thread;
        return Boolean(
            thread &&
            this.store.discuss?.isActive &&
            thread.eq(this.store.discuss.thread),
        );
    }

    /** @returns {Object|null} */
    get notificationItemProps() {
        const message = this.message;
        if (!message) {
            return null;
        }
        const needaction = Boolean(message.needaction);
        return {
            thread: message.thread,
            datetime: message.datetime,
            iconSrc: message.author?.avatarUrl ?? message.thread?.avatarUrl,
            important: needaction,
            hasMarkAsReadButton: needaction,
            isActive: this.props.isActive || this.isOpenInDiscuss,
            muted: needaction ? 0 : 1,
            nameMaxLine: 1,
            textMaxLine: 2,
            onSwipeRight:
                this.hasTouch() && needaction
                    ? {
                          action: () => message.setDone(),
                          icon: "fa-check-circle",
                          bgColor: "bg-success",
                      }
                    : undefined,
            onClick: (/** @type {boolean} */ isMarkAsRead) =>
                this.props.onClick({ isMarkAsRead }),
        };
    }
}
