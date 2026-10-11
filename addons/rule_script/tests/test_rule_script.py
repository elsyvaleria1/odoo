import psycopg

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

ROUND = """
RULE = "test.round"
NAME = "Whole pesos"
VALID_FROM = "2014-01-01"
VALID_TO = {valid_to!r}
SOURCES = ("CFF art. 20",)
INPUTS = {{"amount": "number"}}
OUTPUT = "number"
EXAMPLES = (
    {{"inputs": {{"amount": 100.50}}, "expected": {low}}},
    {{"inputs": {{"amount": 100.51}}, "expected": 101.0}},
)

def evaluate(inputs, rules):
    whole = int(inputs.amount)
    if rules.round_half_up(inputs.amount - whole, 2) >= {threshold}:
        return whole + 1
    return whole
"""

SURCHARGE = """
RULE = "test.surcharge"
VALID_FROM = "{valid_from}"
VALID_TO = {valid_to!r}
INPUTS = {{"amount": "number", "months": "int"}}
OUTPUT = "number"

def evaluate(inputs, rules):
    return rules.call("test.round", amount=inputs.amount * {rate} * inputs.months)
"""


def round_rule(valid_to=None, threshold=0.51, low=100.0):
    return ROUND.format(valid_to=valid_to, threshold=threshold, low=low)


def surcharge_rule(valid_from, rate, valid_to=None):
    return SURCHARGE.format(valid_from=valid_from, valid_to=valid_to, rate=rate)


