import { mailModels } from "@mail/../tests/mail_test_helpers";
import { patch } from "@web/core/utils/patch";

patch(mailModels.DiscussChannel.prototype, {
    _channel_type_policies() {
        return {
            ...super._channel_type_policies(...arguments),
            telegram: {
                allows_seen_infos: false,
                allows_unfollow: true,
                describes_as_channel: false,
                email_invite: "never",
                has_description: true,
                lazy_loads_members: true,
                member_based_naming: false,
                mentionable_by_hashtag: false,
                notify_opted_in_only: true,
                supports_sub_channels: true,
            },
        };
    },
});
