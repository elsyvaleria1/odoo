from unittest.mock import patch

from odoo.exceptions import RedirectWarning
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.hr_recruitment_integration_base.models.hr_job_post import HrJobPost


class TestHrJobPostDoubleCheck(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, "job_post_manager", "hr_recruitment.group_hr_recruitment_manager"
        )
        platform = cls.env["hr.recruitment.platform"].create(
            {"name": "Board", "price_to_update": 5.0}
        )
        job = cls.env["hr.job"].create({"name": "Picker"})
        cls.post = cls.env["hr.job.post"].create(
            {
                "job_id": job.id,
                "platform_id": platform.id,
                "post_html": "<p>x</p>",
                "status": "success",
            }
        )

    def test_the_confirmation_does_not_carry_a_user_to_run_as(self):
        with self.assertRaises(RedirectWarning) as refused:
            self.post.with_user(self.manager).action_update_job_post_check()
        self.assertNotIn("uid", refused.exception.args[3])

    def test_the_confirmed_update_runs_as_its_caller_whatever_uid_the_context_names(
        self,
    ):
        ran_as = []

        def record_user(posts):
            ran_as.append((posts.env.uid, posts.env.su))

        action = self.env.ref(
            "hr_recruitment_integration_base.hr_job_post_double_check_action"
        )
        with patch.object(HrJobPost, "action_update_job_post", record_user):
            action.with_user(self.manager).with_context(
                active_model="hr.job.post",
                active_id=self.post.id,
                uid=self.env.ref("base.user_admin").id,
            ).run()
        self.assertEqual(ran_as, [(self.manager.id, False)])


class TestHrJobPostLog(TransactionCase):
    def test_the_modification_log_escapes_the_values_it_lists(self):
        platform = self.env["hr.recruitment.platform"].create({"name": "Board"})
        job = self.env["hr.job"].create({"name": "<b>Picker</b>"})
        post = self.env["hr.job.post"].create(
            {
                "job_id": job.id,
                "platform_id": platform.id,
                "post_html": "<p>x</p>",
                "status": "success",
            }
        )
        (message,) = post.message_ids.filtered(lambda m: "Job:" in m.body)
        self.assertIn("<strong>Job:</strong>", message.body)
        self.assertIn("&lt;b&gt;Picker&lt;/b&gt;", message.body)
