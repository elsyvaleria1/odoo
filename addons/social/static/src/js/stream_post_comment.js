/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { parseISO } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

import { SocialPostFormatterMixin } from "./social_post_formatter_mixin.js";
import { StreamPostCommentsReply } from "./stream_post_comments_reply.js";

export class StreamPostComment extends SocialPostFormatterMixin(Component) {
    static props = null;
    static template = "social.StreamPostComment";
    static components = { Dropdown, DropdownItem };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.dialog = useService("dialog");
        this.action = proxy({
            showSubComment: false,
            showReplyComment: false,
        });
        this.state = proxy({
            editedComment: undefined,
            isEditMode: false,
        });
    }

    //----------
    // Handlers
    //----------

    async _onLoadReplies() {
        this.action.showSubComment = true;
    }

    async _onReplyComment() {
        this.action.showReplyComment = true;
    }

    _toggleEditMode() {
        this.state.isEditMode = !this.state.isEditMode;
    }

    _deleteComment() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete Comment"),
            body: _t("Do you really want to delete this %s?", this.commentName),
            confirmLabel: _t("Delete"),
            confirm: () => {
                this._confirmDeleteComment();
            },
            cancel: () => {},
        });
    }

    //---------
    // Private
    //---------

    async _confirmDeleteComment() {
        await rpc(this.deleteCommentEndpoint, {
            stream_post_id: this.originalPost.id.raw_value,
            comment_id: this.comment.id,
        });

        this.props.onDeleteComment();
    }

    //-------
    // Utils
    //-------

    formatComment(commentMessage) {
        return this._formatPost(commentMessage);
    }

    //----------
    // Getters
    //----------

    get comment() {
        return this.state.editedComment ?? this.props.comment;
    }

    get account() {
        return this.props.account;
    }

    get originalPost() {
        return this.props.originalPost;
    }

    get deleteCommentEndpoint() {
        return null;
    }

    get authorPictureSrc() {
        return "";
    }

    get currentAuthorPictureSrc() {
        return "";
    }

    get commentName() {
        return _t("comment/reply");
    }

    get link() {
        return "";
    }

    get isDeletable() {
        return this.isAuthor;
    }

    get isEditable() {
        return this.isAuthor;
    }

    isManageable() {
        return this.isDeletable || this.isEditable;
    }

    get isAuthor() {
        return false;
    }

    get isLikable() {
        return true;
    }

    get likesClass() {
        return "fa-solid fa-thumbs-up";
    }

    get commentComponent() {
        return this.constructor;
    }

    get commentReplyComponent() {
        return StreamPostCommentsReply;
    }

    /**
     * @returns {Temporal.ZonedDateTime | null} the created time, null when it is not ISO
     */
    get commentCreatedTime() {
        return parseISO(this.comment.created_time);
    }
}
