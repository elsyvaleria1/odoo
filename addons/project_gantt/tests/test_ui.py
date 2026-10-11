import logging

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.mail.tests.common import mail_new_test_user

_logger = logging.getLogger(__name__)


@tagged("-at_install", "post_install")
class ProjectGanttTestUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        user_groups = "base.group_user,project.group_project_manager"
        if "account.move.line" in cls.env:
            user_groups += ",account.group_account_invoice"
        cls.user_project_manager = mail_new_test_user(
            cls.env,
            company_id=cls.env.company.id,
            email="gilbert.testuser@test.example.com",
            login="user_project_manager",
            groups=user_groups,
            name="Gilbert ProjectManager",
            tz="Europe/Brussels",
        )
        project = cls.env["project.project"].create(
            {
                "name": "Test Project",
            }
        )
        first_day_in_current_month = fields.Datetime.now() + relativedelta(
            day=1, hour=0, minute=0, second=0
        )
        cls.env["project.task"].create(
            {
                "project_id": project.id,
                "name": "Test Task",
                "date_start": first_day_in_current_month - relativedelta(months=1),
                "date_end": first_day_in_current_month
                + relativedelta(months=2, days=-1),
                "user_ids": cls.env.ref("base.user_admin"),
                "planned_hours": 1000.0,
            }
        )

    def test_01_ui(self):
        self.start_tour("/", "project_test_tour", login="admin")
