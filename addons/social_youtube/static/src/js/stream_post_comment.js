/** @odoo-module native */
import { StreamPostComment } from "@social/js/stream_post_comment";

import { StreamPostCommentsReplyYoutube } from "./stream_post_comments_reply.js";

export class StreamPostCommentYoutube extends StreamPostComment {
    get authorPictureSrc() {
        return this.comment.from.author_image_url;
    }

    get link() {
        return `https://www.youtube.com/watch?v=${encodeURIComponent(this.originalPost.youtube_video_id.raw_value)}&lc=${encodeURIComponent(this.comment.id)}&feature=em-comments`;
    }

    get authorLink() {
        return this.comment.from ? this.comment.from.author_channel_url : null;
    }

    get isAuthor() {
        return this.comment.from.id === this.props.mediaSpecificProps.youtubeChannelId;
    }

    get commentReplyComponent() {
        return StreamPostCommentsReplyYoutube;
    }

    get deleteCommentEndpoint() {
        return "/social_youtube/delete_comment";
    }

    get isLikable() {
        return false;
    }

    get isDeletable() {
        return true;
    }
}
