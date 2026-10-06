from odoo import models
from odoo.libs.debug_log import DebugLog

from .mail_bot import ODOOBOT_XMLID

_debug = DebugLog(__name__)


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def execute_command_help(self, **kwargs) -> None:
        super().execute_command_help(**kwargs)
        self.env["mail.bot"]._apply_logic(self, kwargs, command="help")

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        if self._is_chat_with_odoobot(message):
            _debug.logic("odoobot_answering", channel=self.id, message=message.id)
            self.env["mail.bot"]._apply_logic(
                self,
                {
                    "author_id": message.author_id.id,
                    "message_type": message.message_type,
                    "body": message.body,
                    "partner_ids": message.partner_ids.ids,
                    "attachment_ids": message.attachment_ids.ids,
                },
            )
        return message

    def _is_chat_with_odoobot(self, message) -> bool:
        if self.channel_type != "chat" or message.message_type != "comment":
            return False
        odoobot_id = self.env["ir.model.data"]._xmlid_to_res_id(ODOOBOT_XMLID)
        if message.author_id.id == odoobot_id:
            return False
        return bool(
            self.env["discuss.channel.member"].search_count(
                [("channel_id", "=", self.id), ("partner_id", "=", odoobot_id)],
                limit=1,
            )
        )
