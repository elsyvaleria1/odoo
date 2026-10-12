from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged, users
from odoo.tests.common import warmup
from odoo.tools import mute_logger

from odoo.addons.marketing_automation.models.marketing_activity import MarketingActivity
from odoo.addons.marketing_automation.models.marketing_participant import (
    MarketingParticipant,
)
from odoo.addons.marketing_automation.models.marketing_trace import MarketingTrace
from odoo.addons.test_mail.tests.test_performance import BaseMailPerformance
from odoo.addons.test_marketing_automation.tests.common import TestMACommon


@tagged("mail_performance", "marketing_automation", "post_install", "-at_install")
class MAPerformanceCommon(BaseMailPerformance, TestMACommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.date_reference = fields.Datetime.from_string("2024-07-15 10:30:00")

    @contextmanager
    def mockMACalls(self):
        original_act_execute_lines = MarketingActivity._execute_lines
        original_part_create = MarketingParticipant.create
        original_part_search = MarketingParticipant.search
        original_part_write = MarketingParticipant.write
        original_trace_create = MarketingTrace.create
        original_trace_search = MarketingTrace.search
        original_trace_write = MarketingTrace.write

        with (
            patch.object(
                MarketingActivity,
                "_execute_lines",
                autospec=True,
                side_effect=original_act_execute_lines,
            ) as mock_act_execute_lines,
            patch.object(
                MarketingParticipant,
                "create",
                autospec=True,
                side_effect=original_part_create,
            ) as mock_part_create,
            patch.object(
                MarketingParticipant,
                "search",
                autospec=True,
                side_effect=original_part_search,
            ) as mock_part_search,
            patch.object(
                MarketingParticipant,
                "write",
                autospec=True,
                side_effect=original_part_write,
            ) as mock_part_write,
            patch.object(
                MarketingTrace,
                "create",
                autospec=True,
                side_effect=original_trace_create,
            ) as mock_trace_create,
            patch.object(
                MarketingTrace,
                "search",
                autospec=True,
                side_effect=original_trace_search,
            ) as mock_trace_search,
            patch.object(
                MarketingTrace, "write", autospec=True, side_effect=original_trace_write
            ) as mock_trace_write,
        ):
            self._mock_act_execute_lines = mock_act_execute_lines
            self._mock_part_create = mock_part_create
            self._mock_part_search = mock_part_search
            self._mock_part_write = mock_part_write
            self._mock_trace_create = mock_trace_create
            self._mock_trace_search = mock_trace_search
            self._mock_trace_write = mock_trace_write
            yield

    @classmethod
    def _create_test_campaign(cls, campaign_domain=None):
        campaign_domain = campaign_domain or [("name", "!=", "Invalid")]
        test_campaign = (
            cls.env["marketing.campaign"]
            .with_user(cls.user_marketing_automation)
            .create(
                {
                    "domain": campaign_domain,
                    "model_id": cls.env["ir.model"]._get_id(
                        "marketing.test.performance"
                    ),
                    "name": "Test Campaign",
                }
            )
        )
        act1_begin_mailing = cls._create_activity_mail(
            test_campaign,
            mailing_values={
                "email_from": cls.user_marketing_automation.email_formatted,
                "keep_archives": True,
            },
            act_values={
                "interval_number": 1,
                "interval_type": "hour",
                "trigger_type": "begin",
            },
        )
        _act1_1_sms = cls._create_activity_mail(
            test_campaign,
            mailing_values={
                "body_plaintext": "SMS for {{ object.name }}: please confirm on https://test.example.com/confirm_mail",
                "mailing_type": "sms",
                "sms_allow_unsubscribe": True,
            },
            act_values={
                "interval_number": 1,
                "interval_type": "hour",
                "parent_id": act1_begin_mailing.id,
                "trigger_type": "mail_open",
            },
        )
        _act1_2_sa = cls._create_activity_sa(
            test_campaign,
            "records.write({'selection_field': 'key1'})",
            act_values={
                "activity_domain": [("email_from", "!=", False)],
                "interval_number": 1,
                "interval_type": "day",
                "parent_id": act1_begin_mailing.id,
                "trigger_type": "mail_not_open",
            },
        )

        act2_begin_sms = cls._create_activity_mail(
            test_campaign,
            mailing_values={
                "body_plaintext": "SMS for {{ object.name }}: mega promo on https://test.example.com/promo",
                "mailing_type": "sms",
                "keep_archives": True,
            },
            act_values={
                "interval_number": 2,
                "interval_type": "hour",
                "trigger_type": "begin",
            },
        )
        _act2_1_sms = cls._create_activity_mail(
            test_campaign,
            mailing_values={
                "body_plaintext": "SMS for {{ object.name }}: please confirm on https://test.example.com/confirm_sms",
                "mailing_type": "sms",
                "sms_allow_unsubscribe": True,
            },
            act_values={
                "interval_number": 1,
                "interval_type": "hour",
                "parent_id": act2_begin_sms.id,
                "trigger_type": "sms_click",
            },
        )
        _act2_2_sa = cls._create_activity_sa(
            test_campaign,
            "records.write({'selection_field': 'key2'})",
            act_values={
                "activity_domain": [("phone_ids", "!=", False)],
                "interval_number": 1,
                "interval_type": "day",
                "parent_id": act2_begin_sms.id,
                "trigger_type": "sms_not_click",
            },
        )

        act3_begin_wa = cls._create_activity_wa(
            test_campaign,
            template_values={
                "name": f"TestTemplate for {test_campaign.id}",
            },
            act_values={
                "interval_number": 3,
                "interval_type": "hour",
                "trigger_type": "begin",
            },
        )
        _act3_1_sms = cls._create_activity_mail(
            test_campaign,
            mailing_values={
                "body_plaintext": "SMS for {{ object.name }}: please confirm on https://test.example.com/confirm_wa",
                "mailing_type": "sms",
                "sms_allow_unsubscribe": True,
            },
            act_values={
                "interval_number": 1,
                "interval_type": "hour",
                "parent_id": act3_begin_wa.id,
                "trigger_type": "whatsapp_replied",
            },
        )
        _act3_2_sa = cls._create_activity_sa(
            test_campaign,
            "records.write({'selection_field': 'key3'})",
            act_values={
                "activity_domain": [("phone_ids", "!=", False)],
                "interval_number": 1,
                "interval_type": "day",
                "parent_id": act3_begin_wa.id,
                "trigger_type": "whatsapp_not_replied",
            },
        )

        _act4 = cls._create_activity_sa(
            test_campaign,
            "records.write({'selection_field': 'key1'})",
            act_values={
                "interval_number": 4,
                "interval_type": "hour",
                "trigger_type": "begin",
            },
        )

        return test_campaign

    @classmethod
    def _create_test_records(cls, count=200):
        return cls._create_marketauto_records(
            model="marketing.test.performance",
            count=count,
        )


@tagged("mail_performance", "post_install", "-at_install")
class TestMAPerformance(MAPerformanceCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_records = cls._create_test_records()

    def setUp(self):
        super().setUp()
        with self.mock_datetime_and_now(self.date_reference):
            self.test_campaign = self._create_test_campaign()
        self._launch_campaign(self.test_campaign, date_reference=self.date_reference)

    def test_assert_initial_values(self):
        self.assertEqual(len(self.test_records), 1000)

        self.assertFalse(self.test_campaign.require_sync)
        self.assertEqual(self.test_campaign.last_sync_date, self.date_reference)
        self.assertEqual(
            len(self.test_campaign.marketing_activity_ids.trace_ids),
            len(self.test_records) * 4,
            "Should have generated one trace / begin activity / campaign record",
        )
        self.assertEqual(
            len(self.test_campaign.participant_ids),
            len(self.test_records),
            "Should have generated one participant / campaign record",
        )

    @warmup
    def test_campaign_sync_participants_launch(self):
        with self.mock_datetime_and_now(self.date_reference):
            campaign = self._create_test_campaign()
        self.assertEqual(len(self.test_records), 1000)

        with (
            self.assertQueryCount(563),
            self.mock_datetime_and_now(self.date_reference),
            self.mockMACalls(),
        ):
            campaign.sync_participants()

        self.assertEqual(len(campaign.participant_ids), len(self.test_records))
        self.assertEqual(
            self._mock_part_create.call_count,
            10,
            "Sync participants: created by batches of 100",
        )
        self.assertEqual(self._mock_part_search.call_count, 0)
        self.assertEqual(
            self._mock_part_write.call_count,
            0,
            "Sync participants: a participant's run is linked at creation",
        )
        self.assertEqual(
            self._mock_trace_create.call_count,
            10,
            "Sync participants: one batch of traces per batch of participants",
        )
        self.assertEqual(self._mock_trace_search.call_count, 0)
        self.assertEqual(self._mock_trace_write.call_count, 0)

    @mute_logger(
        "odoo.addons.mass_mailing_sms.models.mailing_mailing",
        "odoo.addons.mass_mailing.models.mailing",
    )
    @warmup
    def test_execute_activities_then_sync_participants(self):
        campaign = self.test_campaign

        with (
            self.assertQueryCount(12943),
            self.mock_datetime_and_now(self.date_reference + timedelta(hours=4)),
            self.mock_mail_gateway(),
            self.mockSMSGateway(),
            self.mockWhatsappGateway(),
            self.patchWhatsappCronTrigger(),
            self.mockMACalls(),
        ):
            campaign.execute_activities()

        self.assertEqual(
            len(self._new_mails),
            len(self.test_records) - 200,
            "Should have sent one email / campaign record, minus canceled ones "
            "(no valid email -> no email created), aka 1000 - 200",
        )
        self.assertEqual(
            len(self._new_sms),
            len(self.test_records) - 200,
            "Should have sent one SMS / campaign record, minus canceled ones "
            "(no valid number -> no sms created), aka 1000 - 200",
        )
        self.assertEqual(
            len(self._new_wa_msg),
            len(self.test_records),
            "Should have sent one WA / campaign record, aka 1000",
        )
        self.assertEqual(
            len(campaign.marketing_activity_ids.trace_ids),
            len(self.test_records) * 10,
            "Should have: 4 begin activity + 6 sub activities / record, aka 10 * 1000",
        )
        self.assertEqual(
            self._mock_act_execute_lines.call_count,
            8,
            "4 activities * 2 batch / activity",
        )
        self.assertEqual(self._mock_part_create.call_count, 0)
        self.assertEqual(self._mock_part_search.call_count, 0)
        self.assertEqual(self._mock_part_write.call_count, 0)
        self.assertEqual(
            self._mock_trace_create.call_count,
            12,
            "Child traces: created in one batch per settled batch of parents",
        )
        self.assertEqual(self._mock_trace_search.call_count, 22)
        self.assertEqual(
            self._mock_trace_write.call_count,
            1000,
            "One write per WhatsApp trace, linking it to its message",
        )
        self.assertEqual(
            self.mail_mail_create_mocked.call_count,
            20,
            "Done by batch size inside activity execution batch (2 * 10)",
        )
        self.assertEqual(
            self._mock_sms_create.call_count,
            2,
            "Done by activity execution batch (500 currently)",
        )
        self.assertEqual(
            self._mock_wa_msg_create.call_count,
            2,
            "Done by activity execution batch (500 currently)",
        )

        self.test_records_new = self._create_test_records(count=10)
        self.assertEqual(len(self.test_records_new), 50)
        self.test_records[:50].unlink()

        with (
            self.assertQueryCount(69),
            self.mock_datetime_and_now(self.date_reference + timedelta(hours=24)),
            self.mockMACalls(),
        ):
            campaign.sync_participants()

        self.assertEqual(
            len(campaign.participant_ids),
            1050,
            "Removed records still have their participant, set as unlinked",
        )
        self.assertEqual(self._mock_part_create.call_count, 1)
        self.assertEqual(self._mock_part_search.call_count, 1)
        self.assertEqual(self._mock_part_write.call_count, 1)
        self.assertEqual(self._mock_trace_create.call_count, 1, "Created in one batch")
        self.assertEqual(self._mock_trace_search.call_count, 0)
        self.assertEqual(self._mock_trace_write.call_count, 0)

    @users("user_marketing_automation")
    @warmup
    def test_update_participants(self):
        campaign = self.test_campaign.with_env(self.env)

        activity_mail = campaign.marketing_activity_ids.filtered(
            lambda a: a.trigger_type == "begin" and a.activity_type == "email"
        )
        self.assertTrue(activity_mail)
        activity_mail.write(
            {
                "interval_number": 2,
            }
        )

        new_activity_begin = self._create_activity_mail(
            campaign,
            user=self.env.user,
            act_values={
                "interval_number": 1,
                "interval_type": "day",
                "name": "New begin MAIL activity",
                "trigger_type": "begin",
            },
        )
        _new_activity_sub = self._create_activity_sa(
            campaign,
            "records.write({'selection_field': 'key3'})",
            act_values={
                "activity_domain": [("email_from", "!=", False)],
                "interval_number": 1,
                "interval_type": "day",
                "parent_id": new_activity_begin.id,
                "trigger_type": "mail_not_open",
            },
        )

        with (
            self.assertQueryCount(130),
            self.mockMACalls(),
            self.mock_datetime_and_now(self.date_reference + timedelta(hours=2)),
        ):
            campaign.action_update_participants()

        self.assertEqual(self._mock_part_create.call_count, 0)
        self.assertEqual(self._mock_part_search.call_count, 0)
        self.assertEqual(self._mock_part_write.call_count, 0)
        self.assertEqual(
            self._mock_trace_create.call_count,
            1,
            "New traces for new begin activity created in one batch",
        )
        self.assertEqual(self._mock_trace_search.call_count, 0)
        self.assertEqual(
            self._mock_trace_write.call_count,
            0,
            "Rescheduling moves the steps; the traces follow by computation",
        )
