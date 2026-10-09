import json

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict


class RuleScriptTrace(models.Model):
    _name = "rule.script.trace"
    _description = "Rule Script Trace"
    _order = "id desc"
    _access_anchors = frozendict({"company": ""})

    res_model = fields.Char(
        string="Document Model",
        index=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Document ID",
        index=True,
        required=True,
    )
    purpose = fields.Char(
        required=True,
        help="What the document used the value for.",
    )
    code = fields.Char(
        string="Rule",
        index=True,
        required=True,
    )
    date_on = fields.Date(
        string="Evaluated On",
        required=True,
    )
    version_id = fields.Many2one(
        comodel_name="rule.script.version",
        required=True,
        ondelete="restrict",
    )
    used_version_ids = fields.Many2many(
        comodel_name="rule.script.version",
        relation="rule_script_trace_version_rel",
        string="Versions Used",
        help="Every version the evaluation ran, its nested calls included.",
    )
    inputs = fields.Text(
        required=True,
    )
    value = fields.Text(
        required=True,
    )
    steps = fields.Text(
        help="Each rule evaluated, nested calls first, as JSON.",
    )

    def write(self, vals):
        raise UserError(
            self.env._("A rule trace records what was computed; it does not change.")
        )

    def _record(self, record, purpose, code, on_date, inputs, value, trace) -> None:
        """Keep the evaluation behind a figure of `record`: the version in force,
        what it read and returned, and every nested call."""
        record.check_singleton()
        version_ids = [step["version_id"] for step in trace]
        self.with_privilege(
            "rule_script.privilege_record_trace",
            reason="a document kept the rule behind a figure",
        ).create(
            {
                "res_model": record._name,
                "res_id": record.id,
                "purpose": purpose,
                "code": code,
                "date_on": on_date,
                "version_id": trace[-1]["version_id"],
                "used_version_ids": [fields.Command.set(version_ids)],
                "inputs": json.dumps(inputs, default=str, sort_keys=True),
                "value": json.dumps(value, default=str, sort_keys=True),
                "steps": json.dumps(trace, default=str),
            }
        )
