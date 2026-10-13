/** @odoo-module native */
import { StreamPostComment } from "@social/js/stream_post_comment";
import { fromEpochMilliseconds } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";

import { StreamPostCommentsReplyLinkedin } from "./stream_post_comments_reply.js";

export class StreamPostCommentLinkedin extends StreamPostComment {
    async _onReplyComment() {
        if (!this.action.showReplyComment) {
            await this._onLoadReplies();
        }
        await super._onReplyComment();
    }

    async _onLoadReplies() {
        const innerComments = await rpc("/social_linkedin/get_comments", {
            stream_post_id: this.originalPost.id.raw_value,
            comment_urn: this.comment.id,
            comments_count: this.commentsCount,
        });
        this.comment.comments.data = innerComments.comments;

        super._onLoadReplies();
    }

    get authorPictureSrc() {
        return this.comment.from.picture;
    }

    get link() {
        const activityUrn = this.comment.id.split("(")[1].split(",")[0];
        return `https://www.linkedin.com/feed/update/${encodeURIComponent(activityUrn)}?commentUrn=${encodeURIComponent(this.comment.id)}`;
    }

    get authorLink() {
        if (this.comment.from.isOrganization) {
            return `https://www.linkedin.com/company/${encodeURIComponent(this.comment.from.vanityName)}`;
        }
        return `https://www.linkedin.com/in/${encodeURIComponent(this.comment.from.vanityName)}`;
    }

    get isAuthor() {
        return this.comment.from.id === this.props.mediaSpecificProps.currentUserUrn;
    }

    get commentReplyComponent() {
        return StreamPostCommentsReplyLinkedin;
    }

    get deleteCommentEndpoint() {
        return "/social_linkedin/delete_comment";
    }

    get isLikable() {
        return true;
    }

    get isEditable() {
        return true;
    }

    /** @returns {Temporal.ZonedDateTime} */
    get commentCreatedTime() {
        return (
            super.commentCreatedTime ?? fromEpochMilliseconds(this.comment.created_time)
        );
    }
}
