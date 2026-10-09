import json
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import frozendict

from ..tools.grammar import RuleSyntaxError, parse_rule
from ..tools.runtime import compile_rule

_logger = logging.getLogger(__name__)

# digest -> (header, function); a version's source never changes once it can
# run, so its digest names one compiled function for the life of the process
_COMPILED = {}


class RuleScriptVersion(models.Model):
    _name = "rule.script.version"
    _description = "Rule Script Version"
    _inherit = ["mixin.mail.thread"]
    _order = "script_id, date_from desc, id desc"
    _access_anchors = frozendict({"company": ""})
    _access_verbs = {
        "activate": models.Verb(
            methods=("action_activate",),
            transition=("version_state", "draft", "active"),
            at_create=False,
        ),
        "retire": models.Verb(
            methods=("action_retire",),
            transition=("version_state", "active", "retired"),
            at_create=False,
        ),
    }

    script_id = fields.Many2one(
        comodel_name="rule.script",
        string="Rule",
        index=True,
        required=True,
        ondelete="cascade",
    )
    code = fields.Char(
        related="script_id.code",
    )
    source_code = fields.Text(
        string="Source",
        required=True,
        help="The rule script: UPPERCASE literal constants (RULE, VALID_FROM, "
        "INPUTS, OUTPUT and optionally NAME, VALID_TO, SOURCES, EXAMPLES) and "
        "one evaluate(inputs, rules) function.",
    )
    date_from = fields.Date(
        string="Valid From",
        compute="_compute_header",
        store=True,
    )
    date_to = fields.Date(
        string="Valid To",
        compute="_compute_header",
        store=True,
    )
    legal_sources = fields.Text(
        compute="_compute_header",
        store=True,
        help="The legal basis the version implements, one citation per line.",
    )
    input_signature = fields.Json(
        compute="_compute_header",
        store=True,
    )
    output_type = fields.Char(
        compute="_compute_header",
        store=True,
    )
    dependency_codes = fields.Json(
        string="Calls",
        compute="_compute_header",
        store=True,
        help="The rules this version calls, read from its source.",
    )
    digest = fields.Char(
        compute="_compute_header",
        store=True,
        index=True,
    )
    version_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("active", "Active"),
            ("retired", "Retired"),
        ],
        string="Status",
        default="draft",
        copy=False,
        readonly=True,
        required=True,
        tracking=True,
    )
    origin = fields.Selection(
        selection=[
            ("shipped", "Shipped by a module"),
            ("local", "Local"),
        ],
        default="local",
        copy=False,
        readonly=True,
        required=True,
    )
    module = fields.Char(
        copy=False,
        readonly=True,
    )
    path = fields.Char(
        copy=False,
        readonly=True,
    )
    date_activated = fields.Datetime(
        copy=False,
        readonly=True,
    )
    activated_by_id = fields.Many2one(
        comodel_name="res.users",
        copy=False,
        readonly=True,
    )
    change_reason = fields.Text(
        help="Why this version exists: the reform, ruling or error it answers.",
    )

    # The last word on overlap belongs to PostgreSQL: two activations can each
    # pass _find_overlapping_versions and commit overlapping versions together.
    # Deferred, so the Python check names the colliding versions first.
    _no_overlap = models.Constraint(
        "EXCLUDE USING gist ("
        "script_id WITH =,"
        " daterange(date_from, date_to, '[]') WITH &&)"
        " WHERE (version_state = 'active')"
        " DEFERRABLE INITIALLY DEFERRED",
        "Two active versions of a rule cannot be valid on the same day.",
    )

    @api.constrains("source_code", "script_id")
    def _check_source_code(self) -> None:
        for version in self:
            try:
                header, _module = parse_rule(version.source_code)
            except RuleSyntaxError as error:
                raise ValidationError(
                    self.env._("The rule does not parse: %s", error)
                ) from error
            if header.code != version.script_id.code:
                raise ValidationError(
                    self.env._(
                        "The source declares RULE = '%(declared)s', the "
                        "version belongs to %(code)s.",
                        declared=header.code,
                        code=version.script_id.code,
                    )
                )
            if header.date_to and header.date_to < header.date_from:
                raise ValidationError(self.env._("VALID_TO is before VALID_FROM."))

    def write(self, vals):
        if "version_state" in vals:
            raise UserError(
                self.env._(
                    "A version's status changes through Activate and Retire only."
                )
            )
        if {"source_code", "script_id"} & set(vals) and any(
            version.version_state != "draft" for version in self
        ):
            raise UserError(
                self.env._(
                    "An active or retired version is immutable; write a new version."
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_activated(self) -> None:
        if any(version.version_state != "draft" for version in self):
            raise UserError(
                self.env._("Only a draft version can be deleted; retire it instead.")
            )

    @api.depends("source_code")
    def _compute_header(self) -> None:
        for version in self:
            try:
                header, _module = parse_rule(version.source_code or "")
            except RuleSyntaxError:
                header = None
            version.date_from = header.date_from if header else False
            version.date_to = header.date_to if header else False
            version.legal_sources = "\n".join(header.sources) if header else False
            version.input_signature = header.inputs if header else False
            version.output_type = header.output if header else False
            version.dependency_codes = list(header.dependencies) if header else False
            version.digest = header.digest if header else False

    @api.depends("script_id.code", "date_from", "date_to", "version_state")
    def _compute_display_name(self) -> None:
        for version in self:
            version.display_name = (
                f"{version.script_id.code} {version.date_from or '?'}"
                f" → {version.date_to or '…'}"
            )

    def action_run_tests(self) -> dict:
        self.check_singleton()
        tests = self._get_applicable_tests()
        failures = tests._run_against(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger" if failures else "success",
                "message": "\n".join(failures)
                or self.env._("%s tests passed.", len(tests)),
                "sticky": bool(failures),
            },
        }

    def action_activate(self) -> None:
        for version in self:
            if version.create_uid == self.env.user:
                raise AccessError(
                    self.env._(
                        "A version is activated by someone other than its author."
                    )
                )
            version._activate()

    def action_retire(self) -> None:
        for version in self:
            if version.version_state != "active":
                raise UserError(self.env._("Only an active version can be retired."))
        self._set_version_state("retired")

    def _covers(self, date) -> bool:
        return bool(
            self.date_from
            and self.date_from <= date
            and (not self.date_to or date <= self.date_to)
        )

    def _get_compiled(self) -> tuple:
        self.check_singleton()
        compiled = _COMPILED.get(self.digest)
        if compiled is None:
            header, module = parse_rule(self.source_code)
            compiled = (header, compile_rule(module, f"<rule {header.code}>"))
            _COMPILED[header.digest] = compiled
        return compiled

    def _get_applicable_tests(self):
        self.check_singleton()
        return self.script_id.test_ids.filtered(
            lambda test: (
                test.version_id == self
                or (not test.version_id and self._covers(test.date_on))
            )
        )

    def _find_overlapping_versions(self):
        self.check_singleton()
        return self.script_id.version_ids.filtered(
            lambda version: (
                version != self
                and version.version_state == "active"
                and (not version.date_to or self.date_from <= version.date_to)
                and (not self.date_to or version.date_from <= self.date_to)
            )
        )

    def _activate(self) -> None:
        """Make a draft version the one in force over its dates: its calls must
        name rules that exist, form no cycle, and every test of its dates must
        pass."""
        self.check_singleton()
        if self.version_state != "draft":
            raise UserError(self.env._("Only a draft version can be activated."))
        overlapping = self._find_overlapping_versions()
        if overlapping:
            raise UserError(
                self.env._(
                    "%(version)s overlaps %(others)s; retire them first.",
                    version=self.display_name,
                    others=", ".join(overlapping.mapped("display_name")),
                )
            )
        self._check_dependencies()
        failures = self._get_applicable_tests()._run_against(self)
        if failures:
            raise UserError(
                self.env._(
                    "%(version)s fails its tests:\n%(failures)s",
                    version=self.display_name,
                    failures="\n".join(failures),
                )
            )
        self._set_version_state("active")

    def _check_dependencies(self) -> None:
        Script = self.env["rule.script"]
        missing = [
            code
            for code in self.dependency_codes or []
            if not Script.search_count([("code", "=", code)])
        ]
        if missing:
            raise UserError(
                self.env._(
                    "%(code)s calls unknown rules: %(missing)s",
                    code=self.code,
                    missing=", ".join(missing),
                )
            )
        graph = {
            version.code: set(version.dependency_codes or [])
            for version in self.search([("version_state", "=", "active")])
        }
        graph.setdefault(self.code, set()).update(self.dependency_codes or [])
        path = []

        def visit(code, seen):
            if code in seen:
                raise UserError(
                    self.env._("Rule calls form a cycle: %s", " → ".join([*path, code]))
                )
            path.append(code)
            for callee in graph.get(code, ()):
                visit(callee, seen | {code})
            path.pop()

        visit(self.code, frozenset())

    def _set_version_state(self, version_state) -> None:
        values = {"version_state": version_state}
        if version_state == "active":
            values.update(
                date_activated=fields.Datetime.now(), activated_by_id=self.env.uid
            )
        # past the immutability guard of write(): this is the one sanctioned
        # transition, and the cache of versions in force must follow it
        super().write(values)
        self.env.registry.clear_cache()

    def _sorted_callees_first(self):
        """These versions ordered so that a version comes after the versions
        of this set whose rules it calls; a cycle keeps its members in place,
        for activation to refuse."""
        ordered = self.browse()
        pending = self
        while pending:
            ready = (
                pending._filter_calling_none_of(set(pending.mapped("code"))) or pending
            )
            ordered |= ready
            pending -= ready
        return ordered

    def _filter_calling_none_of(self, codes):
        return self.filtered(
            lambda version: (
                not codes.intersection(version.dependency_codes or []) - {version.code}
            )
        )

    def _retire_or_drop(self) -> None:
        for version in self:
            if version.version_state == "draft":
                version.unlink()
            elif version.version_state == "active":
                version._set_version_state("retired")

    def _create_example_tests(self, header) -> None:
        self.check_singleton()
        self.env["rule.script.test"].create(
            [
                {
                    "script_id": self.script_id.id,
                    "version_id": self.id,
                    "name": example.get("name") or f"{header.code} example {index}",
                    "date_on": example.get("on") or header.date_from,
                    "inputs": json.dumps(example["inputs"]),
                    "expected": json.dumps(example["expected"]),
                    "origin": "shipped",
                }
                for index, example in enumerate(header.examples, 1)
            ]
        )

    def _auto_init(self) -> None:
        """Provide the btree_gist extension the exclusion constraint needs; a
        role that may not create it leaves _find_overlapping_versions the only
        guard (see date_range)."""
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        except Exception:
            _logger.warning(
                "Could not create the btree_gist extension; rule versions are "
                "kept from overlapping by the Python check only.",
                exc_info=True,
            )
        super()._auto_init()
