from typing import TYPE_CHECKING, Any

from odoo import api, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.telegram.tools import keyboard as kb

if TYPE_CHECKING:
    from odoo.api import Environment

    from odoo.addons.approval.models.res_users import ResUsers
    from odoo.addons.sale.models.sale_order import SaleOrder
    from odoo.addons.telegram.models.telegram_bot import TelegramBot


class TelegramSaleConfirmNotifier(models.AbstractModel):
    _name = "telegram.sale.confirm.notifier"
    _description = "Telegram Sale Order Confirmation Notifier"

    @api.model
    def _notify_ready_to_confirm(self, order: SaleOrder) -> None:
        approval_notifier = self.env["telegram.approval.notifier"]
        if not approval_notifier._feature_active():
            return
        for user in order._get_telegram_confirm_users():
            chat = approval_notifier._target_chat(user, order.company_id)
            if not chat:
                continue
            env = approval_notifier._recipient_env(chat)
            chat.bot_id._queue_text(
                chat,
                self._format_message(order, env),
                reply_markup=self._prepare_keyboard(order, env),
                html=False,
            )

    @api.model
    def _confirm(
        self, order: SaleOrder, user: ResUsers, bot: TelegramBot
    ) -> str | None:
        env = self.env
        if user not in order._get_telegram_confirm_users():
            return env._("You are not set up to confirm this order.")
        company = order.company_id
        if company not in bot._served_companies(user):
            return env._("This bot does not act for %(company)s.") % {
                "company": company.name
            }
        if order.state != "draft":
            return env._("Order %(order)s is no longer a quotation.") % {
                "order": order.name
            }
        try:
            order.with_user(user).with_context(
                allowed_company_ids=company.ids
            ).action_confirm()
        except (AccessError, UserError) as exc:
            return str(exc)
        if order.state != "done":
            return env._("Order %(order)s could not be confirmed.") % {
                "order": order.name
            }
        return None

    @api.model
    def _format_message(self, order: SaleOrder, env: Environment) -> str:
        request = order.approval_request_id
        lines = [
            env._("📦 Sale order approved, ready to confirm"),
            env._("Order: %(order)s") % {"order": order.name},
            env._("Customer: %(customer)s") % {"customer": order.partner_id.name},
        ]
        if order.user_id:
            lines.append(env._("Salesperson: %(user)s") % {"user": order.user_id.name})
        lines.append(
            env._("Amount: %(amount)s")
            % {"amount": self._format_amount(order, order.amount_total)}
        )
        if request:
            lines.append(env._("Approval: %(request)s") % {"request": request.name})
        review = self._get_review_lines(order, env)
        if review:
            lines.append("")
            lines.extend(review)
        lines.append("")
        lines.append(env._("Confirm the order?"))
        return "\n".join(lines)

    @api.model
    def _get_review_lines(self, order: SaleOrder, env: Environment) -> list[str]:
        return []

    @api.model
    def _format_amount(self, order: SaleOrder, amount: float) -> str:
        return f"{order.currency_id.symbol or ''}{amount:,.2f}"

    @api.model
    def _prepare_keyboard(self, order: SaleOrder, env: Environment) -> dict[str, Any]:
        base_url = self.env.registry.settings.get(self.env, "web.base.url", False)
        open_row = []
        if base_url and base_url.startswith("https://"):
            open_row = [
                {
                    "text": env._("📄 Open in Odoo"),
                    "url": f"{base_url}/odoo/sale.order/{order.id}",
                }
            ]
        return kb.keyboard(
            [kb.button(env._("✅ Confirm order"), f"sc:c:{order.id}")], open_row
        )