@tagged("post_install", "-at_install")
class TestRuleScript(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Script = cls.env["rule.script"]
        cls.Version = cls.env["rule.script.version"]

    def _load(self, sources, module="test_pack"):
        self.Script._load_rule_sources(module, sources)

    def _versions(self, code):
        return self.Version.search([("script_id.code", "=", code)])

    def test_a_shipped_rule_loads_active_and_evaluates(self):
        self._load({"rules/round.py": round_rule()})

        version = self._versions("test.round")
        self.assertEqual(version.version_state, "active")
        self.assertEqual(version.legal_sources, "CFF art. 20")
        self.assertEqual(len(version.script_id.test_ids), 2)
        self.assertEqual(
            self.Script._evaluate("test.round", "2026-03-01", amount=7.5), 7
        )
        self.assertEqual(
            self.Script._evaluate("test.round", "2026-03-01", amount=7.51), 8
        )

    def test_the_version_in_force_on_the_date_answers(self):
        self._load(
            {
                "rules/round.py": round_rule(),
                "rules/surcharge_2025.py": surcharge_rule(
                    "2025-01-01", 0.0147, valid_to="2025-12-31"
                ),
                "rules/surcharge_2026.py": surcharge_rule("2026-01-01", 0.0207),
            }
        )

        value, trace = self.Script._evaluate_traced(
            "test.surcharge", "2025-06-30", {"amount": 10000.0, "months": 3}
        )
        self.assertEqual(value, 441)
        self.assertEqual(
            [step["code"] for step in trace], ["test.round", "test.surcharge"]
        )
        self.assertEqual(
            self.Script._evaluate(
                "test.surcharge", "2026-06-30", amount=10000.0, months=3
            ),
            621,
        )
        with self.assertRaises(UserError):
            self.Script._evaluate("test.surcharge", "2024-12-31", amount=1.0, months=1)

    def test_a_shipped_rule_failing_its_examples_never_loads(self):
        with self.assertRaises(UserError):
            self._load({"rules/round.py": round_rule(threshold=0.50)})

    def test_an_unparsable_file_fails_the_load(self):
        with self.assertRaises(UserError):
            self._load({"rules/bad.py": "RULE = 'test.bad'\nimport os\n"})

    def test_a_changed_file_retires_its_version_and_a_removed_one_too(self):
        self._load({"rules/round.py": round_rule()})
        first = self._versions("test.round")

        self._load({"rules/round.py": round_rule(valid_to="2030-12-31")})

        self.assertEqual(first.version_state, "retired")
        current = self._versions("test.round") - first
        self.assertEqual(current.version_state, "active")
        self.assertEqual(str(current.date_to), "2030-12-31")

        self._load({})

        self.assertEqual(current.version_state, "retired")

    def test_an_active_version_is_immutable(self):
        self._load({"rules/round.py": round_rule()})
        version = self._versions("test.round")

        with self.assertRaises(UserError):
            version.source_code = round_rule(threshold=0.6)
        with self.assertRaises(UserError):
            version.unlink()
        with self.assertRaises(UserError):
            version.write({"version_state": "draft"})

    def test_a_local_version_needs_another_approver_and_no_overlap(self):
        self._load({"rules/round.py": round_rule(valid_to="2025-12-31")})
        script = self._versions("test.round").script_id
        author = new_test_user(
            self.env, "rule_author", groups="rule_script.group_rule_script_author"
        )
        approver = new_test_user(
            self.env,
            "rule_approver",
            groups="rule_script.group_rule_script_approver",
        )
        overlapping = (
            self.Version.with_user(author)
            .create({"script_id": script.id, "source_code": round_rule()})
            .with_user(approver)
        )
        with self.assertRaises(AccessError):
            overlapping.with_user(author).action_activate()
        with self.assertRaises(UserError):
            overlapping.action_activate()

        local = self.Version.with_user(author).create(
            {
                "script_id": script.id,
                "source_code": round_rule().replace(
                    'VALID_FROM = "2014-01-01"', 'VALID_FROM = "2026-01-01"'
                ),
                "change_reason": "2026 continues the 2014 rule",
            }
        )
        own = self.Version.with_user(approver).create(
            {"script_id": script.id, "source_code": local.source_code}
        )
        with self.assertRaises(AccessError):
            own.action_activate()
        local.with_user(approver).action_activate()

        self.assertEqual(local.version_state, "active")
        self.assertEqual(local.activated_by_id, approver)
        self.assertEqual(
            self.Script._evaluate("test.round", "2026-02-01", amount=1.5), 1
        )

    def test_the_database_refuses_two_active_versions_on_one_day(self):
        self._load({"rules/round.py": round_rule()})
        version = self._versions("test.round")
        copy = self.Version.create(
            {"script_id": version.script_id.id, "source_code": round_rule()}
        )
        copy._set_version_state("active")
        self.env.flush_all()

        with (
            self.assertRaises(psycopg.errors.ExclusionViolation),
            self.env.cr.savepoint(),
        ):
            self.env.cr.execute("SET CONSTRAINTS ALL IMMEDIATE")

    def test_a_version_naming_another_rule_must_match_it(self):
        self._load({"rules/round.py": round_rule()})
        script = self._versions("test.round").script_id
        other = self.Script.create({"code": "test.other", "name": "Other"})

        with self.assertRaises(ValidationError):
            self.Version.create({"script_id": other.id, "source_code": round_rule()})
        with self.assertRaises(ValidationError):
            self.Version.create({"script_id": script.id, "source_code": "RULE = 1"})

    def test_calls_must_name_known_rules_and_form_no_cycle(self):
        with self.assertRaises(UserError):
            self._load({"rules/surcharge.py": surcharge_rule("2026-01-01", 0.02)})

        ping = (
            'RULE = "test.ping"\nVALID_FROM = "2026-01-01"\nINPUTS = {}\nOUTPUT = "any"\n'
            'def evaluate(inputs, rules):\n    return rules.call("test.pong")\n'
        )
        pong = (
            ping.replace('"test.ping"', '"test.tmp"')
            .replace('"test.pong"', '"test.ping"')
            .replace('"test.tmp"', '"test.pong"')
        )
        pong_script = self.Script.create({"code": "test.pong", "name": "pong"})
        pong_version = self.Version.create(
            {"script_id": pong_script.id, "source_code": pong}
        )
        self._load({"rules/ping.py": ping})
        with self.assertRaises(UserError):
            pong_version._activate()

    def test_a_changed_rule_activates_after_the_rules_it_reaches(self):
        def chain_rule(code, body, expected):
            return (
                f'RULE = "{code}"\nVALID_FROM = "2026-01-01"\nINPUTS = {{}}\n'
                f'OUTPUT = "number"\nEXAMPLES = ({{"inputs": {{}}, "expected": {expected}}},)\n'
                f"def evaluate(inputs, rules):\n    return {body}\n"
            )

        middle = chain_rule("test.middle", 'rules.call("test.base")', 1)
        self._load(
            {
                "rules/base.py": chain_rule("test.base", "1", 1),
                "rules/middle.py": middle,
                "rules/top.py": chain_rule("test.top", 'rules.call("test.middle")', 1),
            }
        )

        self._load(
            {
                "rules/base.py": chain_rule("test.base", "1 + 0 * 2", 1),
                "rules/middle.py": middle,
                "rules/top.py": chain_rule(
                    "test.top", 'rules.call("test.middle") + 0', 1
                ),
            }
        )

        self.assertEqual(self.Script._evaluate("test.top", "2026-03-01"), 1)

    def test_an_evaluation_calls_a_bounded_number_of_rules(self):
        many = (
            'RULE = "test.many"\nVALID_FROM = "2026-01-01"\nINPUTS = {}\n'
            'OUTPUT = "number"\n'
            "def evaluate(inputs, rules):\n"
            "    total = 0\n"
            "    for _ in range(2000):\n"
            '        total += rules.call("test.round", amount=1.5)\n'
            "    return total\n"
        )
        self._load({"rules/round.py": round_rule(), "rules/many.py": many})

        with self.assertRaises(UserError):
            self.Script._evaluate("test.many", "2026-03-01")

    def test_a_figure_keeps_the_versions_that_computed_it(self):
        self._load(
            {
                "rules/round.py": round_rule(),
                "rules/surcharge_2026.py": surcharge_rule("2026-01-01", 0.0207),
            }
        )
        document = self.Script.search([("code", "=", "test.round")])

        value = self.Script._evaluate_for(
            document,
            "surcharge of a test",
            "test.surcharge",
            "2026-03-01",
            amount=10000.0,
            months=1,
        )

        trace = self.env["rule.script.trace"].search(
            [("res_model", "=", "rule.script"), ("res_id", "=", document.id)]
        )
        self.assertEqual(value, 207)
        self.assertEqual(trace.code, "test.surcharge")
        self.assertEqual(trace.version_id, self._versions("test.surcharge"))
        self.assertEqual(
            trace.used_version_ids,
            self._versions("test.surcharge") | self._versions("test.round"),
        )
        self.assertEqual(trace.value, "207.0")
        with self.assertRaises(UserError):
            trace.purpose = "something else"

    def test_nobody_writes_a_trace_by_hand(self):
        self._load({"rules/round.py": round_rule()})
        version = self._versions("test.round")
        approver = new_test_user(
            self.env, "trace_writer", groups="rule_script.group_rule_script_approver"
        )

        with self.assertRaises(AccessError):
            self.env["rule.script.trace"].with_user(approver).create(
                {
                    "res_model": "rule.script",
                    "res_id": version.script_id.id,
                    "purpose": "forged",
                    "code": "test.round",
                    "date_on": "2026-01-01",
                    "version_id": version.id,
                    "inputs": "{}",
                    "value": "1",
                }
            )
