import logging
import re
from datetime import datetime, timedelta

from odoo import Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import TelegramCommand, log_command_execution

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)
_COLLECTOR = ("account.collection.remittance", "create")

COLLECT = "cob:"
REMIT = "rem:"
LIST_LIMIT = 8
MAX_DAYS_BACK = 31
PROOF_MIMETYPES = ("application/pdf", "image/jpeg", "image/png", "image/webp")
_AMOUNT = re.compile(r"^\d+(\.\d{1,2})?$")


def _parse_amount(text):
    cleaned = (text or "").replace("$", "").replace(" ", "").strip()
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") == 1 and len(cleaned.rsplit(",", 1)[1]) in (1, 2):
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    if not _AMOUNT.match(cleaned):
        return None
    amount = float(cleaned)
    return amount if amount > 0 else None


def _parse_date(text):
    for pattern in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime((text or "").strip(), pattern).date()
        except ValueError:
            continue
    return None


class TelegramHandlerAccountCollection(models.AbstractModel):
    _name = "telegram.handler.account_collection"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Field Collections"

    def _telegram_commands(self) -> dict:
        return {
            "/cobro": TelegramCommand(
                "_handle_collect_command",
                "internal",
                starts_flow=True,
                access=_COLLECTOR,
                description=_lt("Record what a customer paid you"),
                company="choose",
            ),
            "/custodia": TelegramCommand(
                "_handle_custody_command",
                "internal",
                access=_COLLECTOR,
                description=_lt("See the collections you still hold"),
                company="choose",
            ),
            "/rendir": TelegramCommand(
                "_handle_remit_command",
                "internal",
                starts_flow=True,
                access=_COLLECTOR,
                description=_lt("Hand your collections in"),
                company="choose",
            ),
        }

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        self._refuse_non_collector(bot, chat, internal_user)

    def _telegram_callback_prefixes(self):
        return (COLLECT, REMIT)

    def _telegram_flow_label(self, bot, chat):
        tr = self._tr(bot, chat)
        if (self._flow_step(chat) or "").startswith("remit_"):
            return tr._("a hand-in")
        return tr._("a collection")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        offered = {
            command
            for command in self._telegram_commands()
            if self._offers_command(bot, chat, command, partner, internal_user)
        }
        if not offered:
            return []
        tr = self._tr(bot, chat)
        lines = []
        if "/cobro" in offered:
            lines.append(
                tr._("%(command)s - Record what a customer paid you.")
                % {"command": tg.bold("/cobro")}
            )
        if "/custodia" in offered:
            lines.append(
                tr._("%(command)s - See the collections you still hold.")
                % {"command": tg.bold("/custodia")}
            )
        if "/rendir" in offered:
            lines.append(
                tr._("%(command)s - Hand your collections in to a till or the bank.")
                % {"command": tg.bold("/rendir")}
            )
        return [(tr._("Field Collections"), lines)]

    def _send(self, bot, chat, text, markup=None) -> None:
        bot.send_message(chat.chat_id, text, reply_markup=markup)

    def _is_collector(self, user) -> bool:
        return bool(user) and self.env["account.collection.remittance"].with_user(
            user
        ).has_access("create")

    def _refuse_non_collector(self, bot, chat, user) -> bool:
        if self._is_collector(user):
            return False
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Only collectors record collections here. Ask your manager to "
                "make you a collector."
            ),
        )
        return True

    def _warn_custody(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        collector = user.with_user(user)
        status = collector._get_custody_status(self.env.company)
        if status["overdue_count"]:
            self._send(
                bot,
                chat,
                tr._(
                    "Heads up: %(amount)s of what you hold is past its hand-in date. "
                    "Hand it in today with /rendir."
                )
                % {"amount": tg.bold(self._money(status["overdue_amount"]))},
            )
        elif status["over_limit"]:
            self._send(
                bot,
                chat,
                tr._(
                    "Heads up: you hold %(amount)s, at or above your limit of "
                    "%(limit)s. Hand it in with /rendir before collecting more."
                )
                % {
                    "amount": tg.bold(self._money(status["amount"])),
                    "limit": tg.bold(self._money(status["limit"])),
                },
            )

    def _money(self, amount) -> str:
        return self.env.company.currency_id.format(amount)

    def _held_payments(self, user):
        return (
            self.env["account.payment"]
            .with_user(user)
            .search(
                [
                    ("collector_id", "=", user.id),
                    ("company_id", "=", self.env.company.id),
                    ("is_in_custody", "=", True),
                ],
                order="date, id",
            )
        )

    def _privileged_moves(self):
        return self.env["account.move"].with_privilege(
            "account_collection.privilege_register_collection",
            reason="a collector looks up the open invoices of the customer who paid them",
        )

    def _open_invoices_domain(self):
        return [
            ("move_type", "in", ("out_invoice", "out_receipt")),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("company_id", "=", self.env.company.id),
            ("currency_id", "=", self.env.company.currency_id.id),
        ]

    def _first_file(self, message):
        if photos := message.get("photo"):
            return {"file_id": photos[-1]["file_id"], "mimetype": "image/jpeg"}
        document = message.get("document") or {}
        if document.get("mime_type") in PROOF_MIMETYPES:
            return {"file_id": document["file_id"], "mimetype": document["mime_type"]}
        return None

    def _download_proof(self, bot, data, name):
        if not data.get("proof_file_id"):
            return []
        content = bot.get_file_content(data["proof_file_id"])
        if not content:
            return []
        extension = {
            "application/pdf": "pdf",
            "image/png": "png",
            "image/webp": "webp",
        }.get(data.get("proof_mimetype"), "jpg")
        return [(f"{name}.{extension}", content)]

    @log_command_execution
    def _handle_collect_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        if self._refuse_non_collector(bot, chat, internal_user):
            return
        if not self.env["account.move"]._get_collection_journal():
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._(
                    "Your company has no journal for collections in custody yet; "
                    "ask accounting to set one up."
                ),
            )
            return
        self._flow_start(chat, "collect_customer", {})
        self._warn_custody(bot, chat, internal_user)
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Who paid you? Send the customer's name, part of it, or their tax "
                "ID.\n\n/cancelar stops at any time."
            ),
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if not step:
            return False
        text = (message.get("text") or "").strip()
        handlers = self._get_message_steps()
        if step in handlers:
            handlers[step](bot, chat, message, text, internal_user)
            return True
        self._send(bot, chat, self._tr(bot, chat)._("Use the buttons above, please."))
        return True

    def _get_message_steps(self) -> dict:
        return {
            "collect_customer": self._read_customer,
            "collect_amount": self._read_collect_amount,
            "collect_date": self._read_collect_date,
            "collect_check_date": self._read_collect_check_date,
            "collect_proof": self._read_collect_proof,
            "collect_location": self._read_collect_location,
            "remit_amount": self._read_remit_amount,
            "remit_slip": self._read_remit_slip,
        }

    def _read_customer(self, bot, chat, message, text, user) -> None:
        tr = self._tr(bot, chat)
        if len(text) < 3:
            self._send(bot, chat, tr._("Send at least three letters of the name."))
            return
        customers = self._find_customers(text, user)
        if not customers:
            self._send(
                bot,
                chat,
                tr._("No customer matching %(query)s owes anything. Try another name.")
                % {"query": tg.bold(text)},
            )
            return
        if len(customers) == 1:
            self._offer_collectables(bot, chat, customers, user)
            return
        self._send(
            bot,
            chat,
            tr._("Which customer?"),
            kb.record_list(
                customers.sorted("name"),
                lambda customer: customer.name,
                lambda customer: f"{COLLECT}p:{customer.id}",
                limit=LIST_LIMIT,
                width=48,
            ),
        )

    def _find_customers(self, text, user):
        invoices = self._privileged_moves().search(
            [
                *self._open_invoices_domain(),
                "|",
                ("commercial_partner_id.name", "ilike", text),
                ("commercial_partner_id.vat", "ilike", text),
            ]
        )
        return invoices.commercial_partner_id

    def _get_extra_collectable_rows(self, bot, chat, customer, user) -> tuple:
        return [], 0.0

    def _customer_invoices(self, customer, user):
        return self._privileged_moves().search(
            [
                *self._open_invoices_domain(),
                ("commercial_partner_id", "=", customer.id),
            ],
            order="invoice_date_due, id",
        )

    def _offer_collectables(self, bot, chat, customer, user) -> None:
        tr = self._tr(bot, chat)
        invoices = self._customer_invoices(customer, user)
        extra_rows, extra_total = self._get_extra_collectable_rows(
            bot, chat, customer, user
        )
        if not invoices and not extra_rows:
            self._send(bot, chat, tr._("That customer owes nothing now."))
            return
        chat._flow_advance("collect_invoice", {"customer_id": customer.id})
        invoices_total = sum(invoices.mapped("amount_residual"))
        rows = [
            [
                kb.button(
                    kb.shorten(
                        tr._(
                            "%(name)s · due %(due)s · %(amount)s",
                            name=invoice.name,
                            due=invoice.invoice_date_due.strftime("%d/%m/%y")
                            if invoice.invoice_date_due
                            else "-",
                            amount=self._money(invoice.amount_residual),
                        ),
                        60,
                    ),
                    f"{COLLECT}i:{invoice.id}",
                )
            ]
            for invoice in invoices[:LIST_LIMIT]
        ]
        if invoices:
            rows.append(
                [
                    kb.button(
                        tr._(
                            "All, oldest first (%(total)s)",
                            total=self._money(invoices_total),
                        ),
                        f"{COLLECT}i:all",
                    )
                ]
            )
        rows.extend(extra_rows)
        self._send(
            bot,
            chat,
            tr._("%(customer)s owes %(total)s. Which invoice did they pay?")
            % {
                "customer": tg.bold(customer.name),
                "total": tg.bold(self._money(invoices_total + extra_total)),
            },
            kb.keyboard(*rows),
        )

    def _choose_invoices(self, bot, chat, choice, user) -> None:
        data = self._flow_data(chat)
        customer = self.env["res.partner"].browse(data.get("customer_id"))
        invoices = self._customer_invoices(customer, user)
        if choice != "all":
            invoices = invoices.filtered(lambda invoice: str(invoice.id) == choice)
        if not invoices:
            self._send(
                bot, chat, self._tr(bot, chat)._("That invoice is no longer open.")
            )
            return
        self._ask_collect_amount(
            bot,
            chat,
            user,
            {**data, "invoice_ids": invoices.ids},
            sum(invoices.mapped("amount_residual")),
        )

    def _ask_collect_amount(self, bot, chat, user, data, due) -> None:
        tr = self._tr(bot, chat)
        chat._flow_advance("collect_amount", {**data, "due": due})
        self._send(
            bot,
            chat,
            tr._(
                "How much did they pay? Send the amount, or press the button for "
                "the full %(due)s."
            )
            % {"due": tg.bold(self._money(due))},
            kb.single(tr._("Full %(due)s", due=self._money(due)), f"{COLLECT}a"),
        )

    def _read_collect_amount(self, bot, chat, message, text, user) -> None:
        amount = _parse_amount(text)
        if amount is None:
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._("Send the amount as a number, like 1500.50."),
            )
            return
        self._set_collect_amount(bot, chat, amount, user)

    def _set_collect_amount(self, bot, chat, amount, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        currency = self.env.company.currency_id
        if currency.compare_amounts(amount, data["due"]) > 0:
            self._send(
                bot,
                chat,
                tr._(
                    "That is more than the %(due)s owed. Record the rest at the "
                    "office, or send the amount owed."
                )
                % {"due": tg.bold(self._money(data["due"]))},
            )
            return
        chat._flow_advance("collect_method", {**data, "amount": amount})
        self._send(
            bot,
            chat,
            tr._("How did they pay?"),
            kb.keyboard(
                [
                    kb.button(tr._("Cash"), f"{COLLECT}m:cash"),
                    kb.button(tr._("Check"), f"{COLLECT}m:check"),
                ]
            ),
        )

    def _set_collect_method(self, bot, chat, method) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        chat._flow_advance("collect_date", {**data, "method": method})
        self._send(
            bot,
            chat,
            tr._(
                "When did they pay you? Press a button or send the date as dd/mm/yyyy."
            ),
            kb.keyboard(
                [
                    kb.button(tr._("Today"), f"{COLLECT}d:0"),
                    kb.button(tr._("Yesterday"), f"{COLLECT}d:1"),
                ]
            ),
        )

    def _read_collect_date(self, bot, chat, message, text, user) -> None:
        paid_on = _parse_date(text)
        if not paid_on:
            self._send(bot, chat, self._tr(bot, chat)._("Send the date as dd/mm/yyyy."))
            return
        self._set_collect_date(bot, chat, paid_on)

    def _set_collect_date(self, bot, chat, paid_on) -> None:
        tr = self._tr(bot, chat)
        today = fields.Date.context_today(self)
        if paid_on > today or paid_on < today - timedelta(days=MAX_DAYS_BACK):
            self._send(
                bot,
                chat,
                tr._(
                    "The date must be today or within the last %(days)s days.",
                    days=MAX_DAYS_BACK,
                ),
            )
            return
        data = self._flow_data(chat)
        if data["method"] == "check":
            chat._flow_advance(
                "collect_check_date", {**data, "date": paid_on.isoformat()}
            )
            self._send(
                bot,
                chat,
                tr._(
                    "What date is written on the check? Press the button if it is "
                    "the day they paid you, or send the date as dd/mm/yyyy."
                ),
                kb.single(tr._("Same day"), f"{COLLECT}k"),
            )
            return
        chat._flow_advance("collect_proof", {**data, "date": paid_on.isoformat()})
        self._send(
            bot,
            chat,
            tr._("Send a photo of the receipt you gave the customer, or skip it."),
            kb.single(tr._("Skip"), f"{COLLECT}x"),
        )

    def _read_collect_check_date(self, bot, chat, message, text, user) -> None:
        check_date = _parse_date(text)
        if not check_date:
            self._send(bot, chat, self._tr(bot, chat)._("Send the date as dd/mm/yyyy."))
            return
        self._set_collect_check_date(bot, chat, check_date)

    def _set_collect_check_date(self, bot, chat, check_date) -> None:
        data = self._flow_data(chat)
        chat._flow_advance(
            "collect_proof", {**data, "check_date": check_date.isoformat()}
        )
        self._send(bot, chat, self._tr(bot, chat)._("Send a photo of the check."))

    def _read_collect_proof(self, bot, chat, message, text, user) -> None:
        proof = self._first_file(message)
        if not proof:
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._("Send a photo or a PDF, please."),
            )
            return
        data = self._flow_data(chat)
        self._ask_collect_location(
            bot,
            chat,
            {
                **data,
                "proof_file_id": proof["file_id"],
                "proof_mimetype": proof["mimetype"],
            },
        )

    def _ask_collect_location(self, bot, chat, data) -> None:
        tr = self._tr(bot, chat)
        chat._flow_advance("collect_location", data)
        self._send(
            bot,
            chat,
            tr._(
                "Share where you are with the button below, so the collection "
                "records where it was made, or skip it."
            ),
            {
                "keyboard": [
                    [{"text": tr._("Share my location"), "request_location": True}],
                    [{"text": tr._("Skip")}],
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    def _read_collect_location(self, bot, chat, message, text, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        location = message.get("location")
        if location:
            data = {
                **data,
                "latitude": location["latitude"],
                "longitude": location["longitude"],
            }
        elif text != tr._("Skip"):
            self._send(
                bot,
                chat,
                tr._("Press the button to share your location, or Skip."),
            )
            return
        self._send(
            bot,
            chat,
            tr._("Location received.") if location else tr._("No location."),
            {"remove_keyboard": True},
        )
        self._ask_collect_confirmation(bot, chat, user, data)

    def _ask_collect_confirmation(self, bot, chat, user, data) -> None:
        tr = self._tr(bot, chat)
        chat._flow_advance("collect_confirm", data)
        customer, label, names = self._describe_collectable(bot, chat, data)
        method = {"cash": tr._("Cash"), "check": tr._("Check")}[data["method"]]
        lines = [
            tr._("Record this collection?"),
            "",
            f"{tg.bold(tr._('Customer'))}: {tg.escape(customer)}",
            f"{tg.bold(label)}: {tg.escape(names)}",
            f"{tg.bold(tr._('Amount'))}: {tg.escape(self._money(data['amount']))}",
            f"{tg.bold(tr._('Paid in'))}: {tg.escape(method)}",
            f"{tg.bold(tr._('Paid on'))}: {tg.escape(fields.Date.to_date(data['date']).strftime('%d/%m/%Y'))}",
            *(
                [
                    f"{tg.bold(tr._('Check date'))}: {tg.escape(fields.Date.to_date(data['check_date']).strftime('%d/%m/%Y'))}"
                ]
                if data.get("check_date")
                else []
            ),
            f"{tg.bold(tr._('Proof'))}: {tg.escape(tr._('attached') if data.get('proof_file_id') else tr._('none'))}",
            f"{tg.bold(tr._('Location'))}: {tg.escape(tr._('shared') if 'latitude' in data else tr._('none'))}",
        ]
        self._send(
            bot,
            chat,
            "\n".join(lines),
            kb.confirm_cancel(
                tr._("Confirm"), f"{COLLECT}ok", tr._("Cancel"), f"{COLLECT}no"
            ),
        )

    def _describe_collectable(self, bot, chat, data) -> tuple:
        invoices = (
            self.env["account.move"]
            .with_privilege(
                "account_collection.privilege_register_collection",
                reason="a collector reviews the invoices their collection settles",
            )
            .browse(data["invoice_ids"])
        )
        return (
            invoices.commercial_partner_id.name,
            self._tr(bot, chat)._("Invoices"),
            ", ".join(invoices.mapped("name")),
        )

    def _register_collection(self, data, user):
        invoices = (
            self.env["account.move"]
            .with_privilege(
                "account_collection.privilege_register_collection",
                reason="a collector records the payment a customer handed them",
            )
            .browse(data["invoice_ids"])
        )
        return invoices._create_collection_payment(
            data["amount"],
            fields.Date.to_date(data["date"]),
            data["method"],
            user,
            check_date=fields.Date.to_date(data.get("check_date")),
        )

    def _confirm_collection(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        try:
            payment = self._register_collection(data, user)
            if "latitude" in data:
                payment.write(
                    {
                        "collection_latitude": data["latitude"],
                        "collection_longitude": data["longitude"],
                    }
                )
            if attachments := self._download_proof(bot, data, payment.name):
                payment.message_post(
                    body=tr._("Proof of the collection, sent from Telegram."),
                    attachments=attachments,
                )
        except (UserError, ValidationError, AccessError) as error:
            self._flow_end(chat)
            self._send(
                bot,
                chat,
                tr._("The collection was not recorded: %(reason)s")
                % {"reason": tg.escape(str(error))},
            )
            return
        self._flow_end(chat)
        channels = self._send_receipt_to_customer(bot, chat, payment)
        held = self._held_payments(user)
        self._send(
            bot,
            chat,
            tr._(
                "Collection %(name)s recorded: %(amount)s. You now hold %(held)s in "
                "%(count)s collections; hand them in with /rendir."
            )
            % {
                "name": tg.bold(payment.name),
                "amount": tg.bold(self._money(payment.amount)),
                "held": tg.bold(self._money(sum(held.mapped("amount")))),
                "count": len(held),
            },
        )
        self._tell_customer_reach(bot, chat, payment, channels)

    def _tell_customer_reach(self, bot, chat, payment, channels) -> None:
        tr = self._tr(bot, chat)
        self._send(
            bot,
            chat,
            tr._("The customer got the receipt by %(channels)s.")
            % {"channels": tg.escape(", ".join(channels))}
            if channels
            else tr._(
                "The customer has no email or Telegram on file: hand them a paper "
                "receipt."
            ),
        )

    def _send_receipt_to_customer(self, bot, chat, payment) -> list:
        tr = self._tr(bot, chat)
        if not payment.company_id.account_config_id.collection_send_receipt:
            return []
        channels = [tr._("email")] if payment.partner_id.email else []
        customer = payment.partner_id | payment.partner_id.child_ids
        customer_chat = self.env["telegram.chat"]._for_partner(customer, bot)[:1]
        if customer_chat:
            bot.send_message(
                customer_chat.chat_id,
                tr._(
                    "%(company)s received your payment of %(amount)s through "
                    "%(collector)s (receipt %(name)s). Verify it here: %(url)s"
                )
                % {
                    "company": tg.escape(payment.company_id.name),
                    "amount": tg.bold(payment.currency_id.format(payment.amount)),
                    "collector": tg.escape(payment.collector_id.name),
                    "name": tg.bold(payment.name),
                    "url": tg.link(
                        tr._("your receipt"), payment.get_collection_receipt_url()
                    ),
                },
            )
            channels.append("Telegram")
        return channels

    @log_command_execution
    def _handle_custody_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        if self._refuse_non_collector(bot, chat, internal_user):
            return
        tr = self._tr(bot, chat)
        held = self._held_payments(internal_user)
        if not held:
            self._send(bot, chat, tr._("You hold no collections."))
            return
        today = fields.Date.context_today(self)
        lines = [
            tr._("You hold %(total)s in %(count)s collections:")
            % {
                "total": tg.bold(self._money(sum(held.mapped("amount")))),
                "count": len(held),
            },
            "",
        ]
        lines.extend(
            "• "
            + tr._(
                "%(date)s %(customer)s: %(amount)s (%(days)s days)",
                date=payment.date.strftime("%d/%m"),
                customer=tg.escape(payment.partner_id.name),
                amount=tg.escape(self._money(payment.amount)),
                days=(today - payment.date).days,
            )
            + (
                " " + tg.bold(tr._("overdue"))
                if payment.date_custody_due and payment.date_custody_due < today
                else ""
            )
            for payment in held
        )
        self._send(
            bot,
            chat,
            "\n".join(lines),
            kb.single(tr._("Hand them in"), f"{REMIT}start"),
        )

    @log_command_execution
    def _handle_remit_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        self._start_remittance(bot, chat, internal_user)

    def _start_remittance(self, bot, chat, user) -> None:
        if self._refuse_non_collector(bot, chat, user):
            return
        tr = self._tr(bot, chat)
        abandoned = (
            self.env["account.collection.remittance"]
            .with_user(user)
            .search([("collector_id", "=", user.id), ("state", "=", "draft")])
        )
        if abandoned:
            abandoned.action_cancel()
            self._send(
                bot,
                chat,
                tr._("Your unfinished hand-in %(names)s was cancelled; start again.")
                % {"names": tg.escape(", ".join(abandoned.mapped("bank_reference")))},
            )
        held = self._held_payments(user).filtered(
            lambda payment: not payment.collection_remittance_id
        )
        if not held:
            self._send(bot, chat, tr._("You hold no collections to hand in."))
            return
        journals = (
            self.env["account.journal"]
            .with_user(user)
            .search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("type", "in", ("bank", "cash")),
                    ("is_collection_custody", "=", False),
                ],
                order="type desc, sequence, id",
            )
        )
        if not journals:
            self._send(
                bot, chat, tr._("There is no till or bank account to hand in to.")
            )
            return
        self._flow_start(
            chat,
            "remit_destination",
            {"payment_ids": held.ids, "held": sum(held.mapped("amount"))},
        )
        self._send(
            bot,
            chat,
            tr._("You hand in %(held)s. Where did the money go?")
            % {"held": tg.bold(self._money(sum(held.mapped("amount"))))},
            kb.record_list(
                journals,
                lambda journal: journal.name,
                lambda journal: f"{REMIT}j:{journal.id}",
                limit=LIST_LIMIT,
                width=48,
            ),
        )

    def _set_remit_destination(self, bot, chat, journal_id, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        journal = self.env["account.journal"].with_user(user).browse(int(journal_id))
        chat._flow_advance(
            "remit_amount",
            {**data, "journal_id": journal.id, "journal_type": journal.type},
        )
        self._send(
            bot,
            chat,
            tr._("How much did you hand in? Send the amount, or press the button."),
            kb.single(
                tr._("All %(held)s", held=self._money(data["held"])), f"{REMIT}a"
            ),
        )

    def _read_remit_amount(self, bot, chat, message, text, user) -> None:
        amount = _parse_amount(text)
        if amount is None:
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._("Send the amount as a number, like 1500.50."),
            )
            return
        self._set_remit_amount(bot, chat, amount, user)

    def _set_remit_amount(self, bot, chat, amount, user) -> None:
        tr = self._tr(bot, chat)
        data = {**self._flow_data(chat), "amount": amount}
        if data["journal_type"] != "bank":
            chat._flow_advance("remit_slip", data)
            self._send(
                bot,
                chat,
                tr._("Send a photo of the cash receipt from the till, or skip it."),
                kb.single(tr._("Skip"), f"{REMIT}x"),
            )
            return
        try:
            remittance = self._prepare_remittance(user, data)
        except (UserError, ValidationError, AccessError) as error:
            self._flow_end(chat)
            self._send(
                bot,
                chat,
                tr._("The hand-in was not recorded: %(reason)s")
                % {"reason": tg.escape(str(error))},
            )
            return
        chat._flow_advance("remit_slip", {**data, "remittance_id": remittance.id})
        self._send(
            bot,
            chat,
            tr._(
                "Deposit %(amount)s into %(bank)s quoting the reference "
                "%(reference)s, then send a photo of the deposit slip. With that "
                "reference the bank's report validates your hand-in by itself."
            )
            % {
                "amount": tg.bold(self._money(amount)),
                "bank": tg.escape(remittance.destination_journal_id.name),
                "reference": tg.code(remittance.bank_reference),
            },
        )

    def _prepare_remittance(self, user, data):
        return (
            self.env["account.collection.remittance"]
            .with_user(user)
            .create(
                {
                    "collector_id": user.id,
                    "company_id": self.env.company.id,
                    "destination_journal_id": data["journal_id"],
                    "payment_ids": [Command.set(data["payment_ids"])],
                    "amount_handed_in": data["amount"],
                }
            )
        )

    def _cancel_prepared_remittance(self, chat) -> None:
        remittance_id = self._flow_data(chat).get("remittance_id")
        if not remittance_id:
            return
        user = self._chat_internal_user(chat)
        remittance = (
            self.env["account.collection.remittance"]
            .with_user(user)
            .browse(remittance_id)
            .exists()
        )
        if remittance.state == "draft":
            remittance.action_cancel()

    def _on_flow_cancelled(self, bot, chat):
        self._cancel_prepared_remittance(chat)

    def _read_remit_slip(self, bot, chat, message, text, user) -> None:
        slip = self._first_file(message)
        if not slip:
            self._send(
                bot, chat, self._tr(bot, chat)._("Send a photo or a PDF, please.")
            )
            return
        data = self._flow_data(chat)
        self._ask_remit_confirmation(
            bot,
            chat,
            user,
            {
                **data,
                "proof_file_id": slip["file_id"],
                "proof_mimetype": slip["mimetype"],
            },
        )

    def _ask_remit_confirmation(self, bot, chat, user, data) -> None:
        tr = self._tr(bot, chat)
        chat._flow_advance("remit_confirm", data)
        journal = self.env["account.journal"].with_user(user).browse(data["journal_id"])
        lines = [
            tr._("Hand in these collections?"),
            "",
            f"{tg.bold(tr._('Collections'))}: {len(data['payment_ids'])} · {tg.escape(self._money(data['held']))}",
            f"{tg.bold(tr._('Handed in to'))}: {tg.escape(journal.name)}",
            f"{tg.bold(tr._('Amount'))}: {tg.escape(self._money(data['amount']))}",
        ]
        difference = data["amount"] - data["held"]
        if not self.env.company.currency_id.is_zero(difference):
            lines.append(
                tg.bold(
                    tr._(
                        "Difference: %(difference)s",
                        difference=self._money(difference),
                    )
                )
            )
        self._send(
            bot,
            chat,
            "\n".join(lines),
            kb.confirm_cancel(
                tr._("Confirm"), f"{REMIT}ok", tr._("Cancel"), f"{REMIT}no"
            ),
        )

    def _confirm_remittance(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        try:
            remittance = (
                self.env["account.collection.remittance"]
                .with_user(user)
                .browse(data["remittance_id"])
                if data.get("remittance_id")
                else self._prepare_remittance(user, data)
            )
            remittance.action_submit()
            if attachments := self._download_proof(bot, data, remittance.name):
                remittance.message_post(
                    body=tr._("Hand-in slip, sent from Telegram."),
                    attachments=attachments,
                )
        except (UserError, ValidationError, AccessError) as error:
            self._flow_end(chat)
            self._send(
                bot,
                chat,
                tr._("The hand-in was not recorded: %(reason)s")
                % {"reason": tg.escape(str(error))},
            )
            return
        self._flow_end(chat)
        self._send(
            bot,
            chat,
            tr._(
                "Remittance %(name)s sent to the treasury for validation. Your "
                "collections stay in your custody until it is validated."
            )
            % {"name": tg.bold(remittance.name)},
        )

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        step = self._flow_step(chat)
        tr = self._tr(bot, chat)
        if data == f"{REMIT}start":
            if chat._flow_is_open():
                self._send(
                    bot, chat, tr._("Finish or /cancelar what you are doing first.")
                )
            else:
                self._start_remittance(bot, chat, internal_user)
            return True
        if data in (f"{COLLECT}no", f"{REMIT}no"):
            self._cancel_prepared_remittance(chat)
            self._flow_end(chat)
            self._send(bot, chat, tr._("Cancelled; nothing was recorded."))
            return True
        kind, _sep, value = data.partition(":")[2].partition(":")
        actions = self._get_callback_actions(bot, chat, value, internal_user)
        action = actions.get((step, kind))
        if not action:
            self._send(bot, chat, tr._("That button is no longer valid."))
            return True
        self._clear_keyboard(bot, chat, callback_query)
        action()
        return True

    def _get_callback_actions(self, bot, chat, value, internal_user) -> dict:
        return {
            ("collect_customer", "p"): lambda: self._offer_collectables(
                bot, chat, self.env["res.partner"].browse(int(value)), internal_user
            ),
            ("collect_invoice", "i"): lambda: self._choose_invoices(
                bot, chat, value, internal_user
            ),
            ("collect_amount", "a"): lambda: self._set_collect_amount(
                bot, chat, self._flow_data(chat)["due"], internal_user
            ),
            ("collect_method", "m"): lambda: self._set_collect_method(
                bot, chat, value if value in ("cash", "check") else "cash"
            ),
            ("collect_date", "d"): lambda: self._set_collect_date(
                bot,
                chat,
                fields.Date.context_today(self) - timedelta(days=int(value or 0)),
            ),
            ("collect_check_date", "k"): lambda: self._set_collect_check_date(
                bot, chat, fields.Date.to_date(self._flow_data(chat)["date"])
            ),
            ("collect_proof", "x"): lambda: self._skip_collect_proof(
                bot, chat, internal_user
            ),
            ("collect_confirm", "ok"): lambda: self._confirm_collection(
                bot, chat, internal_user
            ),
            ("remit_destination", "j"): lambda: self._set_remit_destination(
                bot, chat, value, internal_user
            ),
            ("remit_amount", "a"): lambda: self._set_remit_amount(
                bot, chat, self._flow_data(chat)["held"], internal_user
            ),
            ("remit_slip", "x"): lambda: self._skip_remit_slip(
                bot, chat, internal_user
            ),
            ("remit_confirm", "ok"): lambda: self._confirm_remittance(
                bot, chat, internal_user
            ),
        }

    def _skip_collect_proof(self, bot, chat, user) -> None:
        data = self._flow_data(chat)
        if data.get("method") == "check":
            self._send(bot, chat, self._tr(bot, chat)._("Send a photo of the check."))
            return
        self._ask_collect_location(bot, chat, data)

    def _skip_remit_slip(self, bot, chat, user) -> None:
        data = self._flow_data(chat)
        if data.get("journal_type") == "bank":
            self._send(
                bot, chat, self._tr(bot, chat)._("Send a photo of the deposit slip.")
            )
            return
        self._ask_remit_confirmation(bot, chat, user, data)
