import { mailModels } from "@mail/../tests/mail_test_helpers";
import { Command, fields } from "@web/../tests/web_test_helpers";

export class DiscussChannel extends mailModels.DiscussChannel {
    ai_agent_id = fields.Many2one({
        relation: "ai.agent",
    });

    _channel_basic_info_fields() {
        return [...super._channel_basic_info_fields(), "ai_agent_id"];
    }

    _channel_type_policies() {
        return {
            ...super._channel_type_policies(...arguments),
            ai_chat: {
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
    }

    /** @param {import("@mail/../tests/mock_server/mock_models/res_partner").ResPartner} partner */
    _get_or_create_ai_chat(partner) {
        const channels = this.env["discuss.channel"].search([
            ["is_member", "=", true],
            ["channel_type", "=", "ai_chat"],
            ["channel_member_ids", "any", ["partner_id", "=", partner.id]],
        ]);

        if (!channels[0]) {
            return this.env["discuss.channel"].create({
                name: partner.name,
                channel_type: "ai_chat",
                channel_member_ids: [
                    Command.create({
                        partner_id: this.env.user.partner_id.id,
                    }),
                    Command.create({
                        partner_id: partner.id,
                    }),
                ],
            });
        }

        return channels[0];
    }
}
