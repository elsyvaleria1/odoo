from odoo.fields import Command, Domain
from odoo.tests import tagged

from .common import TestFsmFlowSaleCommon


@tagged("-at_install", "post_install")
class TestFsmProjectPricingType(TestFsmFlowSaleCommon):
    def test_pricing_type(self):
        project = self.project_non_billable
        self.assertFalse(
            project.allow_billable,
            "The allow_billable should be false if the project is non billable.",
        )
        self.assertFalse(
            project.pricing_type,
            "The pricing type of this project should be equal to False since it is non billable.",
        )

        def _search_pricing_type(operator, value):
            return Domain("pricing_type", operator, value).optimize_full(project)

        project.write(
            {
                "is_fsm": True,
            }
        )

        self.assertTrue(project.is_fsm, "The project should be a fsm project.")
        self.assertTrue(
            project.allow_billable, "By default, a fsm project should be billable."
        )
        self.assertEqual(
            project.pricing_type,
            "task_rate",
            "The pricing type of a fsm project should be equal to task_rate.",
        )
        self.assertTrue(project.filtered_domain(_search_pricing_type("=", "task_rate")))
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("!=", "task_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "fixed_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "employee_rate"))
        )
        self.assertTrue(project.filtered_domain(_search_pricing_type("!=", False)))
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "fixed_rate"))
        )
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "employee_rate"))
        )
        self.assertFalse(project.filtered_domain(_search_pricing_type("=", False)))

        project.write(
            {
                "sale_line_employee_ids": [
                    Command.create(
                        {
                            "employee_id": self.employee_user.id,
                            "timesheet_product_id": self.service_product_ordered.id,
                        }
                    ),
                ]
            }
        )
        self.assertEqual(
            project.pricing_type,
            "employee_rate",
            "The pricing type of fsm project should be equal to employee_rate when an employee mapping exists in this project.",
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("=", "employee_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "task_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "fixed_rate"))
        )
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("!=", "employee_rate"))
        )
        self.assertTrue(project.filtered_domain(_search_pricing_type("!=", False)))
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "task_rate"))
        )
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "fixed_rate"))
        )
        self.assertFalse(project.filtered_domain(_search_pricing_type("=", False)))

        project.write(
            {
                "allow_billable": False,
            }
        )

        self.assertFalse(
            project.allow_billable, "The fsm project should be non billable."
        )
        self.assertFalse(
            project.pricing_type,
            "The pricing type should be equal to False since the project is non billable.",
        )
        self.assertTrue(project.filtered_domain(_search_pricing_type("=", False)))
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "task_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "fixed_rate"))
        )
        self.assertTrue(
            project.filtered_domain(_search_pricing_type("!=", "employee_rate"))
        )
        self.assertFalse(project.filtered_domain(_search_pricing_type("!=", False)))
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "task_rate"))
        )
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "fixed_rate"))
        )
        self.assertFalse(
            project.filtered_domain(_search_pricing_type("=", "employee_rate"))
        )
