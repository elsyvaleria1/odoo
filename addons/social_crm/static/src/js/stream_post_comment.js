/** @odoo-module native */
import { StreamPostComment } from "@social/js/stream_post_comment";
import { useSocialContext } from "@social/social_context";
import { serializeDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(StreamPostComment.prototype, {
    setup() {
        super.setup(...arguments);
        this.socialContext = useSocialContext();

        this.actionService = useService("action");
    },

    isManageable() {
        return super.isManageable() || this.isConvertibleToLead();
    },

    isConvertibleToLead() {
        return !this.isAuthor;
    },

    generateLeadFromComment() {
        this.actionService.doAction("social_crm.social_post_to_lead_action", {
            additionalContext: {
                default_conversion_source: "comment",
                default_social_stream_post_id: this.originalPost.id.raw_value,
                default_social_account_id: this.originalPost.account_id.raw_value,
                default_author_name: this.comment.from.name,
                default_post_content: this._formatPost(this.comment.message),
                default_post_image_urls:
                    this.comment.attachment?.type === "photo"
                        ? `["${this.comment.attachment.media.image.src}"]`
                        : false,
                default_post_datetime: serializeDateTime(this.commentCreatedTime),
                default_post_link: this.originalPost.post_link.raw_value,
            },
        });

        this.socialContext.closeCommentsModal();
    },
});
