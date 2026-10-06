/** @odoo-module native */
import { StreamPostCommentList } from "@social/js/stream_post_comment_list";

import { StreamPostCommentInstagram } from "./stream_post_comment.js";

export class StreamPostCommentListInstagram extends StreamPostCommentList {
    get commentComponent() {
        return StreamPostCommentInstagram;
    }
}
