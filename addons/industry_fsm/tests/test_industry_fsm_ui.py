from odoo.tests import HttpCase, no_retry, tagged


@no_retry
@tagged("post_install", "-at_install")
class TestIndustryFsmUi(HttpCase):
    def test_ui(self):
        self.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )
        self.start_tour("/odoo", "industry_fsm_tour", login="admin")
        self.start_tour("/odoo", "fsm_task_form_tour", login="admin")
