// @ts-check
/** @odoo-module native */
import { ACTION_TAGS } from "@mail/core/common/action";
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { AttachmentPanel } from "@mail/discuss/core/common/attachment_panel";
import { ChannelInvitation } from "@mail/discuss/core/common/channel_invitation";
import { DeleteThreadDialog } from "@mail/discuss/core/common/delete_thread_dialog";
import { NotificationSettings } from "@mail/discuss/core/common/notification_settings";
import { mailContextOf } from "@mail/utils/common/mail_context";
import { Component, t, useProps, xml } from "@odoo/owl";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";
import { usePopover } from "@web/ui/popover";

/** @typedef {import("@mail/core/common/thread_actions").ActionParams} ActionParams */
/** @typedef {import("@mail/core/common/thread_actions").ThreadActionOwner} ThreadActionOwner */
class ChannelActionDialog extends Component {
    static props = {
        title: t.any(),
        contentComponent: t.any(),
        contentProps: t.any(),
        close: t.any().optional(),
    };
    static components = { Dialog };
    static template = xml`
        <Dialog size="'md'" title="this.props.title" footer="false" contentClass="'o-bg-body'" bodyClass="'p-1'">
            <t t-component="this.props.contentComponent" t-props="this.props.contentProps"/>
        </Dialog>
    `;
    props = useProps(this.constructor.props);
}

registerThreadAction("notification-settings", {
    actionPanelComponent: NotificationSettings,
    /** @param {ActionParams} params */
    condition: ({ owner, store, thread }) =>
        thread?.isChannelKind &&
        store.self_partner &&
        (!owner.props.chatWindow || owner.props.chatWindow.isOpen),
    /** @param {ActionParams} params */
    setup({ owner }) {
        if (!owner.props.chatWindow) {
            this.popover = usePopover(NotificationSettings, {
                onClose: () => this.close(),
                position: "bottom-end",
                fixedPosition: true,
                class: this.panelOuterClass,
            });
        }
    },
    /** @param {ActionParams} params */
    open({ owner, store, thread }) {
        if (owner.isChannelActionList || mailContextOf(owner).inMeetingView) {
            store.env.services.dialog?.add(ChannelActionDialog, {
                title: thread.displayName,
                contentComponent: NotificationSettings,
                contentProps: { thread },
            });
        } else {
            this.popover?.open(owner.root.el.querySelector(`[name="${this.id}"]`), {
                hasSizeConstraints: true,
                thread,
            });
        }
    },
    /** @param {ActionParams} params */
    close: ({ action }) => action.popover?.close(),
    /** @param {ActionParams} params */
    icon: ({ thread }) =>
        thread.channel?.isMuted
            ? "fa-solid fa-bell-slash text-danger"
            : "fa-solid fa-bell",
    name: _t("Notification Settings"),
    panelOuterClass: "bg-100 border border-secondary",
    sequence: 10,
    sequenceGroup: 30,
    toggle: true,
});
/**
 * @param {import("models").DiscussChannel} channel
 * @param {boolean} isFavorite
 * @param {ThreadActionOwner} owner
 */
