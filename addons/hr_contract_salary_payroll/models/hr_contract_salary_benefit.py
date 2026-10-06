from odoo import api, fields, models


class HrContractSalaryBenefit(models.Model):
    _inherit = "hr.contract.salary.benefit"

    source = fields.Selection(
        selection_add=[("rule", "Salary Rule")],
        ondelete={"rule": "cascade"},
    )
    salary_rule_id = fields.Many2one(
        comodel_name="hr.salary.rule",
        domain="[('input_usage_employee', '=', True), ('input_used_in_definition', '=', True), ('struct_id.type_id', '=', structure_type_id)]",
        help="Select the salary rule associated with this benefit",
    )

    # `source` too: the body branches on it below, and the parent only
    # declares `res_field_id` - depends accumulate along the MRO, so without
    # this a benefit switched between the two sources kept the other one's
    # field name, and `_prepare_benefit_vals` (which never checks `source`)
    # then wrote the submitted amount onto that stale version field.
    @api.depends("salary_rule_id", "source")
    def _compute_field(self) -> None:
        for record in self:
            if record.source == "field":
                record.field = record.res_field_id.name
            elif record.source == "rule":
                record.field = record.salary_rule_id.code
            else:
                record.field = False
