import re
import secrets
from decimal import Decimal

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import format_amount, format_datetime
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import keeping
from odoo.addons.telegram.tools.dispatch import TelegramCommand

_lt = LazyTranslate(__name__)
PREFIX = "wal:"
PAGE_SIZE = 8
AMOUNT = re.compile(r"[0-9]{1,12}(?:[.,][0-9]{1,6})?")


class TelegramHandlerWallet(models.AbstractModel):
    """Let verified cardholders consult balances and request approval of top-ups."""

    _name = "telegram.handler.wallet"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Wallet Balances and Top-up Requests"

    def _telegram_commands(self) -> dict:
        return {
            "/saldo": TelegramCommand(
                "_handle_balance_command",
                starts_flow=True,
                description=_lt("Check your card or TAG balance"),
                company="choose",
            ),
            "/recarga": TelegramCommand(
                "_handle_topup_command",
                starts_flow=True,
                access=("approval.request", "create"),
                description=_lt("Request a card or TAG top-up"),
                company="choose",
            ),
        }

    def _telegram_callback_prefixes(self):
        return (PREFIX,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("a wallet consultation or top-up request")

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        return bool(chat and chat.chat_type == "private")

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        bot.send_message(
            chat.chat_id,
            self._tr(bot, chat)._(
                "Use these commands in a private chat linked to your active Odoo user."
            ),
        )

    def _cards(self, bot, user):
        cards = (
            self.env["wallet.card"]
            .with_user(user)
            .with_context(allowed_company_ids=bot._acting_company().ids)
            .with_privilege(
                "wallet_telegram.privilege_read_own_wallet",
                reason="a linked Telegram user reads their own cards and dated balances",
            )
        )
        return cards.search(
            [
                ("holder_id", "=", user.partner_id.id),
                ("active", "=", True),
                ("account_id.active", "=", True),
                ("account_id", "in", keeping(bot).wallet_account_ids.ids),
                ("company_id", "=", bot._acting_company().id),
            ],
            order="number, id",
        )

    def _handle_balance_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        self._start(bot, chat, internal_user, "/saldo")

    def _handle_topup_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        self._start(bot, chat, internal_user, "/recarga")

    def _start(self, bot, chat, user, command) -> None:
        cards = self._cards(bot, user)
        if not cards:
            bot.send_message(
                chat.chat_id,
                self._tr(bot, chat)._(
                    "You have no active card or TAG assigned here. Ask the wallet manager to set you as its holder."
                ),
            )
            return
        self._flow_start(
            chat,
            "card",
            {
                "command": command,
                "nonce": secrets.token_hex(8),
                "user_id": user.id,
            },
        )
        if len(cards) == 1:
            self._select_card(bot, chat, cards, user)
        else:
            self._show_cards(bot, chat, cards)

    def _show_cards(self, bot, chat, cards, page=0) -> None:
        page = max(0, min(page, (len(cards) - 1) // PAGE_SIZE))
        nonce = self._flow_data(chat)["nonce"]
        tr = self._tr(bot, chat)
        trailing = []
        if page:
            trailing.append(kb.button(tr._("Previous"), f"wal:{nonce}:page:{page - 1}"))
        if (page + 1) * PAGE_SIZE < len(cards):
            trailing.append(kb.button(tr._("Next"), f"wal:{nonce}:page:{page + 1}"))
        bot.send_message(
            chat.chat_id,
            tr._("Choose your card or TAG. /cancelar stops this request."),
            reply_markup=kb.record_list(
                cards[page * PAGE_SIZE : (page + 1) * PAGE_SIZE],
                lambda card: f"{card.account_id.name} · {card.number}",
                lambda card: f"wal:{nonce}:card:{card.id}",
                width=60,
                trailing=trailing,
            ),
        )

    def _balance_text(self, bot, chat, card, user) -> str:
        tr = self._tr(bot, chat)
        title = tr._("Card/TAG: %(card)s") % {"card": tg.bold(card.number)}
        if not card.date_balance:
            return (
                title
                + "\n"
                + tr._(
                    "No issuer balance has been read yet. This does not mean the balance is zero."
                )
            )
        return (
            title
            + "\n"
            + tr._(
                "Last consultation: %(date)s\nRecorded balance: %(amount)s\nThe balance may have changed since that consultation."
            )
            % {
                "date": tg.escape(
                    format_datetime(
                        tr, card.date_balance, tz=user.tz or card.account_id.tz
                    )
                ),
                "amount": tg.escape(
                    format_amount(tr, card.amount_balance, card.currency_id)
                ),
            }
        )

    def _select_card(self, bot, chat, card, user) -> None:
        data = self._flow_data(chat)
        bot.send_message(chat.chat_id, self._balance_text(bot, chat, card, user))
        if data["command"] == "/saldo":
            self._flow_end(chat)
            return
        category = card.account_id.telegram_topup_category_id
        if not category or not category.active:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                self._tr(bot, chat)._(
                    "Top-up requests are not configured for this account. Ask the wallet manager to configure its approval category."
                ),
            )
            return
        chat._flow_advance(
            step="amount",
            data={
                **data,
                "card_id": card.id,
                "category_id": category.id,
            },
        )
        bot.send_message(
            chat.chat_id,
            self._tr(bot, chat)._(
                "How much do you need in %(currency)s? Enter a positive amount without thousands separators, for example 500.00."
            )
            % {"currency": tg.escape(card.currency_id.name)},
        )

    def _current_card(self, bot, chat, user):
        data = self._flow_data(chat)
        return self._cards(bot, user).filtered(
            lambda card: card.id == data.get("card_id")
        )

    def _flow_permitted(self, bot, chat, partner, user) -> bool:
        data = self._flow_data(chat)
        return bool(
            user
            and user.active
            and data.get("user_id") == user.id
            and self._offers_command(bot, chat, data.get("command"), partner, user)
        )

    def _unavailable(self, bot, chat, *, end=True) -> None:
        if end:
            self._flow_end(chat)
        bot.send_message(
            chat.chat_id,
            self._tr(bot, chat)._(
                "This selection is no longer available. Start again with /saldo or /recarga."
            ),
        )

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        parts = (callback_query.get("data") or "").split(":")
        if parts[0] != "wal":
            return False
        bot.answer_callback_query(callback_query.get("id"))
        data = self._flow_data(chat)
        if len(parts) not in (3, 4) or parts[1] != data.get("nonce"):
            self._unavailable(bot, chat, end=False)
            return True
        if not self._flow_permitted(bot, chat, partner, internal_user):
            self._unavailable(bot, chat)
            return True
        action = parts[2]
        step = self._flow_step(chat)
        if action == "cancel":
            self._flow_end(chat)
            self._clear_keyboard(bot, chat, callback_query)
            bot.send_message(
                chat.chat_id, self._tr(bot, chat)._("Top-up request cancelled.")
            )
        elif (
            step == "card"
            and action in ("card", "page")
            and len(parts) == 4
            and parts[3].isascii()
            and parts[3].isdecimal()
        ):
            cards = self._cards(bot, internal_user)
            self._clear_keyboard(bot, chat, callback_query)
            if action == "page" and cards:
                self._show_cards(bot, chat, cards, int(parts[3]))
            else:
                card = cards.filtered(lambda card: card.id == int(parts[3]))
                if card:
                    self._select_card(bot, chat, card, internal_user)
                else:
                    self._unavailable(bot, chat)
        elif step == "confirm" and action == "confirm":
            self._submit(bot, chat, internal_user)
            self._clear_keyboard(bot, chat, callback_query)
        return True

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if not step:
            return False
        if not self._flow_permitted(bot, chat, partner, internal_user):
            self._unavailable(bot, chat)
            return True
        if step not in ("amount", "reason"):
            bot.send_message(
                chat.chat_id,
                self._tr(bot, chat)._("Use the buttons above, or /cancelar."),
            )
            return True
        card = self._current_card(bot, chat, internal_user)
        if not card:
            self._unavailable(bot, chat)
            return True
        text = (message.get("text") or "").strip()
        data = self._flow_data(chat)
        tr = self._tr(bot, chat)
        if step == "amount":
            amount = (
                Decimal(text.replace(",", "."))
                if AMOUNT.fullmatch(text)
                else Decimal(0)
            )
            if amount <= 0 or amount % Decimal(str(card.currency_id.rounding)):
                bot.send_message(
                    chat.chat_id,
                    tr._(
                        "Enter a positive amount using the currency's decimal precision, without thousands separators."
                    ),
                )
                return True
            chat._flow_advance(step="reason", data={**data, "amount": str(amount)})
            bot.send_message(
                chat.chat_id,
                tr._("What is the top-up for? Enter a reason of up to 500 characters."),
            )
        elif not text or len(text) > 500:
            bot.send_message(
                chat.chat_id, tr._("Enter a reason between 1 and 500 characters.")
            )
        else:
            data = {**data, "reason": text}
            chat._flow_advance(step="confirm", data=data)
            bot.send_message(
                chat.chat_id,
                tr._(
                    "Request a top-up of %(amount)s for %(card)s?\nReason: %(reason)s\nThis sends a request for approval; it does not reload the card."
                )
                % {
                    "amount": tg.escape(
                        format_amount(tr, float(data["amount"]), card.currency_id)
                    ),
                    "card": tg.bold(card.number),
                    "reason": tg.escape(text),
                },
                reply_markup=kb.confirm_cancel(
                    tr._("Send request"),
                    f"wal:{data['nonce']}:confirm",
                    tr._("Cancel"),
                    f"wal:{data['nonce']}:cancel",
                ),
            )
        return True

    def _submit(self, bot, chat, user) -> None:
        card = self._current_card(bot, chat, user)
        data = self._flow_data(chat)
        if (
            not card
            or not card.account_id.telegram_topup_category_id.active
            or card.account_id.telegram_topup_category_id.id != data["category_id"]
        ):
            self._unavailable(bot, chat)
            return
        tr = self._tr(bot, chat)
        requests = (
            self.env["approval.request"]
            .with_user(user)
            .with_context(allowed_company_ids=card.company_id.ids)
        )
        try:
            with self.env.cr.savepoint():
                request = requests.create(
                    {
                        "category_id": data["category_id"],
                        "request_owner_id": user.id,
                        "company_id": card.company_id.id,
                        "currency_id": card.currency_id.id,
                        "amount": float(data["amount"]),
                        "date": fields.Datetime.now(),
                        "reason": Markup("<p>%s</p><p>%s</p><p>%s</p>")
                        % (
                            tr._("Wallet: %(account)s")
                            % {"account": card.account_id.name},
                            tr._("Card/TAG: %(card)s") % {"card": card.number},
                            data["reason"],
                        ),
                        "telegram_data": {
                            "product_reference": card.number,
                            "company": card.company_id.name,
                            "amount": data["amount"],
                        },
                    }
                )
                request.action_confirm()
        except UserError as exc:
            self._flow_end(chat)
            bot.send_message(
                chat.chat_id,
                tr._(
                    "The request could not be submitted: %(error)s. Start again with /recarga."
                )
                % {"error": tg.escape(exc)},
            )
            return
        self._flow_end(chat)
        bot.send_message(
            chat.chat_id,
            tr._(
                "Request %(request)s submitted for approval. The card has not been reloaded."
            )
            % {"request": tg.bold(request.name)},
        )

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        tr = self._tr(bot, chat)
        lines = {
            "/saldo": tr._("/saldo - View the last dated balance of your card or TAG."),
            "/recarga": tr._(
                "/recarga - Request approval of a top-up for your card or TAG."
            ),
        }
        offered = [
            text
            for command, text in lines.items()
            if self._offers_command(bot, chat, command, partner, internal_user)
        ]
        return [(tr._("Wallets"), offered)] if offered else []