async function setFavorite(channel, isFavorite, owner) {
    const member = channel.self_member_id;
    member.is_favorite = isFavorite;
    try {
        await rpc("/discuss/channel/favorite", {
            channel_id: channel.id,
            is_favorite: isFavorite,
        });
    } catch (error) {
        member.is_favorite = !isFavorite;
        throw error;
    }
    if (owner.isChannelActionList) {
        return;
    }
    channel.store.env.services.notification.add(
        isFavorite
            ? _t("Added %(name)s to Favorites", { name: channel.displayName })
            : _t("Removed %(name)s from Favorites", { name: channel.displayName }),
        { type: isFavorite ? "success" : "warning" },
    );
}
registerThreadAction("add-to-favorites", {
    /** @param {ActionParams} params */
    condition: ({ owner, store, thread }) =>
        store.selfIsInternalUser &&
        Boolean(thread?.channel?.self_member_id) &&
        !thread.channel.self_member_id.is_favorite &&
        !owner.isDiscussContent,
    /** @param {ActionParams} params */
    open: ({ owner, thread }) => setFavorite(thread.channel, true, owner),
    icon: "fa-regular fa-star",
    name: _t("Add to Favorites"),
    sequence: 40,
    sequenceGroup: 20,
});
registerThreadAction("remove-from-favorites", {
    /** @param {ActionParams} params */
    condition: ({ owner, thread }) =>
        Boolean(thread?.channel?.self_member_id?.is_favorite) &&
        !owner.isDiscussContent,
    /** @param {ActionParams} params */
    open: ({ owner, thread }) => setFavorite(thread.channel, false, owner),
    icon: "fa-solid fa-star",
    name: _t("Remove from Favorites"),
    sequence: 40,
    sequenceGroup: 20,
});
registerThreadAction("attachments", {
    actionPanelComponent: AttachmentPanel,
    /** @param {ActionParams} params */
    condition: ({ owner, thread }) =>
        thread?.hasAttachmentPanel &&
        (!owner.props.chatWindow || owner.props.chatWindow.isOpen) &&
        !owner.isChannelActionList,
    icon: "fa-solid fa-paperclip",
    name: _t("Attachments"),
    sequence: 10,
    sequenceGroup: 10,
    toggle: true,
});
registerThreadAction("invite-people", {
    actionPanelComponent: ChannelInvitation,
    /** @param {ActionParams} params */
    actionPanelComponentProps: ({ action }) => ({ close: () => action.close() }),
    /** @param {ActionParams} params */
    close: ({ action }) => action.popover?.close(),
    /** @param {ActionParams} params */
    condition: ({ owner, thread }) =>
        thread?.isChannelKind &&
        (!owner.props.chatWindow || owner.props.chatWindow.isOpen),
    /** @param {ActionParams} params */
    panelOuterClass: ({ owner }) =>
        `o-discuss-ChannelInvitation ${
            owner.props.chatWindow ? "bg-inherit" : ""
        } bg-100 border border-secondary`,
    icon: "oi oi-fw oi-user-plus",
    name: _t("Invite People"),
    /** @param {ActionParams} params */
    open({ owner, store, thread }) {
        if (owner.isChannelActionList) {
            store.env.services.dialog?.add(ChannelActionDialog, {
                title: thread.displayName,
                contentComponent: ChannelInvitation,
                contentProps: {
                    autofocus: true,
                    thread,
                    close: () => store.env.services.dialog.closeAll(),
                },
            });
        } else if (!mailContextOf(owner).inMeetingView) {
            this.popover?.open(owner.root.el.querySelector(`[name="${this.id}"]`), {
                hasSizeConstraints: true,
                thread,
            });
        }
    },
    /** @param {ActionParams} params */
    sequence: ({ owner }) => (owner.isChannelActionList ? 20 : 10),
    sequenceGroup: 20,
    /** @param {ActionParams} params */
    setup({ owner }) {
        if (!owner.props.chatWindow && !mailContextOf(owner).inMeetingView) {
            this.popover = usePopover(ChannelInvitation, {
                onClose: () => this.close(),
                class: this.panelOuterClass,
            });
        }
    },
    toggle: true,
});
registerThreadAction("mark-read", {
    /** @param {ActionParams} params */
    condition: ({ owner, thread }) =>
        thread?.channel?.self_member_id &&
        thread.channel.self_member_id.message_unread_counter > 0 &&
        !thread.channel.isMuted &&
        owner.isChannelActionList,
    /** @param {ActionParams} params */
    open: ({ owner }) => owner.thread.markAsRead(),
    icon: "fa-solid fa-check",
    name: _t("Mark Read"),
    sequence: 10,
    sequenceGroup: 20,
});
registerThreadAction("delete-thread", {
    actionPanelComponent: DeleteThreadDialog,
    /** @param {ActionParams} params */
    actionPanelComponentProps({ action }) {
        return { close: () => action.close() };
    },
    /** @param {ActionParams} params */
    condition({ owner, store, thread }) {
        return (
            thread?.channel?.parent_channel_id &&
            store.selfUser?.eq(thread.create_uid) &&
            !owner.isDiscussContent
        );
    },
    panelOuterClass: "bg-100",
    icon: "fa-solid fa-trash-can",
    name: _t("Delete Thread"),
    /** @param {ActionParams} params */
    close: ({ action }) => action.popover?.close(),
    toggle: true,
    /** @param {ActionParams} params */
    open: ({ action, owner, store, thread }) => {
        if (owner.isChannelActionList) {
            store.env.services.dialog?.add(ChannelActionDialog, {
                title: thread.channel.name,
                contentComponent: DeleteThreadDialog,
                contentProps: {
                    close: () => store.env.services.dialog.closeAll(),
                    thread,
                },
            });
        }
    },
    /** @param {ActionParams} params */
    sequence: ({ owner }) => (owner.props.chatWindow ? 50 : 40),
    sequenceGroup: 40,
    tags: [ACTION_TAGS.DANGER],
});
