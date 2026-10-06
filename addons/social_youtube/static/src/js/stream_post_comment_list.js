/** @odoo-module native */
import { StreamPostCommentList } from "@social/js/stream_post_comment_list";

import { StreamPostCommentYoutube } from "./stream_post_comment.js";

export class StreamPostCommentListYoutube extends StreamPostCommentList {
    get commentComponent() {
        return StreamPostCommentYoutube;
    }
}
