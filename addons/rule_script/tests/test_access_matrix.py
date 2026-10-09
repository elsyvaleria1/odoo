from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

ROUND = """
RULE = "matrix.round"
VALID_FROM = "2014-01-01"
INPUTS = {"amount": "number"}
OUTPUT = "number"

def evaluate(inputs, rules):
    return round(inputs.amount)
"""


@tagged("post_install", "-at_install", "access_matrix")
class TestRuleScriptAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "author_a": Persona("rule_script.group_rule_script_author"),
        "approver_a": Persona("rule_script.group_rule_script_approver"),
        "portal_c": Persona(portal="customer_c"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "rule.script",
            "rule",
            note="every employee evaluates rules for the modules that read them; "
            "authors write them, and no one deletes one with versions on record",
            employee_a="r",
            author_a="rwc",
            approver_a="rwc",
        ),
        Cell(
            "rule.script.version",
            "version",
            note="authors write draft versions; activation and retirement are "
            "the approver's, through action_activate and action_retire",
            employee_a="r",
            author_a="rwcd",
            approver_a="rwcd activate retire",
        ),
        Cell(
            "rule.script.test",
            "test",
            note="authors write and run tests",
            employee_a="r",
            author_a="rwcd",
            approver_a="rwcd",
        ),
        Cell(
            "rule.script.trace",
            "trace",
            note="anyone reads which rule versions computed a figure; only an "
            "evaluation creates a trace, through rule_script.privilege_record_trace, "
            "and a trace never changes",
            employee_a="r",
            author_a="r",
            approver_a="r",
        ),
    )

    @classmethod
    def build(cls):
        script = cls.env["rule.script"].create(
            {"code": "matrix.round", "name": "Round"}
        )
        version = cls.env["rule.script.version"].create(
            {"script_id": script.id, "source_code": ROUND}
        )
        test = cls.env["rule.script.test"].create(
            {
                "script_id": script.id,
                "name": "rounds",
                "date_on": "2026-01-01",
                "inputs": '{"amount": 1.4}',
                "expected": "1",
            }
        )
        trace = cls.env["rule.script.trace"].create(
            {
                "res_model": "rule.script",
                "res_id": script.id,
                "purpose": "matrix",
                "code": "matrix.round",
                "date_on": "2026-01-01",
                "version_id": version.id,
                "inputs": "{}",
                "value": "1",
            }
        )
        return {"rule": script, "version": version, "test": test, "trace": trace}
