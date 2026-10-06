from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountTaxMergeLine(models.TransientModel):
    _name = "wizard.account.tax.merge.line"
    _inherit = ["mixin.account.merge.line"]
    _description = "Tax merge wizard line"
    _order = "sequence, id"

    _merge_record_field = "tax_id"
    _merge_record_display_type = "tax"
    _merge_record_hashed_field = "tax_has_hashed_entries"

    wizard_id = fields.Many2one(
        comodel_name="wizard.account.tax.merge",
        required=True,
        ondelete="cascade",
    )
    display_type = fields.Selection(
        selection=[("line_section", "Section"), ("tax", "Tax")],
        required=True,
    )
    tax_id = fields.Many2one(
        comodel_name="account.tax",
        readonly=True,
        ondelete="cascade",
    )
    company_ids = fields.Many2many(related="tax_id.company_ids")
    tax_has_hashed_entries = fields.Boolean(compute="_compute_tax_has_hashed_entries")

    @api.depends("tax_id")
    @_debug.perf.timed
    def _compute_tax_has_hashed_entries(self) -> None:
        hashed_lines = (
            self.env["account.move.line"]
            .sudo()
            ._read_group(
                [
                    ("move_id.inalterable_hash", "!=", False),
                    "|",
                    ("tax_line_id", "in", self.tax_id.ids),
                    ("tax_ids", "in", self.tax_id.ids),
                ],
                ["tax_line_id", "tax_ids"],
            )
        )
        hashed = {tax.id for taxes in hashed_lines for tax in taxes}
        _debug.perf.count("hashed_taxes_fetched", rows=len(hashed))
        for line in self:
            line.tax_has_hashed_entries = line.tax_id.id in hashed

    @api.depends("tax_id", "wizard_id.wizard_line_ids.is_selected", "display_type")
    def _compute_info(self) -> None:
        super()._compute_info()

    def _get_merge_section_name(self):
        return self.tax_id.display_name

    def _update_info_conflicts(self) -> None:
        self._update_info_company_conflict()
        self._update_info_repartition_conflict()
        self._update_info_hashed_moves_conflict()

    def _update_info_repartition_conflict(self) -> None:
        reference = None
        signature_of = self.wizard_id._get_repartition_signature
        for line in self:
            if not line.is_selected or line.info:
                continue
            signature = signature_of(line.tax_id)
            if reference is None:
                reference = (signature, line.tax_id)
            elif signature != reference[0]:
                line.info = self.env._(
                    "Its distribution differs from %s.",
                    reference[1].display_name,
                )
