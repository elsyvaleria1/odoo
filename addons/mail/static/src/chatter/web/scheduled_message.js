// @ts-check
/** @odoo-module native */
import { AttachmentList } from "@mail/core/common/attachment_list";
import { RelativeTime } from "@mail/core/common/relative_time";
import { AvatarCardPopover } from "@mail/discuss/web/avatar_card/avatar_card_popover";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { DATETIME_SHORT, toLocaleString } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { usePopover } from "@web/ui/popover";
export const SCHEDULED_MESSAGE_TRUNCATE_THRESHOLD = 50;

export class ScheduledMessage extends Component {
    static props = {
        onScheduledMessageChanged: t.function(),
        scheduledMessage: t.object(),
    };
    static template = "mail.ScheduledMessage";
    static components = {
        AttachmentList,
        RelativeTime,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.state = proxy({
            readMore: false,
        });
        this.avatarCard = usePopover(AvatarCardPopover);
        this.dialogService = useService("dialog");
        this.linkNavigation = useService("mail.link_navigation");
    }

    get isShort() {
        return (
            this.props.scheduledMessage.textContent.length <
            SCHEDULED_MESSAGE_TRUNCATE_THRESHOLD
        );
    }

    get scheduledDate() {
        return toLocaleString(
            this.props.scheduledMessage.scheduled_date,
            DATETIME_SHORT,
        );
    }

    get truncatedMessage() {
        return (
            this.props.scheduledMessage.textContent.substring(
                0,
                SCHEDULED_MESSAGE_TRUNCATE_THRESHOLD,
            ) + "..."
        );
    }

    async cancel() {
        const thread = this.props.scheduledMessage.thread;
        await this.props.scheduledMessage.cancel();
        this.props.onScheduledMessageChanged(thread);
    }

    /** @param {MouseEvent} ev */
    onClick(ev) {
        this.linkNavigation.handleClickOnLink(ev, this.props.scheduledMessage.thread);
    }

    /** @param {import("models").Attachment} attachment */
    async onClickAttachmentUnlink(attachment) {
        attachment.remove();
    }

    /** @param {MouseEvent} ev */
    onClickAuthor(ev) {
        if (!this.avatarCard.isOpen) {
            this.avatarCard.open(/** @type {HTMLElement} */ (ev.currentTarget), {
                id: this.props.scheduledMessage.author_id.main_user_id?.id,
            });
        }
    }

    onClickCancel() {
        this.dialogService.add(ConfirmationDialog, {
            body: _t("Are you sure you want to cancel the scheduled message?"),
            cancel: () => {},
            cancelLabel: _t("Close"),
            confirm: this.cancel.bind(this),
            confirmLabel: _t("Cancel Message"),
        });
    }

    async onClickEdit() {
        await this.props.scheduledMessage.edit();
        this.props.onScheduledMessageChanged(this.props.scheduledMessage.thread);
    }

    async onClickSendNow() {
        await this.props.scheduledMessage.send();
        this.props.onScheduledMessageChanged(this.props.scheduledMessage.thread);
    }
}
