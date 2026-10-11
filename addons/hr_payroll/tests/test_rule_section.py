from odoo import tests
from odoo.exceptions import UserError

from odoo.addons.hr_payroll.tests.common import TestPayslipBase


@tests.tagged("post_install", "-at_install")
class TestRuleSection(TestPayslipBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_unlink_section_constraints(self):
        active_input_section, unused_rule_section, unused_section = self.env[
            "hr.salary.rule.section"
        ].create(
            [
                {"name": "Active Input Section", "sequence": 1},
                {"name": "Unused Rule Section", "sequence": 2},
                {"name": "Unused Section", "sequence": 3},
            ]
        )

        self.hra_rule.write(
            {
                "condition_select": "property_input",
                "input_section": active_input_section.id,
            }
        )
        self.developer_pay_structure.write(
            {
                "version_properties_definition": [
                    {"name": str(self.hra_rule.id), "type": "float", "default": 0.0}
                ]
            }
        )
        self.hra_rule._compute_input_used_in_definition()

        self.conv_rule.write(
            {
                "condition_select": "property_input",
                "input_section": unused_rule_section.id,
            }
        )
        self.conv_rule._compute_input_used_in_definition()

        with self.assertRaises(UserError):
            active_input_section.unlink()

        unused_rule_section.unlink()
        self.assertFalse(unused_rule_section.exists())

        unused_section.unlink()
        self.assertFalse(unused_section.exists())
