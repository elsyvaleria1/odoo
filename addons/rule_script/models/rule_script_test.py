from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.json import loads as json_loads
from odoo.tools import frozendict

from ..tools.runtime import RuleContext, RuleRuntimeError, run_rule
from ..tools.types import RuleValueError, coerce


class RuleScriptTest(models.Model):
    _name = "rule.script.test"
    _description = "Rule Script Test"
    _order = "script_id, date_on, id"
    _access_anchors = frozendict({"company": ""})

    script_id = fields.Many2one(
        comodel_name="rule.script",
        string="Rule",
        required=True,
        ondelete="cascade",
    )
    version_id = fields.Many2one(
        comodel_name="rule.script.version",
        string="Example Of",
        ondelete="cascade",
        help="Set for an example a version's source declares; such a test runs "
        "against that version only. Otherwise the test runs against every "
        "version valid on its date.",
    )
    name = fields.Char(
        required=True,
    )
    date_on = fields.Date(
        string="Evaluated On",
        required=True,
    )
    inputs = fields.Text(
        default="{}",
        required=True,
        help="The inputs, as a JSON object; dates as ISO strings.",
    )
    expected = fields.Text(
        required=True,
        help="The expected value, as JSON.",
    )
    tolerance = fields.Float(
        digits=(16, 6),
        default=0.000001,
        help="Largest difference accepted between a number and its expectation.",
    )
    origin = fields.Selection(
        selection=[
            ("shipped", "Shipped by a module"),
            ("local", "Local"),
        ],
        default="local",
        readonly=True,
        required=True,
    )
    legal_reference = fields.Char(
        help="The worked example this test reproduces, e.g. a SAT guide case.",
    )
    last_result = fields.Text(
        readonly=True,
    )

    @api.constrains("inputs", "expected")
    def _check_json(self) -> None:
        for test in self:
            try:
                inputs = json_loads(test.inputs)
                json_loads(test.expected)
            except ValueError as error:
                raise ValidationError(
                    self.env._(
                        "%(test)s is not valid JSON: %(error)s",
                        test=test.name,
                        error=error,
                    )
                ) from error
            if not isinstance(inputs, dict):
                raise ValidationError(
                    self.env._("The inputs of %s are a JSON object.", test.name)
                )

    def _run_against(self, version) -> list:
        """The failure messages of these tests evaluated by `version`; each test
        records its outcome."""
        header, function = version._get_compiled()
        Script = self.env["rule.script"]
        failures = []
        for test in self:
            context = RuleContext(test.date_on, Script._resolve_and_run, 0, [])
            try:
                value = run_rule(function, header, json_loads(test.inputs), context)
                expected = coerce(header.output, json_loads(test.expected))
            except (RuleRuntimeError, RuleValueError) as error:
                message = f"{test.name}: {error}"
            else:
                message = (
                    None
                    if test._matches(value, expected)
                    else f"{test.name}: got {value!r}, expected {expected!r}"
                )
            test.last_result = message or self.env._("Passed")
            if message:
                failures.append(message)
        return failures

    def _matches(self, value, expected) -> bool:
        if isinstance(expected, float) and isinstance(value, (int, float)):
            return abs(value - expected) <= self.tolerance
        return value == expected
