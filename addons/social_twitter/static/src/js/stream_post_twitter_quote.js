/** @odoo-module native */
import { Component, proxy, useProps } from "@odoo/owl";
import { SocialPostFormatterMixin } from "@social/js/social_post_formatter_mixin";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

import { StreamPostCommentsReplyTwitterQuote } from "./stream_post_comments_reply_quote.js";

export class StreamPostTwitterQuote extends SocialPostFormatterMixin(Component) {
    static template = "social_twitter.TwitterQuoteDialog";
    static components = { Dialog, StreamPostCommentsReplyTwitterQuote };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.notification = useService("notification");
        this.state = proxy({
            isEditMode: false,
        });
    }

    _confirmQuoteTweet(event) {
        const formData = new FormData(
            event.currentTarget.closest(".modal-content").querySelector("form"),
        );

        const xhr = new window.XMLHttpRequest();
        xhr.open(
            "POST",
            `/social_twitter/${encodeURIComponent(this.originalPost.stream_id.raw_value)}/quote`,
        );
        formData.append("csrf_token", odoo.csrf_token);
        formData.append("tweet_id", this.originalPost.twitter_tweet_id.raw_value);
        formData.append("stream_id", this.originalPost.stream_id.raw_value);
        xhr.send(formData);
        xhr.onload = () => {
            const result = JSON.parse(xhr.response);
            if (result === true) {
                this.props.refreshStats();
            } else if (result.error) {
                this.notification.add(result.error, { type: "danger" });
            }
        };
        xhr.onerror = () => {
            this.notification.add(_t("Error while sending the data to the server."), {
                type: "warning",
            });
        };
        xhr.onloadend = () => {
            this.props.close();
        };
    }

    _formatCommentStreamPost(message) {
        return this._formatPost(message);
    }

    get originalPost() {
        return this.props.originalPost;
    }

    get JSON() {
        return JSON;
    }
}
