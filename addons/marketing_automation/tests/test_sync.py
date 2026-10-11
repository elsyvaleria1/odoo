from datetime import timedelta

from odoo.fields import Datetime
from odoo.tests import tagged, users
from odoo.tools import mute_logger

from odoo.addons.marketing_automation.tests.common import MarketingAutomationCommon


class SyncingCase(MarketingAutomationCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = Datetime.from_string("2023-11-08 09:00:00")
        cls.activity_1 = cls._create_activity_mail(
            cls.campaign,
            user=cls.user_marketing_automation,
            act_values={
                "create_date": cls.date_reference - timedelta(days=1),
                "trigger_type": "begin",
                "interval_number": 1,
                "interval_type": "hour",
            },
        )
        cls.activity_2 = cls._create_activity_mail(
            cls.campaign,
            user=cls.user_marketing_automation,
            act_values={
                "create_date": cls.date_reference - timedelta(days=1),
                "parent_id": cls.activity_1.id,
                "trigger_type": "activity",
                "interval_number": 1,
                "interval_type": "hour",
            },
        )
        cls.env.flush_all()


@tagged("marketing_automation", "ma_sync")
class TestDuplicate(SyncingCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.participants = cls.env["marketing.participant"].create(
            [
                {
                    "campaign_id": cls.campaign.id,
                    "res_id": record.id,
                    "state": "running",
                }
                for record in cls.test_contacts[:2]
                for idx in range(2)
            ]
        )
        cls.traces = cls.env["marketing.trace"].create(
            [
                {
                    "activity_id": cls.activity_1.id,
                    "participant_id": participant.id,
                    "state": state,
                }
                for participant, states in zip(
                    cls.participants,
                    (
                        ["scheduled", "processed"],
                        ["canceled", "processed"],
                        ["scheduled", "processed"],
                        ["processed", "processed"],
                    ),
                    strict=False,
                )
                for state in states
            ]
        )
        cls.mailing_traces = cls.env["mailing.trace"].create(
            [
                {
                    "marketing_trace_id": trace.id,
                    "model": cls.campaign.model_name,
                    "res_id": trace.res_id,
                    "sent_datetime": sent_dt,
                    "trace_status": trace_status,
                    "trace_type": "mail",
                }
                for trace, (sent_dt, trace_status) in zip(
                    cls.traces,
                    [
                        (False, "outgoing"),
                        (cls.date_reference, "sent"),
                        (cls.date_reference, "bounce"),
                        (False, "error"),
                        (False, "outgoing"),
                        (cls.date_reference, "sent"),
                        (cls.date_reference, "cancel"),
                        (False, "error"),
                    ],
                    strict=False,
                )
            ]
        )
        cls.env.flush_all()

    @users("user_marketing_automation")
    def test_statistics(self):
        campaign = self.campaign.with_env(self.env)
        activity_1 = self.activity_1.with_env(self.env)

        self.assertEqual(campaign.running_participant_count, 4)

        self.assertEqual(activity_1.processed, 5)
        self.assertEqual(activity_1.rejected, 0)
        self.assertEqual(activity_1.total_bounce, 1)
        self.assertEqual(activity_1.total_click, 0)
        self.assertEqual(activity_1.total_open, 0)
        self.assertEqual(activity_1.total_reply, 0)
        self.assertEqual(activity_1.total_sent, 4)


@tagged("marketing_automation", "ma_sync")
class TestSyncing(SyncingCase):

    @users("user_marketing_automation")
    def test_activity_require_sync(self):
        campaign = self.campaign.with_env(self.env)
        activity = self.activity_1.with_env(self.env)

        campaign.action_start_campaign()
        self.assertFalse(activity.require_sync)
        self.assertFalse(campaign.last_sync_date)
        self.assertFalse(campaign.require_sync)

        activity.interval_number = 3
        self.assertTrue(activity.require_sync)
        self.assertFalse(
            campaign.require_sync, 'Campaign without sync date is never "To Sync"'
        )
        campaign.last_sync_date = self.date_reference - timedelta(days=2)
        self.assertTrue(campaign.require_sync)

        activity.require_sync = False
        self.assertFalse(campaign.require_sync)
        activity.interval_type = "week"
        self.assertTrue(activity.require_sync)
        self.assertTrue(campaign.require_sync)

        with self.mock_datetime_and_now(self.date_reference):
            campaign.action_set_synchronized()
        self.assertFalse(activity.require_sync)
        self.assertEqual(campaign.last_sync_date, self.date_reference)
        self.assertFalse(campaign.require_sync)

    @mute_logger("odoo.addons.mass_mailing.models.mailing", "odoo.tests")
    def test_activity_schedule_date(self):
        marketing_campaign = self.env["marketing.campaign"].create(
            {
                "domain": [("id", "in", self.test_contacts.ids)],
                "model_id": self.env["ir.model"]._get_id(self.test_contacts._name),
                "name": "My First Campaign",
            }
        )
        parent_activity = self._create_activity_mail(marketing_campaign)
        child_activity = self._create_activity_mail(
            marketing_campaign,
            act_values={
                "parent_id": parent_activity.id,
                "trigger_type": "mail_not_open",
            },
        )

        self._launch_campaign(marketing_campaign)
        with self.mock_datetime_and_now(self.date_reference):
            [trace.action_execute() for trace in parent_activity.trace_ids]
        self.assertEqual(len(child_activity.trace_ids), len(self.test_contacts))

        child_activity.update(
            {
                "interval_type": "day",
                "interval_number": 5,
            }
        )
        marketing_campaign.action_update_participants()

        expected_schedule_date = self.date_reference + timedelta(days=5)
        for trace in child_activity.trace_ids:
            self.assertEqual(trace.schedule_date, expected_schedule_date)

    @users("user_marketing_automation")
    def test_assert_initial_values(self):
        campaign = self.campaign.with_env(self.env)
        self.assertFalse(campaign.last_sync_date)
        self.assertEqual(campaign.mass_mailing_count, 2)
        self.assertFalse(campaign.require_sync)
        for activity in campaign.marketing_activity_ids:
            self.assertEqual(
                activity.create_date, self.date_reference - timedelta(days=1)
            )
            self.assertFalse(activity.require_sync)
        self.assertFalse(campaign.participant_ids)
        self.assertEqual(campaign.running_participant_count, 0)
        self.assertEqual(campaign.completed_participant_count, 0)
        self.assertEqual(campaign.total_participant_count, 0)
        self.assertEqual(campaign.test_participant_count, 0)
        self.assertEqual(len(self.test_contacts), 10)

    @users("user_marketing_automation")
    def test_campaign_action_update_participants_no_last_sync_date(self):
        campaign = self.campaign.with_env(self.env)
        self.assertFalse(campaign.last_sync_date)

        with self.mock_datetime_and_now(self.date_reference):
            campaign.action_update_participants()
        self.assertEqual(campaign.last_sync_date, self.date_reference)
        self.assertFalse(campaign.participant_ids)
        self.assertActivityWoTrace(self.activity_1 + self.activity_2)

    @users("user_marketing_automation")
    def test_campaign_copy_dupes(self):
        campaign = self.campaign.with_env(self.env)
        with self.mock_datetime_and_now(self.date_reference):
            campaign.sync_participants()
        self.assertEqual(len(campaign.participant_ids), len(self.test_contacts))

        with self.mock_datetime_and_now(self.date_reference + timedelta(days=1)):
            new_campaign = campaign.copy()
            new_campaign.action_start_campaign()
        self.assertFalse(
            new_campaign.last_sync_date,
            "Copying a campaign should not copy its sync date",
        )
        self.assertEqual(len(new_campaign.marketing_activity_ids), 2)
        new_activity_1 = new_campaign.marketing_activity_ids.filtered(
            lambda a: a.trigger_type == "begin"
        )
        new_activity_2 = new_campaign.marketing_activity_ids.filtered(
            lambda a: a.trigger_type != "begin"
        )
        self.assertActivityWoTrace(new_activity_1 + new_activity_2)

        with self.mock_datetime_and_now(self.date_reference + timedelta(days=1)):
            new_campaign.sync_participants()
            new_campaign.action_update_participants()

        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts,
                    "status": "scheduled",
                }
            ],
            new_activity_1,
        )
        self.assertActivityWoTrace(new_activity_2)

    @users("user_marketing_automation")
    def test_campaign_sync_participants(self):
        campaign = self.campaign.with_env(self.env)
        with self.mock_datetime_and_now(self.date_reference):
            campaign.sync_participants()

        self.assertEqual(campaign.last_sync_date, self.date_reference)
        self.assertEqual(len(campaign.participant_ids), len(self.test_contacts))
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts,
                    "status": "scheduled",
                }
            ],
            self.activity_1,
        )
        self.assertActivityWoTrace(self.activity_2)

        new_contacts = self.env["mailing.contact"].create(
            [
                {
                    "country_id": self.env.ref("base.be").id,
                    "email": f"new.ma.test.contact.{idx}@example.com",
                    "name": f"MATest_{idx}_new",
                }
                for idx in range(5)
            ]
        )
        self.test_contacts[:5].unlink()
        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=1)):
            campaign.sync_participants()
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts[5:],
                    "status": "scheduled",
                },
                {
                    "records": new_contacts,
                    "status": "scheduled",
                },
            ],
            self.activity_1,
            canceled_res_ids=set(self.test_contacts[:5].ids),
        )
        self.assertActivityWoTrace(self.activity_2)

    @users("user_marketing_automation")
    def test_participants_creation_dupes(self):
        campaign = self.env["marketing.campaign"].create(
            {
                "domain": [("id", "=", self.test_contacts[0].id)],
                "model_id": self.env["ir.model"]._get_id(self.test_contacts._name),
                "marketing_activity_ids": [
                    (
                        0,
                        0,
                        {
                            "activity_type": "email",
                            "name": "Test Activity",
                            "trigger_type": "begin",
                        },
                    ),
                ],
                "name": "Test Participant Dupes",
            }
        )
        campaign.sync_participants()

        campaign.action_update_participants()

        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts[0],
                    "status": "scheduled",
                }
            ],
            campaign.marketing_activity_ids,
        )

    @users("user_marketing_automation")
    def test_participants_creation_then_update_dupes(self):
        campaign = self.campaign.with_env(self.env)

        with self.mock_datetime_and_now(self.date_reference):
            campaign.action_start_campaign()
            campaign.sync_participants()
            campaign.action_update_participants()

        self.assertEqual(len(campaign.participant_ids), len(self.test_contacts))
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts,
                    "status": "scheduled",
                }
            ],
            self.activity_1,
        )
        self.assertActivityWoTrace(self.activity_2)

        new_activity_begin = self._create_activity_mail(
            campaign,
            user=self.user_admin,
            act_values={
                "create_date": self.date_reference + timedelta(hours=1),
                "trigger_type": "begin",
                "interval_number": 1,
                "interval_type": "hour",
            },
        )
        new_activity_mail = self._create_activity_mail(
            campaign,
            user=self.env.user,
            act_values={
                "create_date": self.date_reference + timedelta(hours=1),
                "parent_id": self.activity_1.id,
                "trigger_type": "mail_open",
                "interval_number": 0,
            },
        )
        for activity in new_activity_begin + new_activity_mail:
            self.assertEqual(
                activity.create_date, self.date_reference + timedelta(hours=1)
            )
        self.assertEqual(campaign.last_sync_date, self.date_reference)
        self.assertTrue(
            campaign.require_sync, "Campaign should require a sync due to new activity"
        )

        new_record = self.env["mailing.contact"].create(
            {
                "email": "ma.test.new.1@example.com",
                "name": "MATest_new_1",
            }
        )
        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=2)):
            campaign.sync_participants()

        self.assertEqual(len(campaign.participant_ids), len(self.test_contacts) + 1)
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts + new_record,
                    "status": "scheduled",
                }
            ],
            self.activity_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": new_record,
                    "status": "scheduled",
                }
            ],
            new_activity_begin,
        )
        self.assertActivityWoTrace(new_activity_mail)

        with (
            self.mock_datetime_and_now(self.date_reference + timedelta(hours=3)),
            self.mock_mail_gateway(),
        ):
            campaign.execute_activities()
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts + new_record,
                    "status": "processed",
                    "trace_status": "sent",
                }
            ],
            self.activity_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": new_record,
                    "status": "processed",
                    "mail_values": {
                        "email_from": self.user_admin.email_formatted,
                    },
                    "trace_status": "sent",
                }
            ],
            new_activity_begin,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts + new_record,
                    "status": "scheduled",
                }
            ],
            new_activity_mail,
        )

        self.assertTrue(campaign.require_sync, "Campaign should require an update")
        with self.mock_datetime_and_now(self.date_reference + timedelta(hours=4)):
            campaign.action_update_participants()
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts + new_record,
                    "status": "processed",
                    "trace_status": "sent",
                }
            ],
            self.activity_1,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts,
                    "status": "scheduled",
                },
                {
                    "records": new_record,
                    "status": "processed",
                    "mail_values": {
                        "email_from": self.user_admin.email_formatted,
                    },
                    "trace_status": "sent",
                },
            ],
            new_activity_begin,
        )
        self.assertMarketAutoTraces(
            [
                {
                    "records": self.test_contacts + new_record,
                    "status": "scheduled",
                }
            ],
            new_activity_mail,
        )


@tagged("marketing_automation", "ma_sync")
class TestCampaignHoldsItsRule(SyncingCase):
    def test_a_stopped_campaign_pauses_its_rule_and_a_restarted_one_resumes_it(self):
        campaign = self.campaign
        rule = campaign.automation_rule_id.with_context(active_test=False)

        campaign.action_start_campaign()
        self.assertTrue(rule.active)
        self.assertFalse(rule.is_paused)

        campaign.action_stop_campaign()
        self.assertFalse(rule.active, "a stopped campaign starts no participant")
        self.assertTrue(rule.is_paused, "and holds the ones under way")

        campaign.action_start_campaign()
        self.assertTrue(rule.active)
        self.assertFalse(rule.is_paused)

    def test_a_draft_campaigns_rule_holds_its_test_participants(self):
        campaign = self.env["marketing.campaign"].create(
            {"name": "Draft Hold", "model_id": self.campaign.model_id.id}
        )
        rule = campaign.automation_rule_id.with_context(active_test=False)

        self.assertEqual(campaign.state, "draft")
        self.assertFalse(rule.active)
        self.assertTrue(rule.is_paused, "the hourly dispatcher leaves its runs alone")
