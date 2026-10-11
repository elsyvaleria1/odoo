/** @odoo-module native */
import { StreamPostComment } from "@social/js/stream_post_comment";
import { _t } from "@web/core/translation";
import { url } from "@web/core/utils/urls";

import { StreamPostCommentsReplyTwitter } from "./stream_post_comments_reply.js";

export class StreamPostCommentTwitter extends StreamPostComment {
    get authorPictureSrc() {
        return this.comment.from.profile_image_url;
    }

    get link() {
        return `https://www.twitter.com/${encodeURIComponent(this.comment.from.id)}/statuses/${encodeURIComponent(this.comment.id)}`;
    }

    get authorLink() {
        return url("https://twitter.com/intent/user", {
            user_id: this.comment.from.id,
        });
    }

    get isAuthor() {
        return this.comment.from.id === this.props.mediaSpecificProps.twitterUserId;
    }

    get commentReplyComponent() {
        return StreamPostCommentsReplyTwitter;
    }

    get deleteCommentEndpoint() {
        return "/social_twitter/delete_tweet";
    }

    get isEditable() {
        return false;
    }

    get likesClass() {
        return "fa-heart";
    }

    get commentName() {
        return _t("Tweet");
    }
}
