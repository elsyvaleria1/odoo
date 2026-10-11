import logging

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.authority import keeping

_logger = logging.getLogger(__name__)


class DigestDigest(models.Model):
    _inherit = "digest.digest"

    telegram_enabled = fields.Boolean(
        default=False,
        help="Send digest reports via Telegram bot instead of email",
    )
    telegram_bot_id = fields.Many2one(
        comodel_name="telegram.bot",
        help="Override bot used for this digest. "
        "If not set, the bot that registered the user's chat is used automatically.",
    )
    telegram_send_mode = fields.Selection(
        selection=[
            ("replace", "Replace Email (Telegram Only)"),
            ("complement", "Complement Email (Both Telegram + Email)"),
        ],
        default="replace",
        help="Replace: Only send via Telegram. Complement: Send via both Telegram and Email.",
    )

    def _action_send_to_user(self, user, tips_count=1, consume_tips=True):
        if not self.telegram_enabled:
            return super()._action_send_to_user(user, tips_count, consume_tips)

        telegram_chat = self._get_user_telegram_chat(user)

        if not telegram_chat:
            _logger.warning(
                "User %s (%s) has no Telegram chat configured, "
                "skipping Telegram send for digest %s",
                user.name,
                user.login,
                self.name,
            )
            if self.telegram_send_mode == "complement":
                return super()._action_send_to_user(user, tips_count, consume_tips)
            return False

        bot = self.telegram_bot_id or telegram_chat.bot_id

        kpi_data = self._get_kpi_data(user.company_id, user)
        message = self._format_digest_for_telegram(kpi_data, user.company_id)

        try:
            response = bot.send_message(telegram_chat.chat_id, message)
            telegram_success = bool(response and response.get("ok", False))

            if telegram_success:
                _logger.info(
                    "Digest %s sent successfully to user %s via Telegram",
                    self.name,
                    user.name,
                )
            else:
                _logger.warning(
                    "Failed to send digest %s to user %s via Telegram: %s",
                    self.name,
                    user.name,
                    response,
                )

        except Exception:
            _logger.exception(
                "Exception sending digest %s to user %s via Telegram",
                self.name,
                user.name,
            )
            telegram_success = False

        if self.telegram_send_mode == "complement":
            super()._action_send_to_user(user, tips_count, consume_tips)
        elif telegram_success:
            if consume_tips:
                self._acquire_tips(
                    user.company_id, user, tips_count=tips_count, consumed=True
                )
        else:
            _logger.warning(
                "Telegram send failed for digest %s user %s, falling back to email",
                self.name,
                user.name,
            )
            return super()._action_send_to_user(user, tips_count, consume_tips)

        return telegram_success

    def action_test_telegram_send(self) -> dict:
        self.check_singleton()

        if not self.telegram_enabled:
            raise UserError(self.env._("Telegram is not enabled for this digest"))

        telegram_chat = self._get_user_telegram_chat(self.env.user)

        if not telegram_chat:
            raise UserError(
                self.env._(
                    "You do not have a Telegram chat configured. "
                    "Please link your Telegram account first in Telegram Bot menu."
                ),
            )

        bot = self.telegram_bot_id or telegram_chat.bot_id

        test_kpis = [
            {
                "kpi_name": "test",
                "kpi_fullname": "Test Message",
                "kpi_col1": {
                    "value": "123",
                    "margin": 5.5,
                    "col_subtitle": "Today",
                },
                "kpi_col2": {
                    "value": "117",
                    "margin": -2.3,
                    "col_subtitle": "Yesterday",
                },
            },
        ]

        message = self._format_digest_for_telegram(test_kpis, self.env.company)
        test_message = f"🧪 <b>TEST MESSAGE</b>\n\n{message}"
        response = bot.send_message(telegram_chat.chat_id, test_message)

        if response and response.get("ok"):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": self.env._("Success"),
                    "message": self.env._(
                        "Test message sent successfully to your Telegram!"
                    ),
                    "type": "success",
                    "sticky": False,
                },
            }

        error_msg = (
            response.get("description", "Unknown error")
            if response
            else "No response from Telegram"
        )
        raise UserError(
            self.env._(
                "Failed to send test message: %s\n\n"
                "Check bot configuration and ensure you have a Telegram chat linked.",
                error_msg,
            ),
        )

    def _get_user_telegram_chat(self, user):
        chats = self.env["telegram.chat"]._for_user(user, self.telegram_bot_id or None)
        return chats.filtered(
            lambda chat: (
                user.company_id in keeping(chat.bot_id).company_ids
                and not keeping(chat.bot_id).moved_to_id
            )
        )[:1]

    def _format_kpi_for_telegram(self, kpi) -> str:
        lines = [tg.bold(kpi["kpi_fullname"])]

        for col_num in [1, 2, 3]:
            col_key = f"kpi_col{col_num}"
            if col_key not in kpi or not kpi[col_key]:
                continue

            col_data = kpi[col_key]
            subtitle = col_data.get("col_subtitle", "")
            value = col_data.get("value", "0")
            margin = col_data.get("margin", 0)

            if margin > 0:
                margin_str = f"↑ +{margin:.1f}%"
            elif margin < 0:
                margin_str = f"↓ {margin:.1f}%"
            else:
                margin_str = "→ 0.0%"

            lines.append(f"  {tg.escape(subtitle)}: {tg.escape(value)} {margin_str}")

        return "\n".join(lines)

    def _format_digest_for_telegram(self, kpis, company) -> str:
        lines = [
            tg.bold(self.name),
            tg.italic(company.name),
            f"📅 {fields.Date.today().strftime('%Y-%m-%d')}",
            "",
        ]

        for kpi in kpis:
            lines.append(self._format_kpi_for_telegram(kpi))
            lines.append("")

        lines.append("—")
        lines.append(tg.escape(self.env._("Generated by Odoo Digest")))

        return "\n".join(lines)
