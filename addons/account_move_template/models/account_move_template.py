from typing import Any

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError

from odoo.addons.base.models.mixin_catalog import name_uniq_index

PAYMENT_JOURNAL_TYPES = ("bank", "cash", "credit")
JOURNAL_TYPES_BY_MOVE_TYPE = {
    "in_invoice": ("purchase",),
    "in_refund": ("purchase",),
    "out_invoice": ("sale",),
    "out_refund": ("sale",),
}


class AccountMoveTemplate(models.Model):
    _name = "account.move.template"
    _description = "Journal Entry Template"
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _check_company_auto = True

    name = fields.Char(
        translate=True,
        index="trigram",
        required=True,
        tracking=True,
    )
    journal_code = fields.Char(
        required=True,
        tracking=True,
        help="When creating a new journal entry a journal having this code will be looked for",
    )
    ref = fields.Char(
        string="Reference",
        help="Internal reference or note",
    )
    active = fields.Boolean(
        default=True,
        tracking=True,
    )
    is_payment = fields.Boolean(
        default=False,
        tracking=True,
        help="If checked, this template will generate a payment instead of a journal entry",
    )
    use_third_party = fields.Boolean(
        string="Issue to the Third Party",
        default=False,
        tracking=True,
        help="If checked, the generated document is issued to the run's "
        "third party when it names one -- the party a document is made out "
        "to in place of the partner, such as the generic public for a "
        "customer who takes no fiscal invoice -- instead of the partner "
        "the operation is about. Leave it off wherever the partner himself "
        "has to be on the document: the credit note that reduces his debt "
        "is one of those.",
    )
    move_type = fields.Selection(
        selection=[
            ("entry", "Journal Entry"),
            ("in_invoice", "Vendor Bill"),
            ("in_refund", "Vendor Credit Note"),
            ("out_invoice", "Customer Invoice"),
            ("out_refund", "Customer Credit Note"),
        ],
        default="entry",
        required=True,
        tracking=True,
        help="Type of journal entry this template will create",
    )
    payment_type = fields.Selection(
        selection=[("outbound", "Send Money"), ("inbound", "Receive Money")],
        tracking=True,
        help="Determines the flow of the payment (outbound or inbound)",
    )
    partner_type = fields.Selection(
        selection=[("customer", "Customer"), ("supplier", "Vendor")],
        tracking=True,
        help="Determines whether the payment is for a customer or vendor",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        tracking=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        compute="_compute_journal_id",
        inverse="_inverse_journal_id",
        store=False,
        readonly=False,
        help="The journal `journal_code` resolves to. Pick one to fill the code.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        check_company=True,
        tracking=True,
    )
    invoice_payment_term_id = fields.Many2one(
        comodel_name="account.payment.term",
        string="Payment Terms",
        check_company=True,
        help="Used to compute the due date of the journal item.",
    )
    line_ids = fields.One2many(
        comodel_name="account.move.template.line",
        inverse_name="template_id",
        string="Lines",
        copy=True,
    )

    _name_src_uniq = name_uniq_index(
        "company_id",
        message="This name is already used by another template!",
    )

    def _journal_company_scope(self) -> models.Model:
        self.check_singleton()
        return self.company_id or self.env.companies

    def _get_journal_types(self) -> tuple[str, ...]:
        self.check_singleton()
        if self.is_payment:
            return PAYMENT_JOURNAL_TYPES
        return JOURNAL_TYPES_BY_MOVE_TYPE.get(self.move_type, ())

    def _resolve_journal_codes(self) -> dict[tuple[tuple[int, ...], str], models.Model]:
        codes_by_scope: dict[tuple[int, ...], set[str]] = {}
        for template in self.filtered("journal_code"):
            scope = tuple(sorted(template._journal_company_scope().ids))
            codes_by_scope.setdefault(scope, set()).add(template.journal_code)

        resolved: dict[tuple[tuple[int, ...], str], models.Model] = {}
        if not codes_by_scope:
            return resolved
        journals = self.env["account.journal"].search(
            [
                ("code", "in", sorted(set().union(*codes_by_scope.values()))),
                ("active", "=", True),
                ("company_id", "in", sorted(set().union(*codes_by_scope))),
            ],
        )
        for scope, codes in codes_by_scope.items():
            for journal in journals:
                if journal.code in codes and journal.company_id.id in scope:
                    key = (scope, journal.code)
                    resolved[key] = resolved.get(key, journals.browse()) | journal
        return resolved

    @api.depends_context("allowed_company_ids")
    @api.depends("journal_code", "company_id")
    def _compute_journal_id(self) -> None:
        resolved = self._resolve_journal_codes()
        for template in self:
            scope = tuple(sorted(template._journal_company_scope().ids))
            template.journal_id = resolved.get(
                (scope, template.journal_code),
                self.env["account.journal"],
            )[:1]

    def _inverse_journal_id(self) -> None:
        for template in self.filtered("journal_id"):
            template.journal_code = template.journal_id.code

    @api.constrains("journal_code", "company_id", "move_type", "is_payment")
    def _check_journal_code(self) -> None:
        templates = self.filtered("journal_code")
        if not templates:
            return

        resolved = templates._resolve_journal_codes()
        journal_labels = dict(
            self.env["account.journal"]
            ._fields["type"]
            ._description_selection(
                self.env,
            ),
        )
        document_labels = dict(
            self._fields["move_type"]._description_selection(self.env),
            payment=self.env._("Payment"),
        )
        for template in templates:
            scope = tuple(sorted(template._journal_company_scope().ids))
            journals = resolved.get((scope, template.journal_code))
            if not journals:
                raise ValidationError(
                    self.env._(
                        "Journal with code '%(code)s' not found in %(company)s. "
                        "Please verify the journal code is correct.",
                        code=template.journal_code,
                        company=", ".join(
                            template._journal_company_scope().mapped("name"),
                        ),
                    ),
                )

            allowed = template._get_journal_types()
            if mismatched := journals.filtered(
                lambda journal, allowed=allowed: (
                    allowed and journal.type not in allowed
                ),
            )[:1]:
                raise ValidationError(
                    self.env._(
                        "Template '%(name)s' creates a %(document)s, which "
                        "needs a %(allowed)s journal, but '%(code)s' is a "
                        "%(type)s journal in %(company)s.",
                        name=template.name,
                        document=document_labels[
                            "payment" if template.is_payment else template.move_type
                        ],
                        allowed=" / ".join(journal_labels[kind] for kind in allowed),
                        code=mismatched.code,
                        type=journal_labels[mismatched.type],
                        company=mismatched.company_id.name,
                    ),
                )

    @api.constrains("is_payment", "payment_type", "partner_type")
    def _check_payment_template_has_its_types(self) -> None:
        for template in self.filtered("is_payment"):
            if template.payment_type and template.partner_type:
                continue

            raise ValidationError(
                self.env._(
                    "Template '%(name)s' creates a payment, so it needs both "
                    "a payment type and a partner type. Without them the run "
                    "fails on the database's own not-null constraint.",
                    name=template.name,
                ),
            )

    @api.constrains("line_ids", "is_payment")
    def _check_template_has_lines(self) -> None:
        if self.env.context.get("install_mode") or self.env.context.get("module"):
            return

        for template in self:
            if template.is_payment:
                continue

            if not any(line.display_type == "product" for line in template.line_ids):
                raise ValidationError(
                    self.env._(
                        "Template '%(name)s' must have at least one product "
                        "line. Please add one before saving.",
                        name=template.name,
                    ),
                )

    def write(self, vals: ValuesType) -> bool:
        if "line_ids" in vals:
            # The commands run one by one, deletions and updates before
            # creations, so a template whose only product line is replaced
            # is empty in between. Its own constraint judges the final lines.
            pending = {
                *self.env.context.get("account_move_template_lines_pending", ()),
                *self.ids,
            }
            self = self.with_context(
                account_move_template_lines_pending=tuple(sorted(pending)),
            )
        return super().write(vals)

    def _check_template_keeps_its_lines(self) -> None:
        pending = self.env.context.get("account_move_template_lines_pending", ())
        self.filtered(
            lambda template: template.id not in pending,
        )._check_template_has_lines()

    def copy_data(self, default: ValuesType | None = None) -> list[dict[str, Any]]:
        vals_list = super().copy_data(default=default)
        if default and "name" in default:
            return vals_list

        for template, vals in zip(self, vals_list, strict=True):
            vals["name"] = template._get_copy_name()
        return vals_list

    def _get_copy_name(self) -> str:
        self.check_singleton()
        candidate = self.env._("%(name)s (copy)", name=self.name)
        index = 2
        records = self.with_context(active_test=False)
        while records.search_count(
            [("name", "=", candidate), ("company_id", "=", self.company_id.id)],
            limit=1,
        ):
            candidate = self.env._(
                "%(name)s (copy %(index)s)",
                name=self.name,
                index=index,
            )
            index += 1
        return candidate

    def action_move_template_run(self) -> dict[str, Any]:
        self.check_singleton()
        wizard = self.env["wizard.account.move.template.create.move"].create(
            {
                "template_id": self.id,
                "partner_id": self.partner_id.id,
                "date": fields.Date.context_today(self),
                "ref": self.ref,
            },
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Create Entry from Template"),
            "res_model": "wizard.account.move.template.create.move",
            "view_mode": "form",
            "target": "new",
            "res_id": wizard.id,
        }
