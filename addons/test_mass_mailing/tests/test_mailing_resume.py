from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.mail.wizards.wizard_mail_message_send import (
    MassMailProgress,
    WizardMailMessageSend,
)
from odoo.addons.test_mass_mailing.tests.common import TestMassMailCommon


@tagged("mass_mailing")
class TestMassMailingResume(TestMassMailCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customers = cls.env["res.partner"].create(
            [
                {"name": f"Resume {index}", "email": f"resume.{index}@example.com"}
                for index in range(3)
            ]
        )

    def _mailing(self):
        return self.env["mailing.mailing"].create(
            {
                "name": "Resumable",
                "subject": "Resumable",
                "body_html": "<p>Hello</p>",
                "mailing_model_id": self.env["ir.model"]._get("res.partner").id,
                "mailing_domain": repr([("id", "in", self.customers.ids)]),
            }
        )

    def test_a_mailing_the_composer_did_not_finish_stays_sending(self):
        mailing = self._mailing()
        mailing.action_put_in_queue()

        def stopped_on_budget(composer, auto_commit=False):
            composer.env.context["mail_composer_progress"].stopped = True
            return composer.env["mail.mail"], composer.env["mail.message"]

        with patch.object(
            WizardMailMessageSend, "_action_send_mail", stopped_on_budget
        ):
            mailing._action_send_mail()
        self.assertEqual(mailing.state, "sending")
        with self.mock_mail_gateway():
            mailing._action_send_mail()
        self.assertEqual(mailing.state, "done")

    def test_a_resumable_mass_mail_stops_on_a_spent_budget(self):
        composer = (
            self.env["wizard.mail.message.send"]
            .with_context(
                default_composition_mode="mass_mail",
                default_model="res.partner",
                active_ids=self.customers.ids,
            )
            .create({"subject": "Budget", "body": "<p>Budget</p>", "force_send": False})
        )
        IrCron = type(self.env["ir.cron"])
        progress = MassMailProgress()
        with (
            patch.object(WizardMailMessageSend, "_batch_size", 1),
            patch.object(IrCron, "_commit_progress", return_value=0),
            self.mock_mail_gateway(),
        ):
            mails = composer.with_context(
                mail_composer_progress=progress
            )._action_send_mail_mass_mail(self.customers.ids, auto_commit=True)
            self.assertEqual(len(mails), 1)
            self.assertTrue(progress.stopped)
            mails = composer._action_send_mail_mass_mail(
                self.customers.ids, auto_commit=True
            )
        self.assertEqual(len(mails), 3, "without a progress holder it finishes")
