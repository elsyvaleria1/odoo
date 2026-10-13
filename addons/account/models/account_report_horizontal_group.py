from odoo import fields, models

from odoo.addons.base.models.mixin_catalog import name_uniq_index


class AccountReportHorizontalGroup(models.Model):
    _name = "account.report.horizontal.group"
    _description = "Horizontal group for reports"

    name = fields.Char(
        translate=True,
        required=True,
    )
    rule_ids = fields.One2many(
        comodel_name="account.report.horizontal.group.rule",
        inverse_name="horizontal_group_id",
        string="Rules",
        required=True,
    )
    report_ids = fields.Many2many(
        comodel_name="report.formula",
        string="Reports",
    )

    _name_src_uniq = name_uniq_index(
        message="A horizontal group with the same name already exists.",
    )

    def _get_header_levels_data(self) -> list:
        return [
            (rule.field_name, rule._get_matching_records()) for rule in self.rule_ids
        ]
