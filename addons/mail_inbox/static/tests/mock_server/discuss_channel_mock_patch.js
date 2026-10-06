import { mailModels } from "@mail/../tests/mail_test_helpers";
import { patch } from "@web/core/utils/patch";

patch(mailModels.DiscussChannel.prototype, {
    _channel_type_policies() {
        return {
            ...super._channel_type_policies(...arguments),
            email: {
                allows_seen_infos: false,
                allows_unfollow: false,
                describes_as_channel: false,
                email_invite: "never",
                has_description: false,
                lazy_loads_members: false,
                member_based_naming: false,
                mentionable_by_hashtag: false,
                notify_opted_in_only: false,
                supports_sub_channels: false,
            },
        };
    },
});
