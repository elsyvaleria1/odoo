from typing import Any

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import clean_context


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    _PAYMENT_FIELDS = frozenset({"payment_state", "payment_date", "paid_by_user_id"})
    _access_verbs = {
        "mark_paid": models.Verb(
            requires="read",
            methods=("action_mark_paid", "action_mark_not_paid"),
        ),
    }

    has_bsl = fields.Selection(
        related="category_id.has_bsl",
        string="Bank Statement Line Requirement",
    )
    has_journal = fields.Selection(related="category_id.has_journal")
    account_move_type = fields.Selection(related="category_id.account_move_type")
    journal_type = fields.Selection(
        selection=[("sale", "Sale"), ("purchase", "Purchase")],
        compute="_compute_journal_type",
        help="Computed journal type based on account move type for filtering.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        domain="[('type', '=', journal_type)] if journal_type else []",
    )
    bank_statement_date = fields.Date(
        compute="_compute_bank_statement_date",
        help="First date a matching bank statement line may carry: the date "
        "part of the request's own date.",
    )
    bank_statement_settlement_days = fields.Integer(
        compute="_compute_bank_statement_settlement_days",
        help="How many days after the request date the bank may still settle "
        "this payment. Zero here, because this module does not know how the "
        "payment was made; a module that knows overrides the compute.",
    )
    bank_statement_date_end = fields.Date(
        compute="_compute_bank_statement_date_end",
        help="Last date a matching bank statement line may carry: the request "
        "date plus the settlement days.",
    )
    include_reconciled_bsl = fields.Boolean(
        string="Include already-reconciled transactions",
        help="Opt-in: allow selecting a bank statement line that is already "
        "reconciled, for payments processed outside the approval flow. "
        "Off by default, so the picker shows only unreconciled lines.",
    )
    bank_statement_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        index="btree_not_null",
        domain="[('date', '>=', bank_statement_date), ('date', '<=', bank_statement_date_end), '|', ('amount', '=', amount), ('amount', '=', -amount), '|', ('is_reconciled', '=', False), ('is_reconciled', '=', include_reconciled_bsl), '|', ('id', '=', bank_statement_line_id), ('approval_request_ids', 'not any', [('state', 'not in', ('refused', 'cancelled'))])]",
        help="Select the bank transaction that corresponds to this payment. "
        "The amount is matched on its absolute value: an outgoing payment "
        "appears as a negative statement line.",
    )
    account_move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="approval_request_id",
        string="Approved Invoices/Bills",
        help="Invoices and bills that carry this request as their approval — "
        "the mixin flow. Documents this request CREATED are reached through "
        "line_ids instead.",
    )
    count_account_move = fields.Integer(compute="_compute_count_account_move")
    payment_state = fields.Selection(
        selection=[("not_paid", "Not Paid"), ("paid", "Paid")],
        default="not_paid",
        copy=False,
        tracking=True,
        help="Whether the underlying payment for this approved request has "
        "actually been made. Independent from `state` — approval and "
        "payment are tracked separately.",
    )
    payment_date = fields.Date(
        copy=False,
        help="Date the request was marked paid. Cleared when reverted to Not Paid.",
    )
    paid_by_user_id = fields.Many2one(
        comodel_name="res.users",
        copy=False,
        help="User who marked this request as paid (manually or via bank "
        "reconciliation).",
    )
    is_payable = fields.Boolean(
        compute="_compute_is_payable",
        store=True,
        help="True when this request's category is Accounting/Payment and "
        "its amount is positive — i.e. it belongs in the Treasury payment "
        "queue.",
    )

    _bank_statement_line_live_uniq = models.UniqueIndex(
        "(bank_statement_line_id) WHERE (bank_statement_line_id IS NOT NULL "
        "AND state NOT IN ('refused', 'cancelled'))",
        "This bank transaction is already assigned to another live approval "
        "request. Refuse or cancel that request first, or pick another "
        "transaction.",
    )

    def _check_bank_statement_line_available(
        self,
        line_id: int,
        exclude: models.BaseModel | None = None,
    ) -> None:
        domain = [
            ("bank_statement_line_id", "=", line_id),
            ("state", "not in", ("refused", "cancelled")),
        ]
        if exclude is not None:
            domain.append(("id", "!=", exclude.id))
        clash = self.sudo().search(domain, limit=1)
        if clash:
            line = self.env["account.bank.statement.line"].sudo().browse(line_id)
            raise ValidationError(
                self.env._(
                    "Bank transaction %(line)s is already assigned to "
                    "approval request %(request)s. Refuse or cancel "
                    "that request first, or pick another transaction.",
                    line=line.display_name,
                    request=clash.display_name,
                ),
            )

    @api.model_create_multi
    def create(self, vals_list):
        seen_line_ids: set[int] = set()
        for vals in vals_list:
            # Same gate write() applies. Without it the treasury seal is only
            # half enforced: a request cannot be marked paid, but it can be
            # created already paid, which is the same thing arrived at from
            # the other side.
            self._check_payment_fields_access(vals)
            line_id = vals.get("bank_statement_line_id")
            if not line_id:
                continue
            if line_id in seen_line_ids:
                raise ValidationError(
                    self.env._(
                        "Two requests in this batch claim the same bank "
                        "transaction — a bank line can only be assigned "
                        "to one live approval request.",
                    ),
                )
            seen_line_ids.add(line_id)
            self._check_bank_statement_line_available(line_id)
        return super().create(vals_list)

    def write(self, vals):
        self._check_payment_fields_access(vals)
        line_id = vals.get("bank_statement_line_id")
        if line_id:
            if len(self) > 1:
                raise ValidationError(
                    self.env._(
                        "Cannot assign the same bank transaction to "
                        "%(count)d requests at once — a bank line can only be "
                        "assigned to one live approval request.",
                        count=len(self),
                    ),
                )
            if self:
                # The guard above leaves at most one record here.
                self._check_bank_statement_line_available(line_id, exclude=self)
        return super().write(vals)

    def _check_payment_fields_access(self, vals: dict) -> None:
        if self._PAYMENT_FIELDS & set(vals) and not self.env.su:
            self.browse().check_access("mark_paid")

    def action_mark_paid(self) -> None:
        to_mark = self.filtered(
            lambda r: r.state == "approved" and r.payment_state != "paid",
        )
        if to_mark:
            to_mark.sudo().write(
                {
                    "payment_state": "paid",
                    "payment_date": fields.Date.context_today(self),
                    "paid_by_user_id": self.env.user.id,
                },
            )

    def action_mark_not_paid(self) -> None:
        to_unmark = self.filtered(lambda r: r.payment_state != "not_paid")
        if to_unmark:
            to_unmark.sudo().write(
                {
                    "payment_state": "not_paid",
                    "payment_date": False,
                    "paid_by_user_id": False,
                },
            )

    @api.depends("approval_type", "amount")
    def _compute_is_payable(self) -> None:
        for request in self:
            request.is_payable = (
                request.approval_type in ("accounting", "payment")
                and request.amount > 0
            )

    @api.depends("account_move_type", "res_model", "res_id")
    def _compute_journal_type(self) -> None:
        for record in self:
            move_type = record._get_source_move_type() or record.account_move_type
            if move_type in ("in_invoice", "in_refund"):
                record.journal_type = "purchase"
            elif move_type in ("out_invoice", "out_refund"):
                record.journal_type = "sale"
            else:
                record.journal_type = False

    def _get_source_move_type(self) -> str:
        self.check_singleton()
        if self.res_model != "account.move" or not self.res_id:
            return ""
        move = self.env["account.move"].sudo().browse(self.res_id).exists()
        return move.move_type or ""

    @api.depends("date", "has_bsl")
    def _compute_bank_statement_date(self) -> None:
        for record in self:
            if record.has_bsl == "no" or not record.has_bsl or not record.date:
                record.bank_statement_date = False
            else:
                record.bank_statement_date = record.date

    @api.depends("has_bsl")
    def _compute_bank_statement_settlement_days(self) -> None:
        for record in self:
            record.bank_statement_settlement_days = 0

    @api.depends("bank_statement_date", "bank_statement_settlement_days")
    def _compute_bank_statement_date_end(self) -> None:
        for record in self:
            if not record.bank_statement_date:
                record.bank_statement_date_end = False
            else:
                record.bank_statement_date_end = fields.Date.add(
                    record.bank_statement_date,
                    days=record.bank_statement_settlement_days,
                )

    @api.depends("line_ids.account_move_id", "account_move_ids")
    def _compute_count_account_move(self) -> None:
        for request in self:
            move_ids = set(request.sudo().line_ids.account_move_line_id.move_id.ids)
            move_ids |= set(request.sudo().account_move_ids.ids)
            request.count_account_move = len(move_ids)

    def _get_all_account_moves(self):
        return self._get_documents_of_model(
            "account.move",
            "account_move_line_id",
            "move_id",
        )

    def _account_moves_by_request(self) -> dict[int, models.BaseModel]:
        """``_get_all_account_moves()`` for a whole recordset, in one search.

        ``_get_documents_of_model`` is ``check_singleton()`` by contract and
        searches once per record, which is right for the singleton callers and
        wrong for a bulk action holding a week of requests. That helper belongs
        to ``approval_product`` and is left alone; this is the batched reading
        of the same two halves -- the lines, which traverse, and the mixin
        link, which needs the one search this does up front.
        """
        empty = self.env["account.move"]
        persisted = self.filtered(lambda request: request._origin.id)
        from_mixin: dict[int, Any] = {}
        if persisted:
            found = (
                self.env["account.move"]
                .sudo()
                .search([("approval_request_id", "in", persisted._origin.ids)])
            )
            for move in found:
                key = move.approval_request_id.id
                from_mixin[key] = from_mixin.get(key, empty) | move
        return {
            request.id: (
                request.line_ids.account_move_line_id.move_id
                | from_mixin.get(request._origin.id, empty)
            )
            for request in self.sudo()
        }

    def action_approve(
        self,
        approver: models.BaseModel | None = None,
        steps: models.BaseModel | None = None,
    ) -> dict[str, Any] | None:
        self._check_accounting_type_has_product()
        self._check_bank_statement_line_required()
        return super().action_approve(approver, steps)

    def action_create_account_moves(self) -> dict[str, Any]:
        return self.action_create_target_documents()

    def action_view_target_documents(self) -> dict[str, Any]:
        if self._is_account_target():
            return self.action_view_account_move()
        return super().action_view_target_documents()

    def action_create_account_moves_bulk(self) -> dict[str, Any]:
        """Create the journal entries of every eligible request in ``self``.

        Bound to the list view so a week of approved requests can be
        invoiced in one click. A request is eligible when it is approved,
        targets ``account.move``, carries lines and has no move yet; the
        others are left untouched and counted in the closing notification.
        Creation is atomic: a failure on one request rolls back the batch,
        so a half-invoiced selection never has to be sorted out by hand.
        """
        moves_by_request = self._account_moves_by_request()
        eligible = self.filtered(
            lambda request: (
                request.state == "approved"
                and request._is_account_target()
                and request.line_ids
                and not moves_by_request.get(request.id)
            ),
        )
        if not eligible:
            raise UserError(
                self.env._(
                    "None of the selected requests can be invoiced. A request "
                    "must be approved, target journal entries, have lines and "
                    "not have been invoiced already.",
                ),
            )

        created_moves = self.env["account.move"]
        for request in eligible:
            request._create_target_documents()
            request._log_target_creation_to_chatter()
        # Eligibility already required that these carried no move, so whatever
        # they carry now is what this run created. One search for the batch.
        for moves in eligible._account_moves_by_request().values():
            created_moves |= moves

        skipped = len(self) - len(eligible)
        message = self.env._(
            "%(moves)s journal entries created from %(requests)s requests.",
            moves=len(created_moves),
            requests=len(eligible),
        )
        if skipped:
            message += " " + self.env._(
                "%(skipped)s selected requests were skipped: not approved, "
                "already invoiced or without lines.",
                skipped=skipped,
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Journal Entries"),
                "message": message,
                "type": "success",
                "sticky": bool(skipped),
                "next": self._get_account_moves_action(created_moves),
            },
        }

    def action_view_account_move(self) -> dict[str, Any]:
        self.check_singleton()
        return self._get_account_moves_action(self._get_all_account_moves())

    def _get_account_moves_action(self, all_moves: models.BaseModel) -> dict[str, Any]:
        if len(all_moves) == 1:
            return {
                "name": all_moves.display_name,
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "res_id": all_moves.id,
                "view_mode": "form",
                # Spelled out because this dict also travels as the `next` of
                # a display_notification, where the button controller does not
                # normalise `views` and the client dies on `views.map`.
                "views": [(False, "form")],
                "context": clean_context(self.env.context),
            }

        move_types = all_moves.mapped("move_type")
        unique_types = set(move_types)

        if not unique_types:
            action_name = self.env._("Journal Entries")
            list_view_ref = "account.view_move_tree"
        elif unique_types == {"in_invoice"}:
            action_name = self.env._("Vendor Bills")
            list_view_ref = "account.view_in_invoice_bill_tree"
        elif unique_types == {"out_invoice"}:
            action_name = self.env._("Customer Invoices")
            list_view_ref = "account.view_out_invoice_tree"
        elif unique_types == {"in_refund"}:
            action_name = self.env._("Vendor Credit Notes")
            list_view_ref = "account.view_in_invoice_refund_tree"
        elif unique_types == {"out_refund"}:
            action_name = self.env._("Customer Credit Notes")
            list_view_ref = "account.view_out_credit_note_tree"
        elif unique_types <= {"in_invoice", "in_refund"}:
            action_name = self.env._("Vendor Bills & Credit Notes")
            list_view_ref = "account.view_in_invoice_bill_tree"
        elif unique_types <= {"out_invoice", "out_refund"}:
            action_name = self.env._("Customer Invoices & Credit Notes")
            list_view_ref = "account.view_out_invoice_tree"
        else:
            action_name = self.env._("Journal Entries")
            list_view_ref = "account.view_move_tree"

        list_view_id = self.env.ref(list_view_ref).id

        return {
            "name": action_name,
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "views": [(list_view_id, "list"), (False, "form")],
            "context": clean_context(self.env.context),
            "domain": [("id", "in", all_moves.ids)],
        }

    def _is_account_target(self) -> bool:
        return self.target_model == "account.move"

    def _get_target_line_field(self) -> str:
        if self._is_account_target():
            return "account_move_line_id"
        return super()._get_target_line_field()

    def _get_target_line_parent_field(self) -> str:
        if self._is_account_target():
            return "move_id"
        return super()._get_target_line_parent_field()

    def _get_target_line_quantity_field(self) -> str:
        if self._is_account_target():
            return "quantity"
        return super()._get_target_line_quantity_field()

    def _get_target_document_name(self) -> str:
        if self._is_account_target():
            return self.env._("Journal Entries")
        return super()._get_target_document_name()

    def _get_target_document_label(self) -> str:
        if self._is_account_target():
            return self.env._("journal entry")
        return super()._get_target_document_label()

    def _get_target_log_label(self) -> str:
        if self._is_account_target():
            return self.env._("invoices/bills")
        return super()._get_target_log_label()

    def _get_target_log_prefix(self) -> str:
        if self._is_account_target():
            return self.env._("Invoice/Bill ")
        return super()._get_target_log_prefix()

    def _is_target_rollback_enabled(self) -> bool:
        if self._is_account_target():
            return True
        return super()._is_target_rollback_enabled()

    def _is_target_recreation_silent(self) -> bool:
        if self._is_account_target():
            return True
        return super()._is_target_recreation_silent()

    def _get_target_document_removable_lines(self, document):
        if self._is_account_target():
            return document.line_ids.filtered("product_id")
        return super()._get_target_document_removable_lines(document)

    def _remove_target_document(self, document) -> None:
        if self._is_account_target():
            document.unlink()
            return
        super()._remove_target_document(document)

    def _is_target_line_creatable(self, line) -> bool:
        if self._is_account_target():
            return bool(line.product_id)
        return super()._is_target_line_creatable(line)

    def _get_target_document_context(self) -> dict[str, Any]:
        if self._is_account_target():
            return clean_context(self.env.context)
        return super()._get_target_document_context()

    def _get_target_move_type(self) -> str:
        return self.category_id.account_move_type or "in_invoice"

    def _check_target_prerequisites(self, lines) -> None:
        super()._check_target_prerequisites(lines)
        if self._is_account_target() and self._get_target_move_type() == "entry":
            raise UserError(
                self.env._(
                    "General journal entries are not supported in creation flow.\n"
                    "Only invoices and bills can be created from approval requests.",
                ),
            )

    def _prepare_target_document_values(self, key, lines) -> dict[str, Any]:
        if not self._is_account_target():
            return super()._prepare_target_document_values(key, lines)

        move_type = self._get_target_move_type()
        partner = self.env["res.partner"].browse(key) if key else False
        move_date = fields.Date.context_today(self, self.date)

        values = {
            "ref": self.name,
            "move_type": move_type,
            "company_id": self.company_id.id,
            "date": move_date,
        }
        if self.journal_id:
            values["journal_id"] = self.journal_id.id
        if partner:
            values["partner_id"] = partner.id
            if move_type in ("in_invoice", "in_refund"):
                if partner.property_supplier_payment_term_id:
                    values["invoice_payment_term_id"] = (
                        partner.property_supplier_payment_term_id.id
                    )
            elif move_type in ("out_invoice", "out_refund"):
                if partner.property_payment_term_id:
                    values["invoice_payment_term_id"] = (
                        partner.property_payment_term_id.id
                    )
        values["invoice_date"] = move_date
        if self.reason:
            values["narration"] = self.reason
        return values

    def _prepare_target_line_values(self, line, key, document, lines) -> dict[str, Any]:
        if not self._is_account_target():
            return super()._prepare_target_line_values(line, key, document, lines)
        return {
            "product_id": line.product_id.id,
            "product_uom_id": line.product_uom_id.id or line.product_id.uom_id.id,
            "quantity": line.quantity,
            "price_unit": line.price_unit or 0.0,
            "name": line.description or line.product_id.display_name,
        }

    def _check_accounting_type_has_product(self) -> None:
        self.check_singleton()
        if self._is_account_target() and not self.line_ids:
            raise UserError(
                self.env._(
                    "You cannot confirm an empty accounting request. "
                    "Please add product lines to create journal entries.",
                ),
            )

    def _get_category_required_field_mapping(
        self,
    ) -> dict[str, tuple[str, str]]:
        mapping = super()._get_category_required_field_mapping()
        mapping["has_journal"] = ("journal_id", self.env._("Journal"))
        return mapping

    def _check_bank_statement_line_required(self) -> None:
        for request in self:
            if request.has_bsl == "required" and not request.bank_statement_line_id:
                raise UserError(
                    self.env._(
                        "Cannot approve request '%(request)s': its category "
                        "'%(category)s' requires a bank statement line. "
                        "Select the matching bank transaction before "
                        "approving.",
                        request=request.name,
                        category=request.category_id.name,
                    ),
                )

    def _can_consent_approve(self) -> bool:
        self.check_singleton()
        if self.has_bsl == "required" and not self.bank_statement_line_id:
            return False
        return super()._can_consent_approve()

    def _check_withdraw_allowed(self) -> None:
        super()._check_withdraw_allowed()

        if not self._is_account_target():
            return
        active = self._get_all_account_moves().filtered(
            lambda m: m.state != "cancel",
        )
        self._raise_withdraw_blocked(active, "invoice/bill")
