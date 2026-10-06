from odoo import models


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _notify_thread_by_ocn(self, message, recipients_data, msg_vals=False, **kwargs):
        icp_sudo = self.env["ir.config_parameter"].sudo()
        if not icp_sudo.get_param("odoo_ocn.project_id") or not icp_sudo.get_param_bool(
            "mail_mobile.enable_ocn"
        ):
            return None

        chat_channels = self.filtered(lambda channel: channel.channel_type == "chat")
        if chat_channels:
            channel_rdata = recipients_data.copy()
            channel_rdata += [
                {
                    "id": partner.id,
                    "share": partner.partner_share,
                    "active": partner.active,
                    "notif": "ocn",
                    "type": "customer",
                    "groups": [],
                }
                for partner in chat_channels.mapped("channel_partner_ids")
            ]
        else:
            channel_rdata = recipients_data

        return super()._notify_thread_by_ocn(
            message, channel_rdata, msg_vals=msg_vals, **kwargs
        )

    def _notify_by_ocn_prepare_payload(
        self, message, receiver_ids, msg_vals=False, force_record_name=False
    ):
        msg_vals = msg_vals or {}
        payload = super()._notify_by_ocn_prepare_payload(
            message,
            receiver_ids,
            msg_vals=msg_vals,
            force_record_name=force_record_name,
        )
        payload["action"] = "mail.action_discuss"
        record_name = force_record_name or message.record_name
        if self.channel_type == "chat":
            payload["subject"] = payload["author_name"]
            payload["type"] = "chat"
            payload["android_channel_id"] = "DirectMessage"
        elif self.channel_type == "channel":
            payload["subject"] = "#%s - %s" % (record_name, payload["author_name"])
            payload["android_channel_id"] = "ChannelMessage"
        else:
            payload["subject"] = "#%s" % (record_name)
        payload["model"] = "mail.channel"
        return payload
