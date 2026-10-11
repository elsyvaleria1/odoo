from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import TestFsmFlowSaleCommon


@tagged("-at_install", "post_install")
class TestIndustryFsmProject(TestFsmFlowSaleCommon):
    def test_timesheet_product_is_required(self):
        with self.assertRaises(ValidationError):
            self.fsm_project.write({"timesheet_product_id": False})

    def test_convert_project_into_fsm_project(self):
        self.project_non_billable.write({"is_fsm": True})
        self.assertTrue(self.project_non_billable.allow_billable)
        self.assertTrue(self.project_non_billable.is_fsm)
        self.assertTrue(self.project_non_billable.allow_material)
        self.assertEqual(self.project_non_billable.pricing_type, "task_rate")

        self.project_employee_rate = self.project_task_rate.copy(
            {
                "name": 'Project with pricing_type="employee_rate"',
                "sale_line_id": self.so.line_ids[0].id,
                "sale_line_employee_ids": [
                    (
                        0,
                        0,
                        {
                            "employee_id": self.employee_user.id,
                            "sale_line_id": self.so.line_ids[1].id,
                        },
                    )
                ],
            }
        )
        self.project_employee_rate.write({"is_fsm": True})
        self.assertTrue(self.project_employee_rate.is_fsm)
        self.assertTrue(self.project_employee_rate.allow_material)
        self.assertEqual(self.project_employee_rate.pricing_type, "employee_rate")
        self.assertFalse(self.project_employee_rate.sale_order_id)
        self.assertFalse(self.project_employee_rate.sale_line_id)

        self.project_project_rate = self.project_task_rate.copy(
            {
                "name": 'Project with pricing_type="project_rate"',
                "sale_line_id": self.so.line_ids[1].id,
            }
        )
        self.project_project_rate.write({"is_fsm": True})
        self.assertTrue(self.project_project_rate.is_fsm)
        self.assertTrue(self.project_project_rate.allow_material)
        self.assertEqual(self.project_project_rate.pricing_type, "task_rate")
        self.assertFalse(self.project_project_rate.sale_order_id)
        self.assertFalse(self.project_project_rate.sale_line_id)

    def test_fsm_project_form_view(self):
        with self.debug_mode():
            with Form(
                self.env["project.project"].with_context({"tracking_disable": True})
            ) as project_form:
                project_form.name = "Test Fsm Project"
                project_form.is_fsm = True
                with project_form.sale_line_employee_ids.new() as mapping_form:
                    mapping_form.employee_id = self.employee_manager
                    mapping_form.timesheet_product_id = self.product_order_timesheet1
                    self.assertEqual(
                        mapping_form.price_unit,
                        self.product_order_timesheet1.lst_price,
                        "The price unit should be computed and equal to the price unit defined in the timesheet product.",
                    )
                    mapping_form.price_unit = 150
                    self.assertNotEqual(
                        mapping_form.price_unit,
                        self.product_order_timesheet1.lst_price,
                        "The price unit should be the one selected by the user and no longer the one defined in the timesheet product.",
                    )
                    self.assertEqual(
                        mapping_form.price_unit,
                        150,
                        "The price should be equal to 150.",
                    )
                project = project_form.save()
                self.assertEqual(
                    project.pricing_type,
                    "employee_rate",
                    "The pricing type of this project should be equal to employee rate since it has a mapping.",
                )
                self.assertFalse(
                    project.partner_id,
                    "No partner should be set with the compute_partner_id because this compute should be ignored in a fsm project.",
                )
                self.assertEqual(
                    project.sale_line_employee_ids.price_unit,
                    150,
                    "The price unit should remain to 150.",
                )

    def test_get_sale_order_items(self):
        self.assertFalse(
            self.task.sale_line_id,
            "The task in the FSM Project should not have any SOL linked.",
        )
        self.assertFalse(
            self.fsm_project._get_sale_order_items(),
            "No SOL should be fetched since no task in that project has a SOL linked.",
        )
        self.assertFalse(
            self.fsm_project._get_sale_orders(),
            "No SOL should be fetched since no task in that project has a SOL linked.",
        )

        self.assertFalse(
            self.fsm_project_employee_rate.task_count,
            "No task should be created in that fsm project.",
        )
        self.assertFalse(
            self.fsm_project_employee_rate._get_sale_order_items(),
            "No SOL should be fetched since no task exists in that project.",
        )
        self.assertFalse(
            self.fsm_project_employee_rate._get_sale_orders(),
            "No SOL should be fetched since no task exists in that project.",
        )

        self.task.write(
            {
                "partner_id": self.partner_1.id,
                "timesheet_ids": [
                    Command.create(
                        {
                            "name": "/",
                            "employee_id": self.employee_user.id,
                            "unit_amount": 1.0,
                            "project_id": self.fsm_project.id,
                        }
                    ),
                ],
            }
        )
        self.task.action_fsm_validate()
        self.assertTrue(self.task.fsm_done)
        self.assertTrue(
            self.task.sale_line_id, "The fsm task should have a SOL linked."
        )

        self.env.flush_all()
        self.assertEqual(
            self.fsm_project._get_sale_order_items(), self.task.sale_line_id
        )
        self.assertEqual(self.fsm_project._get_sale_orders(), self.task.sale_order_id)

    def test_projects_to_make_billable(self):
        Project = self.env["project.project"]
        Task = self.env["project.task"]
        _dummy, project2, project3 = Project.create(
            [
                {
                    "name": "Project with partner",
                    "partner_id": self.partner_1.id,
                    "allow_billable": False,
                    "is_fsm": True,
                    "company_id": self.env.company.id,
                },
                {
                    "name": "Project without partner",
                    "allow_billable": False,
                    "is_fsm": True,
                    "company_id": self.env.company.id,
                },
                {
                    "name": "Project without partner 2",
                    "allow_billable": False,
                    "is_fsm": True,
                    "company_id": self.env.company.id,
                },
            ]
        )
        Task.create(
            [
                {
                    "name": "Task with partner in project 2",
                    "project_id": project2.id,
                    "partner_id": self.partner_1.id,
                },
                {
                    "name": "Task without partner in project 2",
                    "project_id": project2.id,
                },
                {
                    "name": "Task without partner in project 3",
                    "project_id": project3.id,
                },
            ]
        )
        projects_to_make_billable = Project.search(
            Project._get_domain_projects_to_make_billable()
        )
        (non_billable_projects,) = Task._read_group(
            Task._get_domain_projects_to_make_billable(
                [("project_id", "not in", projects_to_make_billable.ids)]
            ),
            [],
            ["project_id:recordset"],
        )[0]
        projects_to_make_billable += non_billable_projects
        self.assertEqual(
            projects_to_make_billable,
            Project,
            "No fsm project should be fetched to make them billable.",
        )

    def test_quotation_creation_from_task(self):
        project = self.env["project.project"].create(
            {
                "name": "Extra Quotation Project",
                "partner_id": self.partner_1.id,
                "allow_billable": True,
                "allow_quotations": True,
            }
        )
        task = self.env["project.task"].create(
            {
                "name": "Task",
                "project_id": project.id,
                "partner_id": self.partner_1.id,
            }
        )
        quotation_context = task.action_fsm_create_quotation()["context"]
        quotation = self.env["sale.order"].with_context(quotation_context).create({})
        self.assertTrue(
            quotation.company_id, "the company on the sales order must be set"
        )
        self.assertEqual(quotation.task_id, task)
        self.assertEqual(quotation.partner_id, task.partner_id)

    def test_sale_order_creation(self):
        project = self.env["project.project"].create(
            {
                "name": "Test Project",
                "partner_id": self.partner_1.id,
                "allow_billable": True,
                "allow_material": True,
            }
        )
        task = self.env["project.task"].create(
            {
                "name": "Test Task",
                "project_id": project.id,
                "partner_id": self.partner_1.id,
            }
        )
        task.with_user(self.project_user).action_fsm_view_material()

        self.consu_product_ordered.with_user(self.project_user).with_context(
            {"fsm_task_id": task.id}
        ).set_fsm_quantity(5)
        self.assertEqual(
            task.material_line_product_count,
            5,
            "5 products should be linked to the task",
        )

        self.assertTrue(
            task.sale_order_id,
            "A sale order should be created on tasks if allow_material is true",
        )
