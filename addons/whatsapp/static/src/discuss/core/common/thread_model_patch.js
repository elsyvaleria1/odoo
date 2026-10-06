/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";

/** @type {import("models").DiscussChannel} */
const threadPatch = {
    setup() {
        super.setup(...arguments);
        this.whatsapp_partner_id = fields.One("res.partner");
        this.whatsappMember = fields.One("discuss.channel.member", {
            /** @this {import("models").DiscussChannel} */
            compute() {
                return (
                    this.channel_type === "whatsapp" &&
                    this.channel_member_ids.find((member) =>
                        member.partner_id?.eq(this.whatsapp_partner_id),
                    )
                );
            },
        });
    },
    _computeOfflineMembers() {
        const res = super._computeOfflineMembers();
        if (this.channel_type === "whatsapp") {
            return res.filter((member) =>
                member.partner_id?.notEq(this.whatsapp_partner_id),
            );
        }
        return res;
    },
    get hasMemberList() {
        return this.channel_type === "whatsapp" || super.hasMemberList;
    },
};

patch(DiscussChannel.prototype, threadPatch);
