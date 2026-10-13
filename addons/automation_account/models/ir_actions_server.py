import logging
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools.misc import format_amount, format_date

from odoo.addons.automation.models.ir_actions_server import STEP_REFERENCE_DEPENDS

_logger = logging.getLogger(__name__)

OPEN_ITEM_TYPES = ("asset_receivable", "liability_payable")

STATEMENT_STATES = ("workflow_register_statement", "workflow_reconcile_statement")
ACTS_ON_STATES = (
    "workflow_reconcile_statement",
    "workflow_apply_credit_note",
    "workflow_change_partner",
)
DOCUMENT_STATES = (
    "workflow_register_statement",
    "workflow_create_document",
    "workflow_change_partner",
    "workflow_apply_credit_note",
)
WORKFLOW_STATES = (
    *STATEMENT_STATES,
    "workflow_create_document",
    "workflow_change_partner",
    "workflow_apply_credit_note",
)


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(
        selection_add=[
            ("workflow_register_statement", "Register Bank Statement Line"),
            ("workflow_create_document", "Create Document from Template"),
            ("workflow_reconcile_statement", "Reconcile Bank Statement Line"),
            ("workflow_change_partner", "Change Partner of a Document"),
            ("workflow_apply_credit_note", "Apply Credit Note to Open Invoices"),
        ],
        ondelete={
            "workflow_register_statement": "cascade",
            "workflow_create_document": "cascade",
            "workflow_reconcile_statement": "cascade",
            "workflow_change_partner": "cascade",
            "workflow_apply_credit_note": "cascade",
        },
    )
    run_at_start = fields.Boolean(
        string="Run at Start",
        help="Execute this step as soon as a workflow started from a bank "
        "statement line begins, if the step is ready by then. Only for steps "
        "that create no document, such as registering the statement line.",
    )
    workflow_template_id = fields.Many2one(
        comodel_name="account.move.template",
        string="Document Template",
        ondelete="restrict",
        help="The template a Create Document step fills in with the run's "
        "partner, amount, date and reference.",
    )
    workflow_company_source = fields.Selection(
        selection=[
            ("transaction", "Company that Holds the Transaction"),
            ("statement", "Bank Statement Line's Company"),
            ("template", "Template's Company"),
        ],
        string="Create In",
        default="transaction",
        required=True,
        help="The company the document is created in. When another company's "
        "bank received the money, that company is the bank statement line's "
        "and the other one holds the transaction with the partner; a run of "
        "one company has only that one. A template that belongs to no "
        "company is created in the one that holds the transaction.",
    )
    workflow_partner_source = fields.Selection(
        selection=[
            ("partner", "Run's Partner"),
            ("third_party", "Run's Third Party"),
        ],
        string="Issue To",
        default="partner",
        required=True,
        help="Who the document is issued to. A run that names no third party "
        "issues it to its partner.",
    )
    workflow_date_source = fields.Selection(
        selection=[
            ("run", "Run's Date"),
            ("statement", "Bank Statement Line's Date"),
            ("document", "Latest Document of the Run"),
            ("today", "Day the Step Runs"),
        ],
        string="Dated",
        default="run",
        required=True,
        help="The date the document carries. The bank statement line's date "
        "is the day the money came in, whatever date the run was given; a "
        "run without one uses its own date. An invoice stamped days after "
        "the date it carries is refused by the tax authority, which is what "
        "the day the step runs avoids.",
    )
    workflow_tax_ids = fields.Many2many(
        comodel_name="account.tax",
        relation="ir_actions_server_workflow_tax_rel",
        column1="action_id",
        column2="tax_id",
        string="Replace Taxes With",
        help="When set, every line of the document carries these taxes "
        "instead of its product's. In another company, the tax of the same "
        "name and use is taken.",
    )
    workflow_source_step_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Acts On",
        domain="[('automation_rule_id', '=', automation_rule_id), ('id', '!=', id)]",
        ondelete="set null",
        help="The step whose document this one works on: the invoice a "
        "reconciliation settles, the credit note applied, the document issued "
        "again. Required when documents are made on more than one branch "
        "before it; it must run before this step.",
    )
    workflow_target_step_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Apply Against",
        domain="[('automation_rule_id', '=', automation_rule_id), ('id', '!=', id)]",
        ondelete="set null",
        help="The step whose document the credit note settles, and no other: "
        "the vendor bill this run issued, not an older one of the same "
        "partner. Leave it empty to settle the partner's open invoices, "
        "oldest first. It must run before this step.",
    )
    workflow_auto_post = fields.Boolean(
        string="Post the Document",
        default=True,
        help="Post the document as soon as it is created. Leave it off to "
        "review the draft first.",
    )

    @api.constrains("state", "workflow_template_id")
    def _check_workflow_template(self) -> None:
        for action in self:
            if action.state == "workflow_create_document" and not (
                action.workflow_template_id
            ):
                raise ValidationError(
                    self.env._(
                        "Step '%(step)s' creates a document from a template "
                        "but names none.",
                        step=action.name,
                    ),
                )

    @api.depends("model_id")
    def _compute_allowed_states(self) -> None:
        super()._compute_allowed_states()
        line_model = self.env["ir.model"]._get("automation.runtime.line")
        for action in self:
            if action.model_id != line_model:
                action.allowed_states = [
                    state
                    for state in action.allowed_states
                    if state not in WORKFLOW_STATES
                ]

    @api.onchange("workflow_template_id")
    def _onchange_workflow_template_id(self) -> None:
        if self.workflow_template_id.use_third_party:
            self.workflow_partner_source = "third_party"
        if self.workflow_template_id.company_id:
            self.workflow_company_source = "template"

    def _prepare_eval_context(self, action) -> dict[str, Any]:
        eval_context = super()._prepare_eval_context(action)

        runtime_line_id = self.env.context.get("runtime_line_id")
        if not runtime_line_id:
            return eval_context

        eval_context["action"] = eval_context["server_action"] = action

        if not eval_context.get("record") and not eval_context.get("records"):
            record = self.env["automation.runtime.line"].browse(runtime_line_id)
            if record.exists():
                eval_context["record"] = record
                eval_context["records"] = record

        return eval_context

    def _get_runtime_telegram_data(self, runtime) -> dict[str, Any]:
        if "approval.request" not in self.env or not runtime.ids:
            return {}

        approval = self.env["approval.request"].search(
            [("automation_runtime_id", "=", runtime.id)],
            limit=1,
        )
        if not approval or "telegram_data" not in approval._fields:
            return {}

        return approval.telegram_data or {}

    def create_move_from_template(
        self,
        runtime_line,
        template,
        context_vals=None,
        auto_post=True,
    ) -> models.Model:
        self.check_singleton()
        runtime_line.check_singleton()
        template.check_singleton()

        if not runtime_line._name == "automation.runtime.line":
            raise UserError(
                self.env._(
                    "This method must be called with a automation.runtime.line record. Got: %s",
                    runtime_line._name,
                ),
            )

        runtime = runtime_line.runtime_id
        _logger.info(
            "Creating move from template '%s' for runtime %s (line %s)",
            template.name,
            runtime.name,
            runtime_line.name,
        )

        wizard_vals = self._prepare_template_wizard_vals(runtime_line, template)

        context_vals = dict(context_vals or {})
        use_latest_document_date = context_vals.pop("use_latest_document_date", False)
        wizard_vals.update(context_vals)

        if use_latest_document_date:
            latest_date = runtime_line._get_nearest_document_date()
            if latest_date:
                wizard_vals["date"] = latest_date
                _logger.info("Using latest document date: %s", latest_date)

        wizard = self.env["wizard.account.move.template.create.move"].create(
            wizard_vals
        )
        result = wizard.create_move()

        if auto_post and result.state == "draft":
            result.action_post()
            _logger.info(
                "Posted document %s (type: %s)",
                result.name,
                result._name,
            )

        if result._name == "account.move":
            _logger.info(
                "Created journal entry %s from template %s (state: %s)",
                result.name,
                template.name,
                result.state,
            )
        elif result._name == "account.payment":
            _logger.info(
                "Created payment %s from template %s (state: %s)",
                result.name,
                template.name,
                result.state,
            )

        return result

    def _prepare_template_wizard_vals(self, runtime_line, template) -> dict[str, Any]:
        self.check_singleton()
        runtime = runtime_line.runtime_id
        wizard_vals = {
            "template_id": template.id,
            "partner_id": runtime.partner_id.id,
            "date": runtime.date,
            "ref": runtime.reference or template.ref,
        }

        if runtime.amount:
            wizard_vals["amount"] = runtime.amount

        if runtime.third_party_id:
            wizard_vals["third_party_id"] = runtime.third_party_id.id

        if runtime._is_intercompany() or not template.company_id:
            wizard_vals["multicompany_id"] = runtime._get_transaction_company().id

        tg_data = self._get_runtime_telegram_data(runtime)
        if tg_data:
            wizard_fields = self.env["wizard.account.move.template.create.move"]._fields

            pm_text = (tg_data.get("payment_method") or "").strip()
            if pm_text and "l10n_mx_edi_payment_method_id" in wizard_fields:
                pm_aliases = {
                    "TC": "Tarjeta de Crédito",
                    "TD": "Tarjeta de Débito",
                }
                pm_search = pm_aliases.get(pm_text.upper(), pm_text)
                pm_records = self.env["l10n_mx_edi.payment.method"].search(
                    [("name", "ilike", pm_search)],
                    order="id",
                )
                if pm_records:
                    if len(pm_records) > 1:
                        _logger.warning(
                            "'%s' matches %d payment methods (%s); taking '%s'",
                            pm_text,
                            len(pm_records),
                            ", ".join(pm_records.mapped("name")),
                            pm_records[0].name,
                        )
                    wizard_vals["l10n_mx_edi_payment_method_id"] = pm_records[0].id
                else:
                    _logger.warning(
                        "No l10n_mx_edi.payment.method found for '%s'",
                        pm_text,
                    )

            cfdi_use_code = tg_data.get("cfdi_use_code")
            if cfdi_use_code and "l10n_mx_edi_usage" in wizard_fields:
                wizard_vals["l10n_mx_edi_usage"] = cfdi_use_code

        return wizard_vals

    def create_move_from_template_name(
        self,
        runtime_line,
        template_name,
        context_vals=None,
        auto_post=True,
    ) -> models.Model:
        self.check_singleton()

        template = self.env["account.move.template"].search(
            [
                ("name", "=", template_name),
                ("company_id", "in", (self.env.company.id, False)),
            ],
            limit=1,
            order="id",
        )

        if not template:
            raise UserError(
                self.env._("Template with name '%s' not found", template_name),
            )

        return self.create_move_from_template(
            runtime_line,
            template,
            context_vals,
            auto_post,
        )

    def create_payment_from_latest_move(
        self, runtime_line, payment_vals=None
    ) -> models.Model:
        self.check_singleton()
        runtime_line.check_singleton()

        move = runtime_line._get_source_move()
        if not move:
            raise UserError(
                self.env._(
                    "No invoice found in workflow to create payment for. "
                    "Ensure a previous action created an account.move.",
                ),
            )

        _logger.info(
            "Creating payment for move %s (runtime line %s)",
            move.name,
            runtime_line.name,
        )

        return self.create_payment_for_move(runtime_line, move, payment_vals)

    def create_payment_for_move(
        self, runtime_line, move, payment_vals=None
    ) -> models.Model:
        self.check_singleton()
        runtime_line.check_singleton()
        move.check_singleton()

        if move.state != "posted":
            raise UserError(
                self.env._(
                    "Cannot create payment for move %s: it must be posted first.",
                    move.name,
                ),
            )

        runtime = runtime_line.runtime_id

        payment_context = {
            "active_model": "account.move",
            "active_ids": move.ids,
        }

        payment_register = (
            self.env["wizard.account.move.line.pay"]
            .with_context(**payment_context)
            .create(
                {
                    "payment_date": runtime.date,
                    "communication": runtime.reference or move.name,
                },
            )
        )

        if payment_vals:
            allowed_fields = [
                "payment_date",
                "journal_id",
                "communication",
                "amount",
            ]
            wizard_vals = {k: v for k, v in payment_vals.items() if k in allowed_fields}
            if wizard_vals:
                payment_register.write(wizard_vals)

        _logger.info(
            "Creating payment for %s via payment.register wizard (amount: %s)",
            move.name,
            payment_register.amount,
        )

        payment_action = payment_register.action_create_payments()

        if isinstance(payment_action, dict) and payment_action.get("res_id"):
            payment = self.env["account.payment"].browse(payment_action["res_id"])
        else:
            payment = move.reconciled_payment_ids.sorted("id", reverse=True)[:1]

        if not payment:
            raise UserError(
                self.env._(
                    "Failed to create payment for move %s. Payment registration returned unexpected result.",
                    move.name,
                ),
            )

        _logger.info(
            "Payment %s created and automatically reconciled with move %s (residual: %s)",
            payment.name,
            move.name,
            move.amount_residual,
        )

        return payment

    def reconcile_statement_with_latest_move(self, runtime_line) -> bool:
        self.check_singleton()
        runtime_line.check_singleton()

        runtime = runtime_line.runtime_id

        st_line = runtime.st_line_id
        if not st_line:
            raise UserError(
                self.env._(
                    "No bank statement line found in runtime. Set st_line_id on the runtime instance.",
                ),
            )

        move = runtime_line._get_source_move()
        if not move:
            raise UserError(
                self.env._(
                    "No invoice found in workflow to reconcile. Ensure a previous action created an account.move.",
                ),
            )

        return self.reconcile_statement_with_move(runtime_line, st_line, move)

    def reconcile_statement_with_move(self, runtime_line, st_line, move) -> bool:
        self.check_singleton()
        runtime_line.check_singleton()
        st_line.check_singleton()
        move.check_singleton()

        _logger.info(
            "Reconciling bank statement line %s with move %s",
            st_line.payment_ref or st_line.id,
            move.name,
        )

        if move.state != "posted":
            raise UserError(
                self.env._(
                    "Cannot reconcile with move %s: it must be posted first.",
                    move.name,
                ),
            )

        open_lines = move.line_ids.filtered(
            lambda line: (
                line.account_id.account_type
                in ("asset_receivable", "liability_payable")
                and not line.reconciled
            ),
        )

        if not open_lines:
            raise UserError(
                self.env._(
                    "No unreconciled receivable/payable lines found in move %s",
                    move.name,
                ),
            )

        if move.company_id != st_line.company_id:
            bridge = self._reconcile_statement_across_companies(st_line, open_lines)
            if not runtime_line.created_record_ref:
                runtime_line.created_record_ref = f"account.move,{bridge.id}"
            return True

        st_line.set_line_bank_statement_line(open_lines.ids)
        _logger.info(
            "Successfully reconciled bank statement line with move %s",
            move.name,
        )

        return True

    def _reconcile_statement_across_companies(
        self, st_line, open_lines
    ) -> models.Model:
        self.check_singleton()
        st_line.check_singleton()

        move = open_lines.move_id
        receiving = st_line.company_id
        owed = move.company_id

        if set(open_lines.mapped("account_id.account_type")) != {"asset_receivable"}:
            raise UserError(
                self.env._(
                    "%(move)s belongs to %(owed)s, and only a customer collection "
                    "can be settled from another company's bank.",
                    move=move.name,
                    owed=owed.display_name,
                ),
            )
        if receiving.currency_id != owed.currency_id:
            raise UserError(
                self.env._(
                    "%(receiving)s and %(owed)s keep their books in different "
                    "currencies, so a collection cannot be settled between them.",
                    receiving=receiving.display_name,
                    owed=owed.display_name,
                ),
            )

        _liquidity, suspense_lines, _other = st_line._seek_for_lines()
        open_balance = -sum(suspense_lines.mapped("balance"))
        open_amount_currency = -sum(suspense_lines.mapped("amount_currency"))
        currency = suspense_lines.currency_id
        if not suspense_lines or len(currency) != 1:
            raise UserError(
                self.env._(
                    "Bank statement line %s has nothing left to reconcile.",
                    st_line.payment_ref or st_line.display_name,
                ),
            )
        if receiving.currency_id.compare_amounts(open_balance, 0) <= 0:
            raise UserError(
                self.env._(
                    "Bank statement line %s is not a collection: only money "
                    "coming in can be settled for another company.",
                    st_line.payment_ref or st_line.display_name,
                ),
            )

        journal = owed.automation_intercompany_journal_id
        if not journal:
            raise UserError(
                self.env._(
                    "Set an Intercompany Collection Journal on %(owed)s "
                    "(Settings > Companies, Accounting Workflows tab) before "
                    "settling a collection that %(receiving)s received.",
                    owed=owed.display_name,
                    receiving=receiving.display_name,
                ),
            )
        owed_to = owed.partner_id.with_company(receiving).property_account_payable_id
        if not owed_to:
            raise UserError(
                self.env._(
                    "Contact %(partner)s has no payable account in %(receiving)s. "
                    "Set one on its Accounting tab while working in %(receiving)s.",
                    partner=owed.partner_id.display_name,
                    receiving=receiving.display_name,
                ),
            )
        owed_by = receiving.partner_id.with_company(owed).property_account_receivable_id
        if not owed_by:
            raise UserError(
                self.env._(
                    "Contact %(partner)s has no receivable account in %(owed)s. "
                    "Set one on its Accounting tab while working in %(owed)s.",
                    partner=receiving.partner_id.display_name,
                    owed=owed.display_name,
                ),
            )

        label = st_line.payment_ref or st_line.display_name
        st_line.with_company(receiving)._add_move_line_to_statement_line_move(
            [
                {
                    "name": label,
                    "account_id": owed_to.id,
                    "partner_id": owed.partner_id.id,
                    "balance": -open_balance,
                    "amount_currency": -open_amount_currency,
                    "currency_id": currency.id,
                },
            ],
        )

        customer_account = open_lines.account_id[:1]
        customer = move.commercial_partner_id
        bridge = (
            self.env["account.move"]
            .with_company(owed)
            .create(
                {
                    "move_type": "entry",
                    "journal_id": journal.id,
                    "date": st_line.date,
                    "ref": label,
                    "company_id": owed.id,
                    "line_ids": [
                        Command.create(
                            {
                                "name": label,
                                "account_id": owed_by.id,
                                "partner_id": receiving.partner_id.id,
                                "balance": open_balance,
                                "amount_currency": open_amount_currency,
                                "currency_id": currency.id,
                            },
                        ),
                        Command.create(
                            {
                                "name": label,
                                "account_id": customer_account.id,
                                "partner_id": customer.id,
                                "balance": -open_balance,
                                "amount_currency": -open_amount_currency,
                                "currency_id": currency.id,
                            },
                        ),
                    ],
                },
            )
        )
        bridge.action_post()

        settled = bridge.line_ids.filtered(
            lambda line: (
                line.account_id == customer_account
                and line.partner_id == customer
                and line.balance < 0
            ),
        )
        (
            settled
            | open_lines.filtered(lambda line: line.account_id == customer_account)
        ).reconcile()

        _logger.info(
            "Settled bank statement line %s of %s against %s of %s through %s",
            label,
            receiving.name,
            move.name,
            owed.name,
            bridge.name,
        )
        return bridge

    def reconcile_latest_move_with_open_invoices(self, runtime_line) -> models.Model:
        self.check_singleton()
        runtime_line.check_singleton()

        move = runtime_line._get_source_move()
        if not move:
            raise UserError(
                self.env._(
                    "No credit note found in workflow to apply. Ensure a previous action created an account.move.",
                ),
            )

        return self.reconcile_move_with_open_invoices(
            runtime_line,
            move,
            target=runtime_line._get_target_move(),
        )

    def reconcile_move_with_open_invoices(
        self,
        runtime_line,
        move,
        target=None,
    ) -> models.Model:
        self.check_singleton()
        runtime_line.check_singleton()
        move.check_singleton()

        if move.state != "posted":
            raise UserError(
                self.env._(
                    "Cannot apply %s to open invoices: it must be posted first.",
                    move.name,
                ),
            )

        if move.move_type not in ("out_refund", "in_refund"):
            raise UserError(
                self.env._(
                    "Cannot apply %s to open invoices: it is not a credit note.",
                    move.display_name,
                ),
            )

        is_customer = move.move_type == "out_refund"
        account_type = "asset_receivable" if is_customer else "liability_payable"
        refund_lines = move.line_ids.filtered(
            lambda line: (
                line.account_id.account_type == account_type and not line.reconciled
            ),
        )
        invoices = self.env["account.move"]
        if not refund_lines:
            _logger.info("Credit note %s has nothing left to apply", move.name)
            return invoices

        if target and target.state != "posted":
            raise UserError(
                self.env._(
                    "%(credit)s is applied to %(target)s only once it is "
                    "posted: post it and retry the run.",
                    credit=move.name,
                    target=target.display_name,
                ),
            )

        invoice_type = "out_invoice" if is_customer else "in_invoice"
        invoice_lines = self.env["account.move.line"].search(
            Domain.AND(
                [
                    [
                        ("account_id", "in", refund_lines.account_id.ids),
                        ("partner_id", "=", move.commercial_partner_id.id),
                        ("parent_state", "=", "posted"),
                        ("reconciled", "=", False),
                        ("move_id.move_type", "=", invoice_type),
                        "|",
                        ("amount_residual", "!=", 0.0),
                        ("amount_residual_currency", "!=", 0.0),
                    ],
                    [("move_id", "=", target.id)] if target else [],
                    move._get_outstanding_company_domain(move.company_id),
                ],
            ),
            order="date, move_name, date_maturity, id",
        )
        if target and not invoice_lines:
            raise UserError(
                self.env._(
                    "%(credit)s cannot be applied to %(target)s: it has nothing "
                    "open for %(partner)s on the credit note's account.",
                    credit=move.name,
                    target=target.display_name,
                    partner=move.commercial_partner_id.display_name,
                ),
            )

        for invoice_line in invoice_lines:
            if all(refund_lines.mapped("reconciled")):
                break
            move.js_add_outstanding_line(invoice_line.id)
            invoices |= invoice_line.move_id

        _logger.info(
            "Applied credit note %s to %d invoice(s) (%s); open credit left: %s",
            move.name,
            len(invoices),
            ", ".join(invoices.mapped("name")) or "-",
            move.amount_residual,
        )

        return invoices

    def mark_action_done_and_continue(self, runtime_line) -> bool:
        self.check_singleton()
        runtime_line.check_singleton()

        runtime_line.action_mark_done()
        return runtime_line.runtime_id.state != "done"

    def get_runtime_context_value(self, runtime_line, field_name, default=None) -> Any:
        self.check_singleton()
        runtime_line.check_singleton()

        runtime = runtime_line.runtime_id

        if field_name in runtime._fields:
            return runtime[field_name]

        return default

    def _get_workflow_line(self) -> models.Model:
        self.check_singleton()
        line = (
            self.env["automation.runtime.line"]
            .browse(self.env.context.get("runtime_line_id"))
            .exists()
        )
        if not line:
            raise UserError(
                self.env._(
                    "Step '%(step)s' only runs as part of a workflow run.",
                    step=self.name,
                ),
            )
        return line

    def _get_workflow_company(self, runtime) -> models.Model:
        self.check_singleton()
        if self.workflow_company_source == "statement":
            return runtime._get_vehicle_company()
        if self.workflow_company_source == "template":
            return (
                self.workflow_template_id.company_id
                or runtime._get_transaction_company()
            )
        return runtime._get_transaction_company()

    def _get_workflow_partner(self, runtime) -> models.Model:
        self.check_singleton()
        if self.workflow_partner_source == "third_party":
            return runtime.third_party_id or runtime.partner_id
        return runtime.partner_id

    def _get_workflow_taxes(self, company) -> models.Model:
        self.check_singleton()
        Tax = self.env["account.tax"].with_company(company)
        company_domain = Tax._get_domain_company_compatible(company)
        own = self.workflow_tax_ids.filtered_domain(company_domain)
        foreign = self.workflow_tax_ids - own
        namesakes = Tax.search(
            [*company_domain, ("name", "in", foreign.mapped("name"))],
        )
        taxes = Tax.browse()
        for tax in self.workflow_tax_ids:
            match = (
                tax
                if tax in own
                else namesakes.filtered(
                    lambda candidate, tax=tax: (
                        candidate.name == tax.name
                        and candidate.type_tax_use == tax.type_tax_use
                        and candidate.amount_type == tax.amount_type
                        and candidate.amount == tax.amount
                    ),
                )[:1]
            )
            if not match:
                raise UserError(
                    self.env._(
                        "Step '%(step)s' replaces the taxes with '%(tax)s', "
                        "which %(company)s does not have.",
                        step=self.name,
                        tax=tax.name,
                        company=company.name,
                    ),
                )
            taxes |= match
        return taxes

    def _acts_on_a_document(self) -> bool:
        self.check_singleton()
        return self.state in ACTS_ON_STATES or (
            self.state == "workflow_create_document"
            and self.workflow_date_source == "document"
        )

    @api.depends(
        *STEP_REFERENCE_DEPENDS,
        "workflow_date_source",
        "workflow_source_step_id",
        "workflow_target_step_id",
    )
    def _compute_step_reference_warning(self) -> None:
        return super()._compute_step_reference_warning()

    @api.depends(
        "automation_rule_id",
        "code",
        "state",
        "workflow_source_step_id",
        "workflow_source_step_id.step_key",
        "workflow_target_step_id",
        "workflow_target_step_id.step_key",
    )
    def _compute_step_references(self) -> None:
        return super()._compute_step_references()

    def _collect_step_references(self):
        refs = super()._collect_step_references()
        if self.workflow_source_step_id.step_key:
            refs.keys.add(self.workflow_source_step_id.step_key)
        if (
            self.state == "workflow_apply_credit_note"
            and self.workflow_target_step_id.step_key
        ):
            refs.keys.add(self.workflow_target_step_id.step_key)
        return refs

    def _get_nearest_document_steps(self, seen=None) -> models.Model:
        self.check_singleton()
        seen = self.browse() if seen is None else seen
        found = self.browse()
        for predecessor in self._get_predecessors() - seen:
            seen |= predecessor
            if predecessor.state in DOCUMENT_STATES:
                found |= predecessor
            else:
                found |= predecessor._get_nearest_document_steps(seen)
        return found

    def _get_step_reference_problems(self) -> list[str]:
        problems = super()._get_step_reference_problems()
        if not self._acts_on_a_document():
            return problems
        source = self.workflow_source_step_id
        if source and source.state not in (*DOCUMENT_STATES, "code"):
            problems.append(
                self.env._(
                    "Step '%(step)s' acts on the document of '%(source)s', "
                    "which makes none.",
                    step=self.name,
                    source=source.name,
                )
            )
        target = self.workflow_target_step_id
        if (
            self.state == "workflow_apply_credit_note"
            and target
            and target.state not in (*DOCUMENT_STATES, "code")
        ):
            problems.append(
                self.env._(
                    "Step '%(step)s' applies against the document of "
                    "'%(target)s', which makes none.",
                    step=self.name,
                    target=target.name,
                )
            )
        if not source:
            candidates = self._get_nearest_document_steps()
            if len(candidates) > 1:
                problems.append(
                    self.env._(
                        "Step '%(step)s' could act on the document of %(steps)s, "
                        "on different branches before it. Name the one in its "
                        "Acts On.",
                        step=self.name,
                        steps=", ".join(f"'{step.name}'" for step in candidates),
                    )
                )
        return problems

    def _get_workflow_document_step(self) -> models.Model:
        self.check_singleton()
        if self.workflow_source_step_id:
            return self.workflow_source_step_id
        seen = self.browse()
        frontier = self._get_predecessors()
        while frontier:
            documents = frontier.filtered(
                lambda step: step.state == "workflow_create_document",
            )
            if documents:
                return documents[:1]
            seen |= frontier
            frontier = frontier._get_predecessors() - seen
        return self.browse()

    def _get_workflow_step_summary(self, runtime) -> str:
        self.check_singleton()
        if self.state == "workflow_create_document":
            template = self.workflow_template_id
            move_types = dict(
                self.env["account.move"]
                ._fields["move_type"]
                ._description_selection(self.env),
            )
            return self.env._(
                "%(document)s in %(journal)s of %(company)s, issued to %(partner)s",
                document=(
                    self.env._("Payment")
                    if template.is_payment
                    else move_types.get(template.move_type, template.move_type)
                ),
                journal=template.journal_code,
                company=self._get_workflow_company(runtime).name,
                partner=self._get_workflow_partner(runtime).display_name
                or self.env._("nobody"),
            )
        if self.state == "workflow_change_partner":
            return self.env._(
                "The document before it, issued again to %(partner)s",
                partner=self._get_workflow_partner(runtime).display_name
                or self.env._("nobody"),
            )
        if self.state in STATEMENT_STATES:
            return runtime.st_line_id.display_name or ""
        return ""

    def _get_workflow_problems(self, runtime) -> list[str]:
        self.check_singleton()
        problems = []
        if self.state in STATEMENT_STATES and not runtime.st_line_id:
            problems.append(
                self.env._(
                    "'%(step)s' needs a bank statement line, and this run names none.",
                    step=self.name,
                ),
            )
        if self.state == "workflow_reconcile_statement" and runtime.st_line_id:
            document_step = self._get_workflow_document_step()
            company = (
                document_step._get_workflow_company(runtime)
                if document_step
                else runtime.st_line_id.company_id
            )
            if (
                company != runtime.st_line_id.company_id
                and not company.automation_intercompany_journal_id
            ):
                problems.append(
                    self.env._(
                        "'%(step)s' settles a bank statement line of "
                        "%(line_company)s against the document '%(document)s' "
                        "creates in %(company)s, and %(company)s has no "
                        "Intercompany Collection Journal.",
                        step=self.name,
                        line_company=runtime.st_line_id.company_id.name,
                        document=document_step.name,
                        company=company.name,
                    ),
                )
        if self.state == "workflow_change_partner" and not (
            self._get_workflow_partner(runtime)
        ):
            problems.append(
                self.env._(
                    "'%(step)s' issues a document again to a partner, and this "
                    "run names none.",
                    step=self.name,
                ),
            )
        if self.state != "workflow_create_document":
            return problems

        template = self.workflow_template_id
        company = self._get_workflow_company(runtime)
        if not self._get_workflow_partner(runtime):
            problems.append(
                self.env._(
                    "'%(step)s' issues its document to a partner, and this "
                    "run names none.",
                    step=self.name,
                ),
            )
        if not self.env["account.journal"].search_count(
            [
                ("code", "=", template.journal_code),
                ("company_id", "=", company.id),
            ],
            limit=1,
        ):
            problems.append(
                self.env._(
                    "'%(step)s' creates its document in journal %(journal)s, "
                    "which %(company)s does not have.",
                    step=self.name,
                    journal=template.journal_code,
                    company=company.name,
                ),
            )
        if template.is_payment and not runtime.amount:
            problems.append(
                self.env._(
                    "'%(step)s' creates a payment, and this run has no amount.",
                    step=self.name,
                ),
            )
        try:
            self._get_workflow_taxes(company)
        except UserError as error:
            problems.append(str(error))
        return problems

    def _workflow_step_detail(self):
        if self.state == "workflow_change_partner":
            return self.env._(
                "To: %(partner)s",
                partner=dict(
                    self._fields["workflow_partner_source"]._description_selection(
                        self.env
                    ),
                ).get(self.workflow_partner_source, ""),
            )
        if self.state != "workflow_create_document":
            return super()._workflow_step_detail()
        sources = {
            field_name: dict(
                self._fields[field_name]._description_selection(self.env),
            ).get(self[field_name], "")
            for field_name in ("workflow_company_source", "workflow_partner_source")
        }
        template = self.workflow_template_id._visible_display_names().get(
            self.workflow_template_id.id
        )
        if not template:
            return super()._workflow_step_detail()
        return self.env._(
            "%(template)s. In: %(company)s. To: %(partner)s",
            template=template,
            company=sources["workflow_company_source"],
            partner=sources["workflow_partner_source"],
        )

    def _run_action_workflow_register_statement(self, eval_context=None) -> None:
        line = self._get_workflow_line()
        st_line = line.runtime_id.st_line_id
        if not st_line:
            raise UserError(
                self.env._(
                    "No bank statement line found in runtime. Set st_line_id on the runtime instance.",
                ),
            )
        if not st_line.move_id:
            raise UserError(
                self.env._(
                    "Bank statement line %(line)s has no journal entry yet.",
                    line=st_line.display_name,
                ),
            )
        line.write({"created_record_ref": f"account.move,{st_line.move_id.id}"})
        line._set_output(
            {
                "amount": st_line.amount,
                "date": st_line.date.isoformat(),
                "partner": st_line.partner_id.display_name or "",
            },
            self.env._(
                "%(amount)s received on %(date)s",
                amount=format_amount(self.env, st_line.amount, st_line.currency_id),
                date=format_date(self.env, st_line.date),
            ),
        )

    def _run_action_workflow_create_document(self, eval_context=None) -> None:
        line = self._get_workflow_line()
        runtime = line.runtime_id
        company = self._get_workflow_company(runtime)
        context_vals = {
            "partner_id": self._get_workflow_partner(runtime).id,
            "third_party_id": False,
            "multicompany_id": company.id,
        }
        if self.workflow_date_source == "document":
            context_vals["use_latest_document_date"] = True
        elif self.workflow_date_source == "statement":
            context_vals["date"] = runtime.st_line_id.date or runtime.date
        elif self.workflow_date_source == "today":
            context_vals["date"] = fields.Date.context_today(self)

        document = self.create_move_from_template(
            line,
            self.workflow_template_id,
            context_vals,
            auto_post=False,
        )
        if self.workflow_tax_ids and document._name == "account.move":
            taxes = self._get_workflow_taxes(company)
            document.invoice_line_ids.write({"tax_ids": [Command.set(taxes.ids)]})
        if self.workflow_auto_post and document.state == "draft":
            document.action_post()
        line.write({"created_record_ref": f"{document._name},{document.id}"})
        amount = (
            document.amount_total
            if document._name == "account.move"
            else document.amount
        )
        partner = document.partner_id.display_name or ""
        line._set_output(
            {
                "document": document.display_name,
                "amount": amount,
                "partner": partner,
                "company": document.company_id.name,
            },
            self.env._(
                "%(document)s for %(amount)s, issued to %(partner)s",
                document=document.display_name,
                amount=format_amount(self.env, amount, document.currency_id),
                partner=partner,
            ),
        )

    def _run_action_workflow_change_partner(self, eval_context=None) -> None:
        line = self._get_workflow_line()
        move = line._get_source_move()
        if not move:
            raise UserError(
                self.env._(
                    "'%(step)s' found no document of an earlier step to issue again.",
                    step=self.name,
                ),
            )
        partner = self._get_workflow_partner(line.runtime_id)
        if not partner:
            raise UserError(
                self.env._(
                    "'%(step)s' issues %(document)s again to a partner, and the "
                    "run names none.",
                    step=self.name,
                    document=move.display_name,
                ),
            )
        changed = move.partner_id != partner
        if changed:
            self._change_move_partner(move, partner)
        line.write({"created_record_ref": f"account.move,{move.id}"})
        line._set_output(
            {
                "document": move.name,
                "partner": partner.display_name,
                "changed": changed,
            },
            self.env._(
                "%(document)s issued to %(partner)s",
                document=move.name,
                partner=partner.display_name,
            )
            if changed
            else self.env._(
                "%(document)s was already issued to %(partner)s",
                document=move.name,
                partner=partner.display_name,
            ),
        )

    def _change_move_partner(self, move, partner) -> None:
        self.check_singleton()
        applied = move.line_ids.filtered(
            lambda line: (
                line.account_id.account_type in OPEN_ITEM_TYPES
                and (line.matched_debit_ids or line.matched_credit_ids)
            ),
        )
        if applied:
            raise UserError(
                self.env._(
                    "%(document)s is already applied to other documents. Remove "
                    "what it settles before issuing it to %(partner)s.",
                    document=move.display_name,
                    partner=partner.display_name,
                ),
            )
        posted = move.state == "posted"
        if posted:
            move.action_draft()
        move.partner_id = partner
        if posted:
            move.action_post()

    @api.model
    def _get_open_amount(self, move) -> float:
        lines = move.line_ids.filtered(
            lambda line: line.account_id.account_type in OPEN_ITEM_TYPES,
        )
        lines.invalidate_recordset(["amount_residual"])
        return move.currency_id.round(abs(sum(lines.mapped("amount_residual"))))

    def _run_action_workflow_reconcile_statement(self, eval_context=None) -> None:
        line = self._get_workflow_line()
        move = line._get_source_move()
        open_before = self._get_open_amount(move) if move else 0.0
        self.reconcile_statement_with_latest_move(line)
        still_open = self._get_open_amount(move)
        settled = move.currency_id.round(open_before - still_open)
        line._set_output(
            {"document": move.name, "settled": settled, "open": still_open},
            self.env._(
                "Settled %(amount)s of %(document)s",
                amount=format_amount(self.env, settled, move.currency_id),
                document=move.name,
            ),
        )

    def _run_action_workflow_apply_credit_note(self, eval_context=None) -> None:
        line = self._get_workflow_line()
        move = line._get_source_move()
        open_before = self._get_open_amount(move) if move else 0.0
        invoices = self.reconcile_latest_move_with_open_invoices(line)
        open_credit = self._get_open_amount(move)
        applied = move.currency_id.round(open_before - open_credit)
        currency = move.currency_id
        line.write({"created_record_ref": f"account.move,{move.id}"})
        line._set_output(
            {
                "credit_note": move.name,
                "applied": applied,
                "invoices": invoices.mapped("name"),
                "open_credit": open_credit,
            },
            self.env._(
                "Applied %(amount)s to %(invoices)s; open credit %(credit)s",
                amount=format_amount(self.env, applied, currency),
                invoices=", ".join(invoices.mapped("name")),
                credit=format_amount(self.env, open_credit, currency),
            )
            if invoices
            else self.env._(
                "Nothing to apply; open credit %(credit)s",
                credit=format_amount(self.env, open_credit, currency),
            ),
        )
