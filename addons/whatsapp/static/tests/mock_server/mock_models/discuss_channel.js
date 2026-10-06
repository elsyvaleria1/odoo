import { mailModels } from "@mail/../tests/mail_test_helpers";
import { mailDataHelpers } from "@mail/../tests/mock_server/mail_mock_server";
import { fields, makeKwArgs } from "@web/../tests/web_test_helpers";
import { now, serializeDateTime } from "@web/core/l10n/dates";

export class DiscussChannel extends mailModels.DiscussChannel {
    whatsapp_channel_valid_until = fields.Datetime({
        default: () => serializeDateTime(now().add({ days: 1 })),
    });
    wa_account_id = fields.Generic({ default: () => 1 });

    /**
     * @override
     * @type {typeof mailModels.DiscussChannel["prototype"]["_to_store"]}
     */
    _to_store(store, fields) {
        /** @type {import("mock_models").ResPartner} */
        const ResPartner = this.env["res.partner"];

        super._to_store(...arguments);
        if (fields && Array.isArray(fields) && fields.length) {
            return;
        }
        const channels = this._filter([
            ["id", "in", this.map((channel) => channel.id)],
            ["channel_type", "=", "whatsapp"],
        ]);
        for (const channel of channels) {
            store._add_record_fields(this.browse(channel.id), {
                whatsapp_channel_valid_until:
                    channel.whatsapp_channel_valid_until || false,
                whatsapp_partner_id: mailDataHelpers.Store.one(
                    ResPartner.browse(channel.whatsapp_partner_id),
                    makeKwArgs({ only_id: true }),
                ),
                wa_account_id: mailDataHelpers.Store.one(
                    this.env["whatsapp.account"].browse(channel.wa_account_id),
                    makeKwArgs({ fields: ["name"] }),
                ),
            });
        }
    }

    /**
     * @override
     * @type {typeof mailModels.DiscussChannel["prototype"]["_channel_type_policies"]}
     */
    _channel_type_policies() {
        return {
            ...super._channel_type_policies(...arguments),
            whatsapp: {
                allows_seen_infos: true,
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
}
