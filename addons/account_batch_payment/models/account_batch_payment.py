import base64

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tools import frozendict


class AccountBatchPayment(models.Model):
    _name = "account.batch.payment"
    _description = "Batch Payment"
    _order = "date desc, id desc"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _access_anchors = frozendict(
        {
            "company": models.Anchor("journal_id.company_id", hierarchy="parent_of"),
        }
    )

    def _get_default_journal(self):
        return self.env["account.journal"].search([("type", "=", "bank")], limit=1)

    name = fields.Char(
        string="Reference",
        copy=False,
        required=True,
    )
    date = fields.Date(
        default=fields.Date.context_today,
        copy=False,
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "New"),
            ("sent", "Sent"),
            ("reconciled", "Reconciled"),
        ],
        compute="_compute_state",
        default="draft",
        store=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Bank",
        default=lambda self: self._get_default_journal(),
        domain=[("type", "=", "bank")],
        check_company=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="journal_id.company_id",
        readonly=True,
    )
    payment_ids = fields.One2many(
        comodel_name="account.payment",
        inverse_name="batch_payment_id",
        string="Payments",
        required=True,
    )
    payment_ids_domain = fields.Char(compute="_compute_payment_ids_domain")
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        store=True,
        readonly=True,
    )
    company_currency_id = fields.Many2one(
        related="journal_id.company_id.currency_id",
        string="Company Currency",
    )
    amount_residual = fields.Monetary(
        currency_field="company_currency_id",
        compute="_compute_from_payment_ids",
        store=True,
    )
    amount_residual_currency = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_from_payment_ids",
        store=True,
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_from_payment_ids",
        store=True,
    )
    batch_type = fields.Selection(
        selection=[("inbound", "Inbound"), ("outbound", "Outbound")],
        default="inbound",
        required=True,
        tracking=True,
    )
    payment_method_id = fields.Many2one(
        comodel_name="account.payment.method",
        compute="_compute_payment_method_id",
        store=True,
        readonly=False,
        domain="[('id', 'in', available_payment_method_ids)]",
        tracking=True,
        help="The payment method used by the payments in this batch.",
    )
    available_payment_method_ids = fields.Many2many(
        comodel_name="account.payment.method",
        compute="_compute_available_payment_method_ids",
    )
    payment_method_code = fields.Char(
        related="payment_method_id.code",
        tracking=True,
    )
    export_file_create_date = fields.Date(
        string="Generation Date",
        default=fields.Date.today,
        copy=False,
        readonly=True,
        help="Creation date of the related export file.",
    )
    export_file = fields.Binary(
        string="File",
        copy=False,
        readonly=True,
        help="Export file related to this batch",
    )
    export_filename = fields.Char(
        string="File Name",
        store=True,
        copy=False,
        help="Name of the export file generated for this batch",
    )

    file_generation_enabled = fields.Boolean(
        compute="_compute_file_generation_enabled",
        help="Whether or not this batch payment should display the 'Generate File' button instead of 'Print' in form view.",
    )
    invalid_sct_partners_ids = fields.Many2many(
        comodel_name="res.partner",
        compute="_compute_invalid_sct_partners_ids",
    )

    @api.depends("batch_type", "journal_id", "payment_method_id")
    def _compute_payment_ids_domain(self) -> None:
        for batch in self:
            batch.payment_ids_domain = str(
                [
                    ("batch_payment_id", "=", False),
                    ("state", "in", self._valid_payment_states()),
                    ("is_sent", "=", False),
                    ("payment_method_id", "=", batch.payment_method_id.id),
                    ("journal_id", "=", batch.journal_id.id),
                    ("payment_type", "=", batch.batch_type),
                    ("amount", "!=", 0),
                ]
            )

    def _valid_payment_states(self):
        return (
            ["in_process", "paid"]
            if self.env["account.move"]._get_invoice_in_payment_state() == "paid"
            else ["in_process"]
        )

    @api.depends("batch_type", "journal_id", "payment_ids")
    def _compute_payment_method_id(self) -> None:
        for batch in self:
            if batch.payment_ids:
                batch.payment_method_id = batch.payment_ids.payment_channel_id[
                    0
                ].payment_method_id
                continue

            if not batch.journal_id:
                batch.available_payment_method_ids = False
                batch.payment_method_id = False
                continue

            available_payment_channels = (
                batch.journal_id._get_available_payment_channels(batch.batch_type)
            )

            batch.available_payment_method_ids = available_payment_channels.mapped(
                "payment_method_id"
            )

            if batch.available_payment_method_ids:
                batch.payment_method_id = batch.available_payment_method_ids[0]._origin
            else:
                batch.payment_method_id = False

    @api.depends("batch_type", "journal_id")
    def _compute_available_payment_method_ids(self) -> None:
        for batch in self:
            available_payment_channels = (
                batch.journal_id._get_available_payment_channels(batch.batch_type)
            )
            batch.available_payment_method_ids = available_payment_channels.mapped(
                "payment_method_id"
            )

    @api.depends("payment_ids.is_sent", "payment_ids.is_bank_matched")
    def _compute_state(self):
        for batch in self:
            if batch.payment_ids and all(
                pay.is_bank_matched and pay.is_sent
                for pay in batch.payment_ids.filtered(
                    lambda p: p.state not in ("canceled", "rejected")
                )
            ):
                batch.state = "reconciled"
            elif batch.payment_ids and all(
                pay.is_sent
                for pay in batch.payment_ids.filtered(
                    lambda p: p.state not in ("canceled", "rejected")
                )
            ):
                batch.state = "sent"
            else:
                batch.state = "draft"

    @api.depends("payment_method_id")
    def _compute_file_generation_enabled(self) -> None:
        for record in self:
            record.file_generation_enabled = (
                record.payment_method_id.code in record._get_methods_generating_files()
            )

    def _get_methods_generating_files(self):
        return []

    @api.depends("journal_id")
    def _compute_currency_id(self) -> None:
        for batch in self:
            batch.currency_id = (
                batch.journal_id.currency_id
                or batch.company_currency_id
                or self.env.company.currency_id
            )

    @api.depends(
        "currency_id",
        "payment_ids.amount",
        "payment_ids.is_bank_matched",
        "payment_ids.state",
    )
    def _compute_from_payment_ids(self) -> None:
        valid_payment_states = self._valid_payment_states()
        for batch in self:
            amount = 0.0
            amount_residual = 0.0
            amount_residual_currency = 0.0
            for payment in batch.payment_ids:
                if payment.move_id:
                    liquidity_lines, _counterpart_lines, _writeoff_lines = (
                        payment._seek_for_lines()
                    )
                    for line in liquidity_lines:
                        if line.currency_id == batch.currency_id:
                            amount += line.amount_currency
                        elif batch.currency_id == line.company_currency_id:
                            amount += line.balance
                        else:
                            amount += line.company_currency_id._convert(
                                from_amount=line.balance,
                                to_currency=batch.currency_id,
                                company=line.company_id,
                                date=line.date,
                            )

                        if payment.state in valid_payment_states:
                            amount_residual += line.amount_residual
                            if line.currency_id == batch.currency_id:
                                amount_residual_currency += (
                                    line.amount_residual_currency
                                )
                            elif batch.currency_id == line.company_currency_id:
                                amount_residual_currency += line.amount_residual
                            else:
                                amount_residual_currency += (
                                    line.company_currency_id._convert(
                                        from_amount=line.amount_residual,
                                        to_currency=batch.currency_id,
                                        company=line.company_id,
                                        date=line.date,
                                    )
                                )
                else:
                    if payment.currency_id == batch.currency_id:
                        payment_amount = payment.amount_signed
                    elif batch.currency_id == payment.company_currency_id:
                        payment_amount = payment.amount_company_currency_signed
                    else:
                        payment_amount = payment.company_currency_id._convert(
                            from_amount=payment.amount_company_currency_signed,
                            to_currency=batch.currency_id,
                            company=payment.company_id,
                            date=payment.date,
                        )
                    amount += payment_amount
                    if payment.state in valid_payment_states:
                        amount_residual_currency += payment_amount
                        if payment.currency_id == batch.company_id.currency_id:
                            amount_residual += payment.amount_signed
                        elif batch.currency_id == payment.company_currency_id:
                            amount_residual += payment.amount_company_currency_signed
                        else:
                            amount_residual += payment.company_currency_id._convert(
                                from_amount=payment.amount_company_currency_signed,
                                to_currency=batch.company_id.currency_id,
                                company=payment.company_id,
                                date=payment.date,
                            )

            batch.amount_residual = amount_residual
            batch.amount = amount
            batch.amount_residual_currency = amount_residual_currency

    @api.constrains("batch_type", "journal_id", "payment_ids", "payment_method_id")
    def _check_payments_constrains(self) -> None:
        for record in self:
            if (
                record.payment_ids
                and record.journal_id != record.payment_ids.journal_id
            ):
                raise ValidationError(
                    self.env._(
                        "The journal of the batch payment and of the payments it contains must be the same."
                    )
                )
            all_types = set(record.payment_ids.mapped("payment_type"))
            if all_types and record.batch_type not in all_types:
                raise ValidationError(
                    self.env._(
                        "The batch must have the same type as the payments it contains."
                    )
                )
            all_payment_methods = record.payment_ids.payment_method_id
            if len(all_payment_methods) > 1:
                raise ValidationError(
                    self.env._(
                        "All payments in the batch must share the same payment method."
                    )
                )
            if (
                all_payment_methods
                and record.payment_method_id not in all_payment_methods
            ):
                raise ValidationError(
                    self.env._(
                        "The batch must have the same payment method as the payments it contains."
                    )
                )
            payment_with_entries = record.payment_ids.filtered(
                lambda payment: payment.move_id
            )
            payment_without_entries = record.payment_ids - payment_with_entries
            if payment_with_entries and payment_without_entries:
                raise ValidationError(
                    self.env._("All payments must either have an entry or not at all.")
                )
            payment_null = record.payment_ids.filtered(lambda p: p.amount == 0)
            if payment_null:
                raise ValidationError(
                    self.env._(
                        "You cannot add payments with zero amount in a Batch Payment."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        all_payment_ids = []
        for vals in vals_list:
            vals["name"] = self._get_batch_name(
                vals.get("batch_type"), vals.get("date", today), vals
            )
            if "payment_ids" in vals:
                payments = self.new({"payment_ids": vals["payment_ids"]}).payment_ids
                if payments._origin.batch_payment_id:
                    raise ValidationError(
                        self.env._(
                            "You cannot create a batch with payments that are already in another batch."
                        )
                    )
                all_payment_ids.extend(payments.ids)

        if len(all_payment_ids) != len(set(all_payment_ids)):
            raise ValidationError(
                self.env._("You cannot create batches with overlapping payments.")
            )
        return super().create(vals_list)

    def write(self, vals):
        if "batch_type" in vals:
            vals["name"] = self.with_context(
                default_journal_id=self.journal_id.id
            )._get_batch_name(vals["batch_type"], self.date, vals)
        if "payment_ids" in vals:
            if len(self) > 1:
                raise ValidationError(
                    self.env._("You cannot add the same payment to multiple batches.")
                )
            original_payments = self.new(
                {"payment_ids": vals["payment_ids"]}
            ).payment_ids._origin
            if original_payments.batch_payment_id - self:
                raise ValidationError(
                    self.env._(
                        "You cannot create a batch with payments that are already in another batch."
                    )
                )

        return super().write(vals)

    def unlink(self):
        for batch in self:
            for payment in batch.payment_ids:
                payment.message_post(
                    body=self.env._(
                        "Payment removed from batch %s",
                        batch._get_html_link(title=batch.name),
                    ),
                    message_type="comment",
                )
        return super().unlink()

    @api.model
    def _get_batch_name(self, batch_type, sequence_date, vals):
        if not vals.get("name"):
            sequence_code = "account.inbound.batch.payment"
            if batch_type == "outbound":
                sequence_code = "account.outbound.batch.payment"
            return (
                self.env["ir.sequence"]
                .with_context(sequence_date=sequence_date)
                .next_by_code(sequence_code)
            )
        return vals["name"]

    @api.depends("state")
    def _compute_display_name(self):
        state_values = dict(self._fields["state"].selection)
        for batch in self:
            batch.display_name = f"{batch.name} ({state_values.get(batch.state)})"

    @api.depends(
        "payment_method_id",
        "payment_ids.partner_id.country_id",
        "payment_ids.partner_id.city",
    )
    def _compute_invalid_sct_partners_ids(self) -> None:
        sepa_batches = self.filtered(lambda b: b.payment_method_id.code == "sepa_ct")
        for batch in sepa_batches:
            invalid_partners = self.env["res.partner"]
            for partner in batch.payment_ids.partner_id:
                addresses = partner.sudo()._get_all_addr()
                has_valid_address = any(
                    addr.get("city") and addr.get("country") for addr in addresses
                )
                if not has_valid_address:
                    invalid_partners |= partner

            batch.invalid_sct_partners_ids = invalid_partners
        (self - sepa_batches).invalid_sct_partners_ids = self.env["res.partner"]

    def action_invalid_partners_from_sct(self):
        return self.invalid_sct_partners_ids._get_records_action(
            name=self.env._("Invalid Partners")
        )

    def confirm_batch(self):
        validate_action = self._check_batch_validity()
        if validate_action:
            return validate_action
        return self._send_after_validation()

    def _check_batch_validity(self) -> dict | None:
        self.check_singleton()
        if not self.payment_ids:
            raise UserError(
                self.env._(
                    "Cannot validate an empty batch. Please add some payments to it first."
                )
            )

        errors = (not self.export_file and self.check_payments_for_errors()) or []
        warnings = self.get_payment_warnings()
        if errors or warnings:
            if len(errors) == 1 and not warnings:
                raise RedirectWarning(
                    message=errors[0]["title"] + "\n" + errors[0].get("help", ""),
                    action=errors[0]
                    .get("records", self.env["account.payment"])
                    ._get_records_action(name=self.env._("Payments in Error")),
                    button_text=self.env._("Check Payments"),
                )
            return {
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "wizard.account.batch.payment.validate.error",
                "target": "new",
                "res_id": self.env["wizard.account.batch.payment.validate.error"]
                .create_from_errors_list(self, errors, warnings)
                .id,
            }
        return None

    def action_confirm_batch(self):
        return self.confirm_batch()

    def _send_after_validation(self):

        self.check_singleton()
        if self.payment_ids:
            self.payment_ids.mark_as_sent()

            if self.file_generation_enabled:
                return self.export_batch_payment()
        return None

    def get_payment_warnings(self):
        return []

    def check_payments_for_errors(self):
        self.check_singleton()
        rslt = self._check_and_post_draft_payments(
            self.payment_ids.filtered(lambda x: x.state == "draft")
        )

        valid_payment_states = self._valid_payment_states()
        wrong_state_payments = self.payment_ids.filtered(
            lambda x: x.state not in valid_payment_states
        )

        if wrong_state_payments:
            rslt.append(
                {
                    "title": self.env._(
                        "To validate the batch, payments must be in process. But some are already matched with a bank statement."
                    ),
                    "records": wrong_state_payments,
                    "help": self.env._(
                        "Remove the payments from the batch or change their state."
                    ),
                }
            )

        if self.batch_type == "outbound":
            not_allowed_payments = self.payment_ids.filtered(
                lambda x: x.bank_account_id and not x.bank_account_id.allow_out_payment
            )
            if not_allowed_payments:
                rslt.append(
                    {
                        "code": "out_payment_not_allowed",
                        "title": self.env._(
                            "Some recipient accounts do not allow out payments."
                        ),
                        "records": not_allowed_payments,
                        "help": self.env._(
                            "Target another recipient account or allow sending money to the current one."
                        ),
                    }
                )

        sent_payments = self.payment_ids.filtered(lambda x: x.is_sent)
        if sent_payments:
            rslt.append(
                {
                    "title": self.env._("Some payments have already been sent."),
                    "records": sent_payments,
                }
            )

        return rslt

    def _check_and_post_draft_payments(self, draft_payments):
        exceptions_mapping = {}
        for payment in draft_payments:
            try:
                payment.action_post()
            except UserError as e:
                name = e.args[0]
                if name in exceptions_mapping:
                    exceptions_mapping[name] += payment
                else:
                    exceptions_mapping[name] = payment

        return [
            {"title": error, "records": pmts}
            for error, pmts in exceptions_mapping.items()
        ]

    def export_batch_payment(self) -> None:
        self.check_access("write")
        for record in self.sudo():
            record = record.with_company(record.journal_id.company_id)
            export_file_data = record._generate_export_file()
            record.export_file = export_file_data["file"]
            record.export_filename = export_file_data["filename"]
            record.export_file_create_date = fields.Date.today()
            record.message_post(
                attachments=[
                    (record.export_filename, base64.decodebytes(record.export_file)),
                ]
            )

    def _generate_export_file(self):
        self.check_singleton()
        return False
