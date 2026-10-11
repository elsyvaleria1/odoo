import re
import unicodedata
from datetime import datetime
from typing import Self

import psycopg
from dateutil import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import email_normalize_all, float_round, frozendict

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import CURRENCY_MINOR_UNITS, SENSITIVE_KEYS
from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__, sensitive_keys=SENSITIVE_KEYS)


class PaymentTransaction(models.Model):
    _name = "payment.transaction"
    _description = "Payment Transaction"
    _order = "id desc"
    _rec_name = "reference"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    @api.model
    def _selection_installed_langs(self):
        return self.env["res.lang"].get_installed()

    provider_id = fields.Many2one(
        comodel_name="payment.provider",
        readonly=True,
        required=True,
    )
    provider_code = fields.Selection(
        related="provider_id.code",
        string="Provider Code",
    )
    company_id = fields.Many2one(
        related="provider_id.company_id",
    )
    payment_method_id = fields.Many2one(
        comodel_name="payment.method",
        readonly=True,
        required=True,
    )
    payment_method_code = fields.Char(
        related="payment_method_id.code",
        string="Payment Method Code",
    )
    primary_payment_method_id = fields.Many2one(
        comodel_name="payment.method",
        compute="_compute_primary_payment_method_id",
    )
    reference = fields.Char(
        readonly=True,
        required=True,
        help="The internal reference of the transaction",
    )
    provider_reference = fields.Char(
        readonly=True,
        help="The provider reference of the transaction",
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        readonly=True,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        readonly=True,
        required=True,
    )
    token_id = fields.Many2one(
        comodel_name="payment.token",
        string="Payment Token",
        index="btree_not_null",
        readonly=True,
        domain='[("provider_id", "=", "provider_id")]',
        ondelete="restrict",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pending", "Pending"),
            ("authorized", "Authorized"),
            ("done", "Confirmed"),
            ("cancel", "Canceled"),
            ("error", "Error"),
        ],
        string="Status",
        default="draft",
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    state_message = fields.Text(
        string="Message",
        readonly=True,
        help="The complementary information message about the state",
    )
    last_state_change = fields.Datetime(
        string="Last State Change Date",
        default=fields.Datetime.now,
        readonly=True,
    )

    operation = fields.Selection(
        selection=[
            ("online_redirect", "Online payment with redirection"),
            ("online_direct", "Online direct payment"),
            ("online_token", "Online payment by token"),
            ("validation", "Validation of the payment method"),
            ("offline", "Offline payment by token"),
            ("refund", "Refund"),
        ],
        index=True,
        readonly=True,
    )
    is_live = fields.Boolean(
        string="Production Environment",
        help="Whether the transaction happened in a production environment. False for transactions"
        " created before this tracking was implemented.",
    )
    source_transaction_id = fields.Many2one(
        comodel_name="payment.transaction",
        index="btree_not_null",
        readonly=True,
        help="The source transaction of the related child transactions",
    )
    child_transaction_ids = fields.One2many(
        comodel_name="payment.transaction",
        inverse_name="source_transaction_id",
        string="Child Transactions",
        readonly=True,
        help="The child transactions of the transaction.",
    )
    refunds_count = fields.Integer(compute="_compute_refunds_count")

    is_post_processed = fields.Boolean(
        string="Is Post-processed",
        help="Has the payment been post-processed",
    )
    tokenize = fields.Boolean(
        string="Create Token",
        help="Whether a payment token should be created when post-processing the transaction",
    )
    landing_route = fields.Char(
        help="The route the user is redirected to after the transaction"
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        readonly=True,
        required=True,
        ondelete="restrict",
    )
    partner_name = fields.Char()
    partner_lang = fields.Selection(
        selection=_selection_installed_langs,
        string="Language",
    )
    partner_email = fields.Char(string="Email")
    partner_address = fields.Char(string="Address")
    partner_zip = fields.Char(string="Zip")
    partner_city = fields.Char(string="City")
    partner_state_id = fields.Many2one(
        comodel_name="res.country.state",
        string="State",
    )
    partner_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country",
    )
    partner_phone = fields.Char(
        string="Phone",
        compute="_compute_partner_phone",
        store=True,
        readonly=False,
    )

    _reference_uniq = models.Constraint(
        "unique(reference)",
        "Reference must be unique!",
    )


    @api.depends("partner_id")
    def _compute_partner_phone(self) -> None:
        for tx in self:
            tx.partner_phone = tx.partner_id._phone_get_number().number or False

    def _compute_primary_payment_method_id(self) -> None:
        for pm, txs in self.grouped("payment_method_id").items():
            txs.primary_payment_method_id = pm.primary_payment_method_id or pm

    def _compute_refunds_count(self) -> None:
        rg_data = self.env["payment.transaction"]._read_group(
            domain=[
                ("source_transaction_id", "in", self.ids),
                ("operation", "=", "refund"),
            ],
            groupby=["source_transaction_id"],
            aggregates=["__count"],
        )
        data = {source_transaction.id: count for source_transaction, count in rg_data}
        for record in self:
            record.refunds_count = data.get(record.id, 0)


    @api.constrains("state")
    def _check_state_authorized_supported(self) -> None:
        illegal_authorize_state_txs = self.filtered(
            lambda tx: (
                tx.state == "authorized" and not tx.provider_id.support_manual_capture
            )
        )
        if illegal_authorize_state_txs:
            raise ValidationError(
                self.env._(
                    "Transaction authorization is not supported by the following payment providers: %s",
                    ", ".join(
                        set(illegal_authorize_state_txs.mapped("provider_id.name"))
                    ),
                )
            )

    @api.constrains("token_id")
    def _check_token_is_active(self) -> None:
        if self.token_id and not self.token_id.active:
            raise ValidationError(
                self.env._(
                    "Creating a transaction from an archived token is forbidden."
                )
            )


    @api.model_create_multi
    def create(self, vals_list):
        providers = self.env["payment.provider"].browse(
            [values.get("provider_id") for values in vals_list]
        )
        partners = self.env["res.partner"].browse(
            [values.get("partner_id") for values in vals_list]
        )

        references_in_use = set()
        for values, provider, partner in zip(
            vals_list, providers, partners, strict=True
        ):
            if not values.get("reference"):
                values["reference"] = self._get_unique_reference(
                    provider.code, references_in_use=references_in_use, **values
                )
            references_in_use.add(values["reference"])

            values["is_live"] = provider.state == "enabled"

            partner_emails = email_normalize_all(partner.email)
            values.update(
                {
                    "partner_name": partner.name or partner.parent_id.name,
                    "partner_lang": partner.lang,
                    "partner_email": partner_emails[0] if partner_emails else None,
                    "partner_address": payment_utils.format_partner_address(
                        partner.street, partner.street2
                    ),
                    "partner_zip": partner.zip,
                    "partner_city": partner.city,
                    "partner_state_id": partner.state_id.id,
                    "partner_country_id": partner.country_id.id,
                }
            )

            values.update(self._prepare_provider_create_vals(provider.code, values))

        txs = super().create(vals_list)

        txs.invalidate_recordset(["amount"])

        return txs

    @api.model
    def _prepare_provider_create_vals(
        self, provider_code: str, values: ValuesType
    ) -> ValuesType:
        return {}


    def action_view_refunds(self):
        self.check_singleton()

        action = {
            "name": self.env._("Refund"),
            "res_model": "payment.transaction",
            "type": "ir.actions.act_window",
        }
        if self.refunds_count == 1:
            refund_tx = self.env["payment.transaction"].search(
                [("source_transaction_id", "=", self.id), ("operation", "=", "refund")],
                limit=1,
            )
            action["res_id"] = refund_tx.id
            action["view_mode"] = "form"
        else:
            action["view_mode"] = "list,form"
            action["domain"] = [("source_transaction_id", "=", self.id)]
        return action

    def action_capture(self):
        payment_utils.check_rights_on_recordset(self)

        if any(
            tx.provider_id.sudo().support_manual_capture == "partial" for tx in self
        ):
            return {
                "name": self.env._("Capture"),
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "wizard.payment.transaction.capture",
                "target": "new",
                "context": {
                    "active_model": "payment.transaction",
                    "active_ids": self.filtered(
                        lambda tx: tx.state in ["authorized", "done"]
                    ).ids,
                    "payment_backend_action": True,
                },
            }
        else:
            captured_txs_sudo = self.env["payment.transaction"].sudo()
            for tx in self.filtered(lambda tx: tx.state == "authorized"):
                captured_txs_sudo |= (
                    tx.sudo().with_context(payment_backend_action=True)._capture()
                )
            return captured_txs_sudo._prepare_action_feedback_notification()

    def action_void(self):
        payment_utils.check_rights_on_recordset(self)

        if any(tx.state != "authorized" for tx in self):
            raise ValidationError(
                self.env._("Only authorized transactions can be voided.")
            )

        voided_txs_sudo = self.env["payment.transaction"].sudo()
        for tx in self:
            captured_amount = sum(
                child_tx.amount
                for child_tx in tx.child_transaction_ids.filtered(
                    lambda t, tx=tx: t.state == "done" and t.operation == tx.operation
                )
            )
            voided_txs_sudo |= (
                tx.sudo()
                .with_context(payment_backend_action=True)
                ._void(amount_to_void=tx.amount - captured_amount)
            )
        return voided_txs_sudo._prepare_action_feedback_notification()

    def action_refund(self, amount_to_refund=None):
        payment_utils.check_rights_on_recordset(self)

        if any(tx.state != "done" for tx in self):
            raise ValidationError(
                self.env._("Only confirmed transactions can be refunded.")
            )

        refunded_txs_sudo = self.env["payment.transaction"].sudo()
        for tx in self:
            refunded_txs_sudo |= (
                tx.sudo()
                .with_context(payment_backend_action=True)
                ._refund(amount_to_refund=amount_to_refund)
            )
        return refunded_txs_sudo._prepare_action_feedback_notification()

    def _prepare_action_feedback_notification(self) -> dict:
        if not (failed_txs := self.filtered(lambda tx: tx.state == "error")):
            notification_type = "success"
            msg = self.env._("Your payment operation has been successfully submitted.")
        else:
            notification_type = "danger"
            msg = self.env._(
                "Your payment operation could not be completed for following transactions:"
                " %(tx_refs)s",
                tx_refs=", ".join(failed_txs.mapped("reference")),
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": notification_type,
                "message": msg,
                "next": {
                    "type": "ir.actions.act_window_close"
                },
            },
        }

    def action_post_process(self) -> dict:
        self._post_process()
        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }


    @api.model
    def _get_unique_reference(
        self,
        provider_code,
        prefix=None,
        separator="-",
        references_in_use: set[str] | None = None,
        **kwargs,
    ) -> str:
        references_in_use = references_in_use or set()

        if prefix:
            prefix = (
                unicodedata.normalize("NFKD", prefix)
                .encode("ascii", "ignore")
                .decode("utf-8")
            )
        if (
            not prefix
        ):
            prefix = self.sudo()._get_reference_prefix(separator, **kwargs)
        if (
            not prefix
        ):
            prefix = payment_utils.singularize_reference_prefix()

        reference = prefix
        if prefix in references_in_use or self.sudo().search_count(
            [("reference", "=", prefix)], limit=1
        ):
            same_prefix_references = set(
                self.sudo()
                .search([("reference", "=like", f"{prefix}{separator}%")])
                .with_context(prefetch_fields=False)
                .mapped("reference")
            )
            same_prefix_references |= {
                ref
                for ref in references_in_use
                if ref.startswith(f"{prefix}{separator}")
            }

            search_pattern = re.compile(
                rf"^{re.escape(prefix)}{re.escape(separator)}(\d+)$"
            )
            max_sequence_number = (
                0
            )
            for existing_reference in same_prefix_references:
                search_result = re.search(search_pattern, existing_reference)
                if (
                    search_result
                ):
                    current_sequence = int(search_result.group(1))
                    max_sequence_number = max(max_sequence_number, current_sequence)

            reference = f"{prefix}{separator}{max_sequence_number + 1}"
        return reference

    @api.model
    def _get_reference_prefix(self, separator, **values):
        return ""

    def _prepare_processing_values(self):
        self.check_singleton()

        processing_values = {
            "provider_id": self.provider_id.id,
            "provider_code": self.provider_code,
            "reference": self.reference,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "partner_id": self.partner_id.id,
            "should_tokenize": self.tokenize,
        }

        processing_values.update(
            self._prepare_provider_processing_values(processing_values)
        )

        if self.operation in ("online_redirect", "validation"):
            redirect_form_view = self.provider_id._get_redirect_form_view(
                is_validation=self.operation == "validation"
            )
            if redirect_form_view:
                rendering_values = self._prepare_redirect_form_values(processing_values)
                redirect_form_html = self.env["ir.qweb"]._render(
                    redirect_form_view.id, rendering_values
                )
                processing_values.update(redirect_form_html=redirect_form_html)

        processing_values.update(
            {
                "state": self.state,
                "state_message": self.state_message,
            }
        )

        return processing_values

    def _prepare_provider_processing_values(self, processing_values):
        return {}

    def _prepare_redirect_form_values(self, processing_values):
        return {}

    def _prepare_mandate_data(self):
        self.check_singleton()
        return {}

    def _charge_with_token(self) -> None:
        self.check_singleton()
        self._check_provider_is_not_disabled()
        self._log_sent_message()
        try:
            self._send_payment_request()
        except ValidationError as e:
            self._set_error(str(e))

    def _send_payment_request(self):
        return

    def _capture(self, amount_to_capture=None):
        self.check_singleton()
        self._check_provider_is_not_disabled()

        capture_tx = self._create_child_transaction(amount_to_capture or self.amount)
        capture_tx._log_sent_message()
        try:
            capture_tx._send_capture_request()
        except ValidationError as e:
            capture_tx._set_error(str(e))
        return capture_tx

    def _send_capture_request(self):
        return

    def _void(self, amount_to_void=None):
        self.check_singleton()
        self._check_provider_is_not_disabled()

        void_tx = self._create_child_transaction(amount_to_void or self.amount)
        void_tx._log_sent_message()
        try:
            void_tx._send_void_request()
        except ValidationError as e:
            void_tx._set_error(str(e))
        return void_tx

    def _send_void_request(self):
        return

    def _refund(self, amount_to_refund=None):
        self.check_singleton()
        self._check_provider_is_not_disabled()

        refund_tx = self._create_child_transaction(
            amount_to_refund or self.amount, is_refund=True
        )
        refund_tx._log_sent_message()
        try:
            refund_tx._send_refund_request()
        except ValidationError as e:
            refund_tx._set_error(str(e))
        return refund_tx

    def _send_refund_request(self):
        return

    def _check_provider_is_not_disabled(self) -> None:
        if self.provider_id.state == "disabled":
            raise UserError(
                self.env._(
                    "Making a request to the provider is not possible because the provider is disabled."
                )
            )

    def _create_child_transaction(
        self, amount, is_refund=False, **custom_create_values
    ) -> Self:
        self.check_singleton()

        if is_refund:
            reference_prefix = f"R-{self.reference}"
            amount = -amount
            operation = "refund"
        else:
            reference_prefix = f"P-{self.reference}"
            operation = self.operation

        return self.create(
            {
                "provider_id": self.provider_id.id,
                "payment_method_id": self.payment_method_id.id,
                "reference": self._get_unique_reference(
                    self.provider_code, prefix=reference_prefix
                ),
                "amount": amount,
                "currency_id": self.currency_id.id,
                "token_id": self.token_id.id,
                "operation": operation,
                "source_transaction_id": self.id,
                "partner_id": self.partner_id.id,
                **custom_create_values,
            }
        )


    def _process(self, provider_code, payment_data):
        tx = self or self._search_by_reference(provider_code, payment_data)
        if tx:
            tx.check_singleton()
            previous_state = tx.state
            tx._check_amount(payment_data)
            if tx.state == "error" and tx.state != previous_state:
                return tx
            tx._apply_updates(payment_data)
            if tx.tokenize and tx.state in {"authorized", "done"}:
                tx._tokenize(payment_data)
        return tx

    @api.model
    def _inbound_gate_owner(self):
        return self.provider_id

    @api.model
    def _resolve_notification(self, provider_code, payment_data, acknowledged) -> tuple:
        tx = self.sudo()._search_notification_subject(provider_code, payment_data)
        if not tx:
            raise acknowledged
        return tx, {"data": payment_data}

    @api.model
    def _search_notification_subject(self, provider_code, payment_data):
        return self._search_by_reference(provider_code, payment_data)

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        self.check_singleton()
        return self._is_notification_signature_valid(
            self._inbound_notification_data(headers, body)
        )

    def _inbound_notification_data(self, headers, body):
        return request.get_http_params() if request else {}

    def _is_notification_signature_valid(self, payment_data) -> bool:
        self.check_singleton()
        return False

    def _search_by_reference(self, provider_code, payment_data):
        reference = self._extract_reference(provider_code, payment_data)
        if not reference:
            _logger.warning(
                "Received payment data from provider %s with missing reference",
                provider_code,
            )
            return self

        tx = self._search_by_notified_value(provider_code, "reference", reference)
        if not tx:
            _logger.warning("No transaction found matching reference %s.", reference)
        return tx

    @api.model
    def _search_by_notified_value(self, provider_code, field_name, value):
        if not value or not isinstance(value, str):
            return self.browse()
        return self.search(
            Domain(field_name, "=", value) & Domain("provider_code", "=", provider_code)
        )

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        return payment_data.get("reference")

    def _check_amount(self, payment_data) -> None:
        self.check_singleton()

        if self.operation == "validation":
            return

        amount_data = self._extract_amount_data(payment_data)
        if not amount_data:
            return

        amount = amount_data["amount"]
        currency_code = amount_data["currency_code"]
        precision_digits = amount_data.get("precision_digits")

        if not amount or not currency_code:
            error_message = self.env._(
                "The amount or currency is missing from the payment data."
            )
            self._set_error(error_message)
            return

        if self.operation == "refund":
            amount = -amount
        if precision_digits is None:
            precision_digits = CURRENCY_MINOR_UNITS.get(
                self.currency_id.name, self.currency_id.decimal_places
            )
        tx_amount = float_round(
            self.amount, precision_digits=precision_digits, rounding_method="DOWN"
        )
        if self.currency_id.compare_amounts(amount, tx_amount) != 0:
            error_message = self.env._(
                "The amount from the payment data doesn't match the one from the transaction."
            )
            self._set_error(error_message)
            return

        if currency_code != self.currency_id.name:
            error_message = self.env._(
                "The currency from the payment data doesn't match the one from the transaction."
            )
            self._set_error(error_message)

    def _extract_amount_data(self, payment_data) -> dict | None:
        return {}

    def _apply_updates(self, payment_data):
        return

    def _tokenize(self, payment_data):
        self.check_singleton()

        if not (token_values := self._extract_token_values(payment_data)):
            return

        token = self.env["payment.token"].create(
            {
                "provider_id": self.provider_id.id,
                "payment_method_id": self.payment_method_id.id,
                "partner_id": self.partner_id.id,
                **token_values,
            }
        )
        self.write(
            {
                "token_id": token,
                "tokenize": False,
            }
        )
        _logger.info(
            "Token %(token_id)s created for partner %(partner_id)s from transaction %(ref)s.",
            {
                "token_id": token.id,
                "partner_id": self.partner_id.id,
                "ref": self.reference,
            },
        )

    def _extract_token_values(self, payment_data) -> dict:
        return {}

    def _set_pending(self, *, state_message=None, extra_allowed_states=()):
        allowed_states = ("draft",)
        target_state = "pending"
        txs_to_process = self._update_state(
            allowed_states + extra_allowed_states, target_state, state_message
        )
        txs_to_process._log_received_message()
        return txs_to_process

    def _set_authorized(self, *, state_message=None, extra_allowed_states=()):
        allowed_states = ("draft", "pending")
        target_state = "authorized"
        txs_to_process = self._update_state(
            allowed_states + extra_allowed_states, target_state, state_message
        )
        txs_to_process._log_received_message()
        return txs_to_process

    def _set_done(self, *, state_message=None, extra_allowed_states=()):
        allowed_states = ("draft", "pending", "authorized", "error")
        target_state = "done"
        txs_to_process = self._update_state(
            allowed_states + extra_allowed_states, target_state, state_message
        )
        txs_to_process._log_received_message()
        txs_to_process._update_source_transaction_state()
        return txs_to_process

    def _set_canceled(self, state_message=None, extra_allowed_states=()):
        allowed_states = ("draft", "pending", "authorized")
        target_state = "cancel"
        txs_to_process = self._update_state(
            allowed_states + extra_allowed_states, target_state, state_message
        )
        txs_to_process._log_received_message()
        txs_to_process._update_source_transaction_state()
        return txs_to_process

    def _set_error(self, state_message, extra_allowed_states=()):
        allowed_states = ("draft", "pending", "authorized")
        target_state = "error"
        txs_to_process = self._update_state(
            allowed_states + extra_allowed_states, target_state, state_message
        )
        txs_to_process._log_received_message()
        return txs_to_process

    def _update_state(self, allowed_states, target_state, state_message):

        def classify_by_state(transactions_):
            txs_to_process_ = transactions_.filtered(
                lambda _tx: _tx.state in allowed_states
            )
            txs_already_processed_ = transactions_.filtered(
                lambda _tx: _tx.state == target_state
            )
            txs_wrong_state_ = transactions_ - txs_to_process_ - txs_already_processed_

            return txs_to_process_, txs_already_processed_, txs_wrong_state_

        txs_to_process, txs_already_processed, txs_wrong_state = classify_by_state(self)
        for tx in txs_already_processed:
            _logger.info(
                "Skipped the update of transaction %(ref)s as it is already in state %(state)s.",
                {"ref": tx.reference, "state": tx.state},
            )
        for tx in txs_wrong_state:
            _logger.warning(
                "Refused to update transaction %(ref)s from state %(tx_state)s to state"
                " %(target_state)s; allowed source states are: %(allowed_states)s.",
                {
                    "ref": tx.reference,
                    "tx_state": tx.state,
                    "target_state": target_state,
                    "allowed_states": allowed_states,
                },
            )
        txs_to_process.write(
            {
                "state": target_state,
                "state_message": state_message,
                "last_state_change": fields.Datetime.now(),
                "is_post_processed": False,
            }
        )
        return txs_to_process

    def _update_source_transaction_state(self) -> None:
        for child_tx in self.filtered("source_transaction_id"):
            sibling_txs = (
                child_tx.source_transaction_id.child_transaction_ids.filtered_domain(
                    [
                        ("state", "in", ["done", "cancel"]),
                        ("operation", "=", child_tx.operation),
                    ]
                )
            )
            processed_amount = sum(tx.amount for tx in sibling_txs)
            if (
                child_tx.currency_id.compare_amounts(
                    child_tx.source_transaction_id.amount, processed_amount
                )
                == 0
            ):
                fully_voided = all(tx.state == "cancel" for tx in sibling_txs)
                target_state = "cancel" if fully_voided else "done"
                child_tx.source_transaction_id._update_state(
                    ("authorized",), target_state, ""
                )
                child_tx.source_transaction_id._log_received_message()


    def _cron_post_process(self) -> None:
        txs_to_post_process = self
        if not txs_to_post_process:
            retry_limit_date = datetime.now() - relativedelta.relativedelta(days=4)
            txs_to_post_process = self.search(
                [
                    ("is_post_processed", "=", False),
                    ("last_state_change", ">=", retry_limit_date),
                ]
            )
        for tx in txs_to_post_process:
            try:
                tx._post_process()
                self.env["ir.cron"]._commit_progress(1)
            except psycopg.OperationalError:
                self.env.cr.rollback()
            except Exception:
                _logger.exception(
                    "An error occurred while post-processing transaction %s:",
                    tx.reference,
                )
                self.env.cr.rollback()

    def _post_process(self):
        self.is_post_processed = True


    def _send_api_request(
        self, method, endpoint, *, params=None, data=None, json=None, **kwargs
    ):
        self.check_singleton()
        return self.provider_id._send_api_request(
            method,
            endpoint,
            params=params,
            data=data,
            json=json,
            reference=self.reference,
            **kwargs,
        )


    def _log_sent_message(self) -> None:
        for tx in self:
            if message := tx._get_sent_message():
                tx._log_message_on_linked_documents(message)

    def _log_received_message(self) -> None:
        for tx in self:
            if message := tx._get_received_message():
                tx._log_message_on_linked_documents(message)

    def _log_message_on_linked_documents(self, message) -> None:
        self.check_singleton()


    def _get_sent_message(self):
        self.check_singleton()

        if self.operation in {
            "online_redirect",
            "online_direct",
            "online_token",
            "offline",
        }:
            sent_message = self.env._(
                "The transaction %(ref)s of %(formatted_amount)s has been initiated.",
                ref=self._get_html_link(),
                formatted_amount=self.currency_id.format(self.amount),
            )
        elif self.operation == "refund":
            sent_message = self.env._(
                "The refund %(ref)s of %(formatted_amount)s has been initiated.",
                ref=self._get_html_link(),
                formatted_amount=self.currency_id.format(-self.amount),
            )
        else:
            sent_message = (
                None
            )
        return sent_message

    def _get_received_message(self):
        self.check_singleton()

        if self.operation == "validation":
            return None

        msg_values = {
            "tx_label": "refund" if self.operation == "refund" else "transaction",
            "ref": self._get_html_link(),
            "formatted_amount": self.currency_id.format(self.amount),
        }
        match self.state:
            case "pending":
                received_message = self.env._(
                    "The %(tx_label)s %(ref)s of %(formatted_amount)s is pending.",
                    **msg_values,
                )
            case "authorized":
                received_message = self.env._(
                    "The %(tx_label)s %(ref)s of %(formatted_amount)s has been authorized.",
                    **msg_values,
                )
            case "done":
                received_message = self.env._(
                    "The %(tx_label)s %(ref)s of %(formatted_amount)s has been confirmed.",
                    **msg_values,
                )
            case "cancel":
                received_message = self.env._(
                    "The %(tx_label)s %(ref)s of %(formatted_amount)s has been canceled.",
                    **msg_values,
                )
            case "error":
                received_message = self.env._(
                    "The %(tx_label)s %(ref)s of %(formatted_amount)s encountered an error.",
                    **msg_values,
                )
            case _:
                received_message = None

        if self.state in {"cancel", "error"} and self.state_message:
            received_message += Markup("<br/>") + self.state_message

        return received_message

    def _get_last(self):
        return self.filtered(lambda t: t.state != "draft").sorted()[:1]
