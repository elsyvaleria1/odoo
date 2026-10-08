from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_project_base import TestProjectCommon


@tagged("post_install", "-at_install")
class TestProjectReviewTagNameCreate(TestProjectCommon):
    def test_wildcards_in_a_new_name_match_literally(self) -> None:
        Tag = self.env["project.tags"]
        existing = Tag.create({"name": "50 days"})
        tag_id, name = Tag.name_create("50%")
        self.assertNotEqual(tag_id, existing.id)
        self.assertEqual(name, "50%")
        underscore = Tag.create({"name": "AxB"})
        tag_id, _name = Tag.name_create("A_B")
        self.assertNotEqual(tag_id, underscore.id)

    def test_case_insensitive_match_is_reused(self) -> None:
        Tag = self.env["project.tags"]
        existing = Tag.create({"name": "Urgent"})
        self.assertEqual(Tag.name_create(" urgent ")[0], existing.id)


@tagged("post_install", "-at_install")
class TestProjectReviewPartnerCompany(TestProjectCommon):
    def setUp(self) -> None:
        super().setUp()
        self.company_b = self.env["res.company"].create({"name": "Partner Co"})
        self.partner = self.env["res.partner"].create({"name": "Customer"})

    def test_company_change_against_a_project_is_refused(self) -> None:
        self.env["project.project"].create(
            {
                "name": "Customer project",
                "partner_id": self.partner.id,
                "company_id": self.env.company.id,
            }
        )
        with self.assertRaises(UserError):
            self.partner.company_id = self.company_b
        self.partner.company_id = self.env.company

    def test_company_change_against_a_task_is_refused(self) -> None:
        project = self.env["project.project"].create(
            {"name": "Task project", "company_id": self.env.company.id}
        )
        self.env["project.task"].create(
            {"name": "Task", "project_id": project.id, "partner_id": self.partner.id}
        )
        with self.assertRaises(UserError):
            self.partner.company_id = self.company_b
        self.partner.company_id = self.env.company

    def test_company_free_records_do_not_block(self) -> None:
        self.env["project.project"].create(
            {"name": "Free", "partner_id": self.partner.id}
        )
        self.partner.company_id = self.company_b
        self.assertEqual(self.partner.company_id, self.company_b)
