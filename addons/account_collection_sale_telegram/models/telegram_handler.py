from odoo import fields, models

from odoo.addons.account_collection_telegram.models.telegram_handler import (
    COLLECT,
    LIST_LIMIT,
)
from odoo.addons.telegram.tools import keyboard as kb


class TelegramHandlerAccountCollection(models.AbstractModel):
    _inherit = "telegram.handler.account_collection"

    def _cash_sales_to_collect(self, user, domain):
        orders = self.env["sale.order"].with_user(user)
        if not orders.has_access("read"):
            return orders
        return orders.search(
            [
                *domain,
                ("state", "=", "done"),
                ("invoice_state", "=", "to do"),
                ("payment_term_id.is_immediate", "=", True),
                ("company_id", "=", self.env.company.id),
            ],
            order="date_order, id",
        )

    def _find_customers(self, text, user):
        orders = self._cash_sales_to_collect(
            user,
            [
                "|",
                ("partner_id.commercial_partner_id.name", "ilike", text),
                ("partner_id.commercial_partner_id.vat", "ilike", text),
            ],
        )
        return (
            super()._find_customers(text, user)
            | orders.partner_id.commercial_partner_id
        )

    def _get_extra_collectable_rows(self, bot, chat, customer, user) -> tuple:
        rows, total = super()._get_extra_collectable_rows(bot, chat, customer, user)
        tr = self._tr(bot, chat)
        orders = self._cash_sales_to_collect(
            user, [("partner_id.commercial_partner_id", "=", customer.id)]
        )
        rows += [
            [
                kb.button(
                    kb.shorten(
                        tr._(
                            "Cash sale %(name)s · %(amount)s",
                            name=order.name,
                            amount=self._money(order.amount_total),
                        ),
                        60,
                    ),
                    f"{COLLECT}o:{order.id}",
                )
            ]
            for order in orders[:LIST_LIMIT]
        ]
        return rows, total + sum(orders.mapped("amount_total"))

    def _choose_cash_sale(self, bot, chat, value, user) -> None:
        data = self._flow_data(chat)
        order = self._cash_sales_to_collect(user, [("id", "=", int(value or 0))])
        if not order:
            self._send(
                bot, chat, self._tr(bot, chat)._("That sale is no longer to collect.")
            )
            return
        self._ask_collect_amount(
            bot,
            chat,
            user,
            {**data, "order_id": order.id, "invoice_ids": []},
            order.amount_total,
        )

    def _ask_collect_confirmation(self, bot, chat, user, data) -> None:
        if not data.get("order_id") or "hand_over" in data:
            super()._ask_collect_confirmation(bot, chat, user, data)
            return
        tr = self._tr(bot, chat)
        chat._flow_advance("collect_hand_over", data)
        self._send(
            bot,
            chat,
            tr._("Does the customer take the goods now?"),
            kb.keyboard(
                [
                    kb.button(tr._("Yes, now"), f"{COLLECT}h:1"),
                    kb.button(tr._("No, deliver later"), f"{COLLECT}h:0"),
                ]
            ),
        )

    def _set_collect_hand_over(self, bot, chat, user, hand_over) -> None:
        data = self._flow_data(chat)
        self._ask_collect_confirmation(
            bot, chat, user, {**data, "hand_over": hand_over}
        )

    def _get_callback_actions(self, bot, chat, value, internal_user) -> dict:
        return {
            **super()._get_callback_actions(bot, chat, value, internal_user),
            ("collect_invoice", "o"): lambda: self._choose_cash_sale(
                bot, chat, value, internal_user
            ),
            ("collect_hand_over", "h"): lambda: self._set_collect_hand_over(
                bot, chat, internal_user, value == "1"
            ),
        }

    def _describe_collectable(self, bot, chat, data) -> tuple:
        if not data.get("order_id"):
            return super()._describe_collectable(bot, chat, data)
        user = self._chat_internal_user(chat)
        order = self.env["sale.order"].with_user(user).browse(data["order_id"])
        tr = self._tr(bot, chat)
        return (
            order.partner_id.commercial_partner_id.name,
            tr._("Cash sale"),
            tr._("%(order)s, the customer takes the goods now", order=order.name)
            if data.get("hand_over")
            else order.name,
        )

    def _register_collection(self, data, user):
        if not data.get("order_id"):
            return super()._register_collection(data, user)
        return (
            self.env["sale.order"]
            .with_user(user)
            .with_privilege(
                "account_collection.privilege_register_collection",
                "account_collection_sale.privilege_invoice_cash_sale",
                "account_collection_sale.privilege_hand_over_cash_sale",
                reason="a collector invoices, collects and hands over a cash sale on "
                "the spot",
            )
            .browse(data["order_id"])
            ._settle_cash_sale(
                data["amount"],
                fields.Date.to_date(data["date"]),
                data["method"],
                user,
                check_date=fields.Date.to_date(data.get("check_date")),
                hand_over=bool(data.get("hand_over")),
            )
        )
