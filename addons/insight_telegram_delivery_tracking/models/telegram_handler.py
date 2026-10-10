import re

from odoo import fields, models
from odoo.exceptions import AccessError
from odoo.tools.translate import LazyTranslate

from odoo.addons.insight_telegram.models.telegram_chat import _chunks
from odoo.addons.insight_telegram.services import catalog
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.dispatch import TelegramCommand

_lt = LazyTranslate(__name__)
REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{5,63}")


class TelegramHandlerDeliveryTracking(models.AbstractModel):
    """Let linked employees read their accessible shipments by tracking number."""

    _name = "telegram.handler.delivery_tracking"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Carrier Tracking"

    def _telegram_commands(self) -> dict:
        return {
            "/rastreo": TelegramCommand(
                "_handle_tracking_command",
                access=("stock.picking", "read"),
                description=_lt("Check a shipment by its tracking number"),
            ),
        }

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        return bool(chat and chat.chat_type == "private")

    def _handle_tracking_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = self._tr(bot, chat)
        if len(args) != 1 or not REFERENCE.fullmatch(args[0]):
            bot.send_message(
                chat.chat_id,
                tr_env._("Send one complete tracking number: %(example)s")
                % {"example": tg.code("/rastreo TOL01583026")},
            )
            return
        # Keep the router's company scope and language, but explicitly discard
        # superuser mode before reading any shipment.
        reader = self.with_user(internal_user).with_context(lang=tr_env.lang)
        try:
            text = catalog.answer(
                reader.env,
                catalog.QUERIES["tracking"],
                {"reference": args[0]},
                tz=internal_user.tz or "America/Mexico_City",
                today=fields.Date.context_today(reader),
            )
        except AccessError:
            bot.send_message(
                chat.chat_id,
                tr_env._("You do not have permission to consult these shipments."),
            )
            return
        for chunk in _chunks(text):
            bot.send_message(chat.chat_id, chunk)

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._offers_command(bot, chat, "/rastreo", partner, internal_user):
            return []
        tr_env = self._tr(bot, chat)
        return [
            (
                tr_env._("Shipment tracking"),
                [
                    tr_env._("%(command)s — check the saved status and its read date.")
                    % {"command": tg.code("/rastreo TOL01583026")},
                ],
            ),
        ]
