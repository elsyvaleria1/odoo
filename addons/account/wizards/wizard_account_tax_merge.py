from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountTaxMerge(models.TransientModel):
    _name = "wizard.account.tax.merge"
    _inherit = ["mixin.account.merge"]
    _description = "Tax merge wizard"

    _merge_model = "account.tax"
    _merge_records_field = "tax_ids"

    tax_ids = fields.Many2many(comodel_name="account.tax")
    wizard_line_ids = fields.One2many(
        comodel_name="wizard.account.tax.merge.line",
        inverse_name="wizard_id",
        compute="_compute_wizard_line_ids",
        store=True,
        readonly=False,
    )

    def _get_merge_messages(self):
        return {
            "wrong_model": self.env._("This can only be used on taxes."),
            "too_few": self.env._("You must select at least 2 taxes."),
            "merged": self.env._("Taxes successfully merged!"),
        }

    @api.model
    def _get_grouping_key(self, tax):
        return (
            tax.name,
            tax.type_tax_use,
            tax.tax_scope,
            tax.country_id,
            tax.amount_type,
            tax.amount,
            tax.price_include_override,
            tax.include_base_amount,
            tax.is_base_affected,
            tax.active,
        )

    @api.model
    def _get_repartition_signature(self, tax):
        return tuple(
            (
                line.document_type,
                line.repartition_type,
                line.factor_percent,
                line.account_id.id,
                tuple(sorted(line.tag_ids.ids)),
            )
            for line in tax.repartition_line_ids._sorted_for_positional_pairing()
        )

    @api.depends("tax_ids")
    def _compute_wizard_line_ids(self) -> None:
        super()._compute_wizard_line_ids()

    def _get_merge_tables_excluded(self, model):
        return super()._get_merge_tables_excluded(model) | {
            self.env["account.tax.repartition.line"]._table
        }

    @api.model
    def _repoint_repartition_lines(self, taxes_to_remove, tax_to_merge_into) -> None:

        def ordered(tax):
            return tax.repartition_line_ids._sorted_for_positional_pairing()

        destination = ordered(tax_to_merge_into)
        mapping = {}
        for tax in taxes_to_remove:
            for old, new in zip(ordered(tax), destination, strict=True):
                mapping[old.id] = new.id
        self.env["account.tax.repartition.line"]._remap_move_lines(mapping)

    @api.model
    def _prepare_merge(self, taxes):
        self._repoint_repartition_lines(taxes[1:], taxes[0])
