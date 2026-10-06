from datetime import timedelta

from odoo.fields import Date
from odoo.tests import TransactionCase


class TestPostponedPost(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.platform = cls.env["hr.recruitment.platform"].create({"name": "Board"})
        cls.job = cls.env["hr.job"].create({"name": "Picker", "is_published": True})

    def _post_tomorrow(self, apply_method, **vals):
        wizard = (
            self.env["wizard.hr.job.create.post"]
            .with_context(active_model="hr.job", active_id=self.job.id)
            .create(
                {
                    "job_id": self.job.id,
                    "platform_ids": self.platform.ids,
                    "apply_method": apply_method,
                    "post_html": "<p>Picker</p>",
                    "campaign_start_date": Date.today() + timedelta(days=1),
                    **vals,
                }
            )
        )
        wizard.action_post_job()
        return self.env["hr.job.post"].search([("job_id", "=", self.job.id)])

    def test_a_postponed_redirect_post_keeps_the_job_page(self):
        post = self._post_tomorrow("redirect")
        self.assertEqual(post.status, "pending")
        self.assertEqual(post.apply_vector, self.job.full_url)

    def test_a_postponed_email_post_keeps_the_address(self):
        post = self._post_tomorrow("email", job_apply_mail="jobs@example.com")
        self.assertEqual(post.status, "pending")
        self.assertEqual(post.apply_vector, "jobs@example.com")
