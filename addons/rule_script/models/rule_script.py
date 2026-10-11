import logging
from pathlib import Path

from odoo import api, fields, models, tools
from odoo.exceptions import UserError
from odoo.modules import get_module_path
from odoo.tools import frozendict

from ..tools.grammar import RuleSyntaxError, parse_rule
from ..tools.runtime import RuleContext, RuleRuntimeError, run_rule
from ..tools.types import RuleValueError

_logger = logging.getLogger(__name__)

RULES_DIRECTORY = "rules"


class RuleScript(models.Model):
    _name = "rule.script"
    _description = "Rule Script"
    _order = "code"
    _access_anchors = frozendict({"company": ""})

    code = fields.Char(
        required=True,
        help="Dotted code callers evaluate the rule by, e.g. mx.cff.round_payment.",
    )
    name = fields.Char(
        translate=True,
        required=True,
    )
    description = fields.Text(
        translate=True,
    )
    active = fields.Boolean(
        default=True,
    )
    version_ids = fields.One2many(
        comodel_name="rule.script.version",
        inverse_name="script_id",
        string="Versions",
    )
    current_version_id = fields.Many2one(
        comodel_name="rule.script.version",
        string="Version in Force",
        compute="_compute_current_version_id",
        help="The active version valid today.",
    )
    test_ids = fields.One2many(
        comodel_name="rule.script.test",
        inverse_name="script_id",
        string="Tests",
    )

    _code_uniq = models.Constraint(
        "unique (code)",
        "A rule code is unique.",
    )

    @api.depends(
        "version_ids.version_state",
        "version_ids.date_from",
        "version_ids.date_to",
    )
    def _compute_current_version_id(self) -> None:
        today = fields.Date.context_today(self)
        for script in self:
            script.current_version_id = script.version_ids.filtered(
                lambda version: (
                    version._covers(today) and version.version_state == "active"
                )
            )[:1]

    def _evaluate(self, code, on_date, **inputs):
        value, _trace = self._evaluate_traced(code, on_date, inputs)
        return value

    def _evaluate_for(self, record, purpose, code, on_date, **inputs):
        value, trace = self._evaluate_traced(code, on_date, inputs)
        self.env["rule.script.trace"]._record(
            record, purpose, code, fields.Date.to_date(on_date), inputs, value, trace
        )
        return value

    def _evaluate_traced(self, code, on_date, inputs) -> tuple:
        trace = []
        try:
            value = self._resolve_and_run(
                code, fields.Date.to_date(on_date), inputs, 0, trace
            )
        except (RuleRuntimeError, RuleValueError) as error:
            raise UserError(
                self.env._("Rule %(code)s failed: %(error)s", code=code, error=error)
            ) from error
        return value, trace

    def _resolve_and_run(self, code, on_date, inputs, depth, trace):
        version = self.env["rule.script.version"].browse(
            self._get_version_id_in_force(code, on_date)
        )
        if not version:
            raise RuleRuntimeError(f"no version of {code} is in force on {on_date}")
        header, function = version._get_compiled()
        context = RuleContext(on_date, self._resolve_and_run, depth, trace)
        value = run_rule(function, header, inputs, context)
        trace.append(
            {"code": code, "version_id": version.id, "inputs": inputs, "value": value}
        )
        return value

    @api.model
    @tools.ormcache("code", "on_date")
    def _get_version_id_in_force(self, code, on_date):
        version = self.env["rule.script.version"].search(
            [
                ("script_id.code", "=", code),
                ("version_state", "=", "active"),
                ("date_from", "<=", on_date),
                "|",
                ("date_to", "=", False),
                ("date_to", ">=", on_date),
            ],
            limit=1,
        )
        return version.id

    @api.model
    def _load_module_rules(self, module) -> None:
        root = Path(get_module_path(module))
        sources = {
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in sorted((root / RULES_DIRECTORY).rglob("*.py"))
        }
        self._load_rule_sources(module, sources)

    @api.model
    def _load_rule_sources(self, module, sources) -> None:
        Version = self.env["rule.script.version"]
        shipped = Version.with_context(active_test=False).search(
            [
                ("origin", "=", "shipped"),
                ("module", "=", module),
                ("version_state", "!=", "retired"),
            ]
        )
        by_path = {version.path: version for version in shipped}
        scripts = {
            script.code: script
            for script in self.with_context(active_test=False).search([])
        }
        created = Version
        for path, source in sources.items():
            try:
                header, _module = parse_rule(source)
            except RuleSyntaxError as error:
                raise UserError(
                    self.env._(
                        "%(module)s/%(path)s is not a valid rule: %(error)s",
                        module=module,
                        path=path,
                        error=error,
                    )
                ) from error
            current = by_path.pop(path, Version)
            if current and current.digest == header.digest:
                continue
            current._retire_or_drop()
            script = scripts.get(header.code)
            if not script:
                script = scripts[header.code] = self.create(
                    {"code": header.code, "name": header.name}
                )
            version = Version.create(
                {
                    "script_id": script.id,
                    "origin": "shipped",
                    "module": module,
                    "path": path,
                    "source_code": source,
                }
            )
            version._create_example_tests(header)
            created |= version
        for version in by_path.values():
            version._retire_or_drop()
        for version in created._sorted_callees_first():
            if version._find_overlapping_versions():
                _logger.warning(
                    "event=rule_shipped_shadowed rule=%s module=%s path=%s",
                    version.code,
                    module,
                    version.path,
                )
                continue
            version._activate()
