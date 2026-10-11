/** @odoo-module native */
import { StreamPostComments } from "@social/js/stream_post_comments";
import { useSocialContext } from "@social/social_context";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(StreamPostComments.prototype, {
    setup() {
        super.setup(...arguments);
        this.socialContext = useSocialContext();

        this.actionService = useService("action");
    },

    isConvertibleToLead() {
        return !this.isAuthor;
    },

    generateLeadFromPost() {
        this.actionService.doAction("social_crm.social_post_to_lead_action", {
            additionalContext: {
                default_conversion_source: "stream_post",
                default_social_stream_post_id: this.originalPost.id.raw_value,
                default_social_account_id: this.originalPost.account_id.raw_value,
                default_post_content: this._formatPost(
                    this.originalPost.message.raw_value,
                ),
                default_post_image_urls:
                    this.originalPost.stream_post_image_urls.raw_value,
            },
        });

        this.socialContext.closeCommentsModal();
    },
});
