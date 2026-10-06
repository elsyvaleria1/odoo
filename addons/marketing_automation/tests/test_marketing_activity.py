from odoo import fields
from odoo.tests import Form
from odoo.tools import mute_logger

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCommon


class TestMarketingActivity(MarketingAutomationCommon):
    def test_activity_summary(self):
        activity_form = Form(self.env["marketing.activity"])
        activity_form.name = "Test Activity"
        activity_form.interval_number = 3
        activity_form.interval_type = None
        self.assertEqual(activity_form.activity_summary, "")

        activity_form.interval_type = "day"
        activity_form.validity_duration = True
        activity_form.validity_duration_number = 5
        activity_form.validity_duration_type = "hour"
        self.assertIn("3 Days", activity_form.activity_summary)
        self.assertIn("5 Hours", activity_form.activity_summary)

        activity_form.validity_duration_type = None
        self.assertEqual(activity_form.activity_summary, "")


class TestServerActionActivity(MarketingAutomationCommon):
    @mute_logger(
        "odoo.addons.marketing_automation.models.marketing_activity",
        "odoo.db.cursor",
    )
    def test_a_failing_action_does_not_poison_the_rest_of_the_batch(self):
        activity = self._create_activity_sa(
            self.campaign,
            "if record.name == 'MATest_0':\n"
            "    env.cr.execute('SELECT 1/0')\n"
            "record.write({'name': record.name + ' reached'})",
            act_values={"trigger_type": "begin", "interval_number": 0},
        )
        now = fields.Datetime.now()
        self._launch_campaign(self.campaign, date_reference=now)

        with self.mock_datetime_and_now(now):
            self.campaign.execute_activities()

        traces = activity.trace_ids
        failed = traces.filtered(lambda trace: trace.res_id == self.test_contacts[0].id)
        self.assertEqual(failed.state, "error")
        self.assertEqual(set((traces - failed).mapped("state")), {"processed"})
        self.test_contacts.invalidate_recordset(["name"])
        self.assertEqual(
            len(self.test_contacts.filtered(lambda c: c.name.endswith(" reached"))),
            9,
        )
