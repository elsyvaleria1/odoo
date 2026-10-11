"""Comprehensive tests for time-based automation triggers.

Tests cover:
- on_time (custom date field)
- on_time_created (automatic create_date)
- on_time_updated (automatic write_date)
- Cron processing
- Domain filtering
- Last run tracking
- Edge cases
"""

import datetime
import logging
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestTimeBasedTriggers(common.TransactionCase):
    """Test time-based triggers (on_time, on_time_created, on_time_updated)."""

    def _run_cron(self):
        IrCron = type(self.env["ir.cron"])
        with patch.object(IrCron, "_commit_progress", return_value=float("inf")):
            self.env["automation.rule"]._cron_process_time_based_actions()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Automation = cls.env["automation.rule"]
        cls.Action = cls.env["ir.actions.server"]
        cls.Lead = cls.env["automation.lead.test"]

        cls.model_lead = cls.env["ir.model"]._get("automation.lead.test")


    def test_on_time_trigger_setup(self):
        _logger.info("Testing on_time trigger setup")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "One Day After Creation",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        self.Action.create(
            {
                "name": "Time Trigger Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'One day passed'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        self.assertEqual(automation.trigger, "on_time")
        self.assertEqual(automation.trg_date_id, date_field)
        self.assertEqual(automation.trg_date_range, 1)
        self.assertEqual(automation.trg_date_range_type, "day")

    def test_on_time_created_trigger_setup(self):
        _logger.info("Testing on_time_created trigger setup")

        automation = self.Automation.create(
            {
                "name": "2 Hours After Creation",
                "model_id": self.model_lead.id,
                "trigger": "on_time_created",
                "trg_date_range": 2,
                "trg_date_range_type": "hour",
            }
        )

        self.Action.create(
            {
                "name": "After Creation Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': '2 hours passed'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        self.assertEqual(automation.trigger, "on_time_created")
        self.assertEqual(automation.trg_date_range, 2)
        self.assertEqual(automation.trg_date_range_type, "hour")

    def test_on_time_updated_trigger_setup(self):
        _logger.info("Testing on_time_updated trigger setup")

        automation = self.Automation.create(
            {
                "name": "30 Minutes After Update",
                "model_id": self.model_lead.id,
                "trigger": "on_time_updated",
                "trg_date_range": 30,
                "trg_date_range_type": "minute",
            }
        )

        self.Action.create(
            {
                "name": "After Update Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': '30 minutes since update'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        self.assertEqual(automation.trigger, "on_time_updated")
        self.assertEqual(automation.trg_date_range, 30)
        self.assertEqual(automation.trg_date_range_type, "minute")

    def test_time_trigger_all_range_types(self):
        _logger.info("Testing all time range types")

        for range_type in ["minute", "hour", "day", "month"]:
            automation = self.Automation.create(
                {
                    "name": f"Time Trigger {range_type}",
                    "model_id": self.model_lead.id,
                    "trigger": "on_time_created",
                    "trg_date_range": 5,
                    "trg_date_range_type": range_type,
                }
            )

            self.assertEqual(automation.trg_date_range_type, range_type)


    def test_search_time_based_records_on_time(self):
        _logger.info("Testing time-based record search for on_time")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "1 Day After",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)
        one_day_ago = now - datetime.timedelta(days=1, hours=1)
        one_hour_ago = now - datetime.timedelta(hours=1)

        lead1 = self.Lead.create({"name": "Old Lead"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead1.id),
        )

        lead2 = self.Lead.create({"name": "Recent Lead"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (one_day_ago, lead2.id),
        )

        lead3 = self.Lead.create({"name": "Very Recent Lead"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (one_hour_ago, lead3.id),
        )

        self.env.invalidate_all()

        records = automation._search_time_based_automation_records(until=now)

        self.assertIn(lead1, records)
        self.assertIn(lead2, records)
        self.assertNotIn(lead3, records)

    def test_search_time_based_records_with_domain_filter(self):
        _logger.info("Testing time trigger with domain filter")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "Priority Only Time Trigger",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
                "filter_domain": "[('priority', '=', True)]",
            }
        )

        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)

        priority_lead = self.Lead.create({"name": "Priority Lead", "priority": True})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, priority_lead.id),
        )

        regular_lead = self.Lead.create({"name": "Regular Lead", "priority": False})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, regular_lead.id),
        )

        self.env.invalidate_all()

        records = automation._search_time_based_automation_records(until=now)

        self.assertIn(priority_lead, records)
        self.assertNotIn(regular_lead, records)

    def test_time_trigger_last_run_tracking(self):
        _logger.info("Testing last_run tracking")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "Last Run Test",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        now = fields.Datetime.now()
        four_days_ago = now - datetime.timedelta(days=4)
        two_days_ago = now - datetime.timedelta(days=2)

        lead = self.Lead.create({"name": "Test Lead"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (four_days_ago, lead.id),
        )
        self.env.invalidate_all()

        records1 = automation._search_time_based_automation_records(until=now)
        self.assertIn(lead, records1)

        automation.write({"last_run": two_days_ago})

        records2 = automation._search_time_based_automation_records(until=now)
        self.assertNotIn(lead, records2)


    def test_cron_process_time_based_actions(self):
        _logger.info("Testing cron processing of time triggers")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "Cron Test Automation",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        self.Action.create(
            {
                "name": "Cron Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Cron executed'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)

        lead = self.Lead.create({"name": "Cron Target"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Cron executed")

        self.assertTrue(automation.last_run)
        self.assertGreaterEqual(automation.last_run, self.env.cr.now())

    def test_cron_processes_multiple_automations(self):
        _logger.info("Testing cron with multiple automations")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )
        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)

        automation1 = self.Automation.create(
            {
                "name": "Auto 1",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )
        self.Action.create(
            {
                "name": "Action 1",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Auto1'})",
                "automation_rule_id": automation1.id,
                "usage": "automation",
            }
        )

        automation2 = self.Automation.create(
            {
                "name": "Auto 2",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )
        self.Action.create(
            {
                "name": "Action 2",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'state': 'open'})",
                "automation_rule_id": automation2.id,
                "usage": "automation",
            }
        )

        lead = self.Lead.create({"name": "Multi Auto", "state": "draft"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Auto1")
        self.assertEqual(lead.state, "open")

    def test_cron_skips_inactive_automations(self):
        _logger.info("Testing cron skips inactive automations")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )

        automation = self.Automation.create(
            {
                "name": "Inactive Automation",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
                "active": False,
            }
        )

        self.Action.create(
            {
                "name": "Should Not Execute",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Should not see this'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)

        lead = self.Lead.create({"name": "Test Lead"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Test Lead")


    def test_on_time_created_uses_create_date(self):
        _logger.info("Testing on_time_created uses create_date")

        automation = self.Automation.create(
            {
                "name": "On Time Created",
                "model_id": self.model_lead.id,
                "trigger": "on_time_created",
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        self.Action.create(
            {
                "name": "Created Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Created trigger'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        now = fields.Datetime.now()
        two_days_ago = now - datetime.timedelta(days=2)

        lead = self.Lead.create({"name": "Created Test"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Created trigger")

    def test_on_time_updated_uses_write_date(self):
        _logger.info("Testing on_time_updated uses write_date")

        automation = self.Automation.create(
            {
                "name": "On Time Updated",
                "model_id": self.model_lead.id,
                "trigger": "on_time_updated",
                "trg_date_range": 1,
                "trg_date_range_type": "hour",
            }
        )

        self.Action.create(
            {
                "name": "Updated Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Updated trigger'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        now = fields.Datetime.now()
        three_hours_ago = now - datetime.timedelta(hours=3)

        lead = self.Lead.create({"name": "Updated Test"})
        lead.write({"state": "open"})

        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET write_date = %s WHERE id = %s",
            (three_hours_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Updated trigger")


    def test_time_trigger_with_missing_date_field(self):
        _logger.info("Testing time trigger with missing field")

        automation = self.Automation.create(
            {
                "name": "Missing Field",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )

        foreign_field = self.env["ir.model.fields"]._get("res.users", "login_date")
        self.assertTrue(foreign_field, "fixture: res.users.login_date must exist")
        self.assertNotIn(
            foreign_field.name,
            self.env[self.model_lead.model]._fields,
            "precondition: the field must be absent from the automation's model",
        )
        self.env.cr.execute(
            "UPDATE automation_rule SET trg_date_id = %s WHERE id = %s",
            (foreign_field.id, automation.id),
        )
        self.env.invalidate_all()

        now = fields.Datetime.now()

        records = automation._search_time_based_automation_records(until=now)
        self.assertFalse(records)

    def test_time_trigger_validation_negative_range(self):
        _logger.info("Testing negative range validation")

        with self.assertRaises(ValidationError):
            self.Automation.create(
                {
                    "name": "Negative Range",
                    "model_id": self.model_lead.id,
                    "trigger": "on_time_created",
                    "trg_date_range": -5,
                    "trg_date_range_type": "day",
                }
            )

    def test_time_trigger_multiple_range_types_same_model(self):
        _logger.info("Testing multiple range types")

        date_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "create_date"
        )
        now = fields.Datetime.now()

        auto_hour = self.Automation.create(
            {
                "name": "Hour Range",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "hour",
            }
        )
        self.Action.create(
            {
                "name": "Hour Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Hour'})",
                "automation_rule_id": auto_hour.id,
                "usage": "automation",
            }
        )

        auto_day = self.Automation.create(
            {
                "name": "Day Range",
                "model_id": self.model_lead.id,
                "trigger": "on_time",
                "trg_date_id": date_field.id,
                "trg_date_range": 1,
                "trg_date_range_type": "day",
            }
        )
        self.Action.create(
            {
                "name": "Day Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'state': 'open'})",
                "automation_rule_id": auto_day.id,
                "usage": "automation",
            }
        )

        two_days_ago = now - datetime.timedelta(days=2)
        lead = self.Lead.create({"name": "Multi Range", "state": "draft"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (two_days_ago, lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Hour")
        self.assertEqual(lead.state, "open")

    def test_time_trigger_with_zero_range(self):
        _logger.info("Testing zero range")

        automation = self.Automation.create(
            {
                "name": "Zero Range",
                "model_id": self.model_lead.id,
                "trigger": "on_time_created",
                "trg_date_range": 0,
                "trg_date_range_type": "day",
            }
        )

        self.Action.create(
            {
                "name": "Zero Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Zero range'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        lead = self.Lead.create({"name": "Zero Test"})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE automation_lead_test SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - datetime.timedelta(minutes=5), lead.id),
        )
        self.env.invalidate_all()

        self._run_cron()

        self.assertEqual(lead.name, "Zero range")
