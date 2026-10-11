"""Comprehensive tests for webhook automation triggers.

Tests cover:
- Webhook setup and configuration (UUID, URL)
- Webhook execution with various payloads
- Actions integration (code, object_write, mail)
- Error handling
- Logging
- Edge cases
"""

import contextlib
import logging

from odoo.exceptions import ValidationError
from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests import common, tagged

from odoo.addons.integration.tests.common import open_admission

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestWebhookIntegration(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Automation = cls.env["automation.rule"]
        cls.Action = cls.env["ir.actions.server"]
        cls.Lead = cls.env["automation.lead.test"]
        cls.Project = cls.env["test_automation.project"]

        cls.model_lead = cls.env["ir.model"]._get("automation.lead.test")
        cls.model_project = cls.env["ir.model"]._get("test_automation.project")

        cls.test_lead = cls.Lead.create(
            {
                "name": "Webhook Test Lead",
            }
        )


    def test_webhook_trigger_creates_uuid(self):
        _logger.info("Testing webhook UUID generation")

        automation = self.Automation.create(
            {
                "name": "Webhook with UUID",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
            }
        )

        self.assertTrue(automation.webhook_uuid)
        self.assertEqual(len(automation.webhook_uuid), 36)

    def test_webhook_url_computed(self):
        _logger.info("Testing webhook URL computation")

        automation = self.Automation.create(
            {
                "name": "Webhook URL Test",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
            }
        )

        self.assertTrue(automation.url)
        self.assertIn("/web/hook/", automation.url)
        self.assertIn(automation.webhook_uuid, automation.url)

    def test_webhook_url_only_for_webhook_trigger(self):
        _logger.info("Testing webhook URL specificity")

        automation = self.Automation.create(
            {
                "name": "Not Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_create",
            }
        )

        self.assertFalse(automation.url)

    def test_webhook_uuid_rotation(self):
        _logger.info("Testing webhook UUID rotation")

        automation = self.Automation.create(
            {
                "name": "Webhook Rotation Test",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
            }
        )

        old_uuid = automation.webhook_uuid
        old_url = automation.url

        automation.action_rotate_webhook_uuid()

        self.assertNotEqual(automation.webhook_uuid, old_uuid)
        self.assertNotEqual(automation.url, old_url)
        self.assertIn(automation.webhook_uuid, automation.url)

    def test_webhook_uuid_unique(self):
        _logger.info("Testing webhook UUID uniqueness")

        automation1 = self.Automation.create(
            {
                "name": "Webhook 1",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
            }
        )

        automation2 = self.Automation.create(
            {
                "name": "Webhook 2",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
            }
        )

        self.assertNotEqual(automation1.webhook_uuid, automation2.webhook_uuid)
        self.assertNotEqual(automation1.url, automation2.url)


    def test_webhook_basic_execution(self):
        _logger.info("Testing basic webhook execution")

        automation = self.Automation.create(
            {
                "name": "Basic Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Webhook Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Webhook triggered'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload = {"event": "test"}
        automation._execute_webhook(payload)

        self.assertEqual(self.test_lead.name, "Webhook triggered")

    def test_webhook_with_payload_data(self):
        _logger.info("Testing webhook with payload data")

        automation = self.Automation.create(
            {
                "name": "Payload Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "model.browse(payload.get('lead_id'))",
            }
        )

        self.Action.create(
            {
                "name": "Payload Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Payload processed'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload = {"lead_id": self.test_lead.id, "event": "lead_update"}
        automation._execute_webhook(payload)

        self.assertEqual(self.test_lead.name, "Payload processed")

    def test_webhook_with_model_and_id_payload(self):
        _logger.info("Testing webhook with _model/_id payload")

        automation = self.Automation.create(
            {
                "name": "Standard Payload Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": (
                    "model.env[payload['_model']].browse(int(payload['_id']))"
                ),
            }
        )

        self.Action.create(
            {
                "name": "Standard Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Standard payload'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload = {"_model": "automation.lead.test", "_id": self.test_lead.id}
        automation._execute_webhook(payload)

        self.assertEqual(self.test_lead.name, "Standard payload")

    def test_webhook_multiple_executions(self):
        _logger.info("Testing webhook multiple executions")

        automation = self.Automation.create(
            {
                "name": "Multi Execution Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Counter Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": """
# Use state field to count executions
state_map = {'draft': '1', 'cancel': '2', 'open': '3'}
current = record.state if record.state in state_map else 'draft'
next_states = {'draft': 'cancel', 'cancel': 'open', 'open': 'pending'}
record.write({'state': next_states.get(current, 'cancel')})
""",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        self.test_lead.write({"state": "draft"})
        for i in range(3):
            automation._execute_webhook({"iteration": i})

        self.assertEqual(self.test_lead.state, "pending")

    def test_webhook_with_complex_record_getter(self):
        _logger.info("Testing webhook with complex record_getter")

        priority_lead = self.Lead.create({"name": "Priority Lead", "priority": True})
        regular_lead = self.Lead.create({"name": "Regular Lead", "priority": False})

        automation = self.Automation.create(
            {
                "name": "Complex Getter Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": (
                    "model.browse(payload.get('lead_id')) "
                    "if payload.get('is_priority') else model.browse([])"
                ),
            }
        )

        self.Action.create(
            {
                "name": "Complex Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Priority webhook'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload1 = {"lead_id": priority_lead.id, "is_priority": True}
        automation._execute_webhook(payload1)
        self.assertEqual(priority_lead.name, "Priority webhook")

        payload2 = {"lead_id": regular_lead.id, "is_priority": False}
        with self.assertRaises(ValidationError):
            automation._execute_webhook(payload2)


    def test_webhook_with_multiple_actions(self):
        _logger.info("Testing webhook with multiple actions")

        automation = self.Automation.create(
            {
                "name": "Multi-Action Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Action 1",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Action1'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
                "sequence": 10,
            }
        )

        self.Action.create(
            {
                "name": "Action 2",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'state': 'open'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
                "sequence": 20,
            }
        )

        automation._execute_webhook({"test": "multi_action"})

        self.assertEqual(self.test_lead.name, "Action1")
        self.assertEqual(self.test_lead.state, "open")

    def test_webhook_with_object_write_action(self):
        _logger.info("Testing webhook with object_write action")

        automation = self.Automation.create(
            {
                "name": "Object Write Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Write Action",
                "model_id": self.model_lead.id,
                "state": "object_write",
                "update_path": "name",
                "evaluation_type": "value",
                "value": "Object write from webhook",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        automation._execute_webhook({})

        self.assertEqual(self.test_lead.name, "Object write from webhook")

    def test_webhook_with_mail_action(self):
        _logger.info("Testing webhook with mail action")

        LeadThread = self.env["automation.lead.thread.test"]
        thread_lead = LeadThread.create({"name": "Mail Test Lead"})

        model_thread = self.env["ir.model"]._get("automation.lead.thread.test")

        automation = self.Automation.create(
            {
                "name": "Mail Webhook",
                "model_id": model_thread.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({thread_lead.id})",
            }
        )

        template = self.env["mail.template"].create(
            {
                "name": "Webhook Mail Template",
                "model_id": model_thread.id,
                "subject": "Webhook on {{ object.name }}",
                "body_html": "<p>Sent by a webhook</p>",
            }
        )
        self.Action.create(
            {
                "name": "Mail Action",
                "model_id": model_thread.id,
                "state": "mail_post",
                "mail_post_method": "comment",
                "template_id": template.id,
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )
        messages_before = thread_lead.message_ids

        automation._execute_webhook({"subject": "Test notification"})

        posted = thread_lead.message_ids - messages_before
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted.subject, "Webhook on Mail Test Lead")


    def test_webhook_invalid_record_getter(self):
        _logger.info("Testing webhook with invalid record_getter")

        automation = self.Automation.create(
            {
                "name": "Invalid Getter",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "invalid_python_code {",
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        with self.assertRaises(SyntaxError):
            automation._execute_webhook({})

    def test_webhook_record_getter_returns_no_record(self):
        _logger.info("Testing webhook with no record")

        automation = self.Automation.create(
            {
                "name": "No Record",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "model.browse([])",
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        with self.assertRaises(ValidationError):
            automation._execute_webhook({})

    def test_webhook_record_getter_returns_deleted_record(self):
        _logger.info("Testing webhook with deleted record")

        temp_lead = self.Lead.create({"name": "Temp Lead"})
        temp_id = temp_lead.id
        temp_lead.unlink()

        automation = self.Automation.create(
            {
                "name": "Deleted Record",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({temp_id})",
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        with self.assertRaises(ValidationError):
            automation._execute_webhook({})

    def test_webhook_action_execution_error(self):
        _logger.info("Testing webhook action error handling")

        automation = self.Automation.create(
            {
                "name": "Error Action Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Failing Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "raise Exception('Action failed!')",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        with self.assertRaises(ValueError) as context:
            automation._execute_webhook({})

        self.assertIn("Action failed!", str(context.exception))

    def test_webhook_empty_payload(self):
        _logger.info("Testing webhook with empty payload")

        automation = self.Automation.create(
            {
                "name": "Empty Payload Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Simple Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Empty payload OK'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        automation._execute_webhook({})

        self.assertEqual(self.test_lead.name, "Empty payload OK")


    def test_webhook_logging_enabled(self):
        _logger.info("Testing webhook logging")

        automation = self.Automation.create(
            {
                "name": "Logged Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
                "log_webhook_calls": True,
            }
        )

        self.Action.create(
            {
                "name": "Logged Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload = {"test": "logging"}
        admission = open_admission(
            automation, body=json_dumps_bytes(payload), path="/web/hook/x"
        )
        automation._execute_webhook(payload, admission=admission)
        self.env.cr.precommit.run()

        call = self.env["integration.exchange"].search(
            [("channel_id", "=", f"automation.rule,{automation.id}")]
        )
        self.assertEqual(len(call), 1)
        self.assertEqual(call.state, "success")
        self.assertIn("logging", call.request_payload)

    def test_webhook_logging_error(self):
        _logger.info("Testing webhook error logging")

        automation = self.Automation.create(
            {
                "name": "Error Logged Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "model.browse([])",
                "log_webhook_calls": True,
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        admission = open_admission(automation, body=b"{}", path="/web/hook/x")
        with contextlib.suppress(ValidationError):
            automation._execute_webhook({}, admission=admission)

        self.env.cr.precommit.run()

        call = self.env["integration.exchange"].search(
            [("channel_id", "=", f"automation.rule,{automation.id}")]
        )
        self.assertEqual(call.state, "failed")
        self.assertIn("No record to run the automation on", call.error_message)


    def test_webhook_on_different_model(self):
        _logger.info("Testing webhook on project model")

        project = self.Project.create({"name": "Test Project"})

        automation = self.Automation.create(
            {
                "name": "Project Webhook",
                "model_id": self.model_project.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({project.id})",
            }
        )

        self.Action.create(
            {
                "name": "Project Action",
                "model_id": self.model_project.id,
                "state": "code",
                "code": "record.write({'name': 'Webhook triggered'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        automation._execute_webhook({"project_id": project.id})

        self.assertEqual(project.name, "Webhook triggered")

    def test_webhook_search_by_field(self):
        _logger.info("Testing webhook with field search")

        self.test_lead.write({"state": "draft"})

        automation = self.Automation.create(
            {
                "name": "Field Search Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "model.search([('state', '=', payload.get('state'))], limit=1)",
            }
        )

        self.Action.create(
            {
                "name": "Field Search Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Found by field'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        payload = {"state": "draft"}
        automation._execute_webhook(payload)

        self.assertEqual(self.test_lead.name, "Found by field")


    def test_webhook_with_no_record_getter_runs_record_less(self):
        _logger.info("Testing record-less webhook")

        automation = self.Automation.create(
            {
                "name": "No Getter Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": False,
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": (
                    "env['ir.config_parameter'].sudo().set_param("
                    "'test_automation.recordless', payload.get('ping'))"
                ),
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        self.assertTrue(automation._execute_webhook({"ping": "pong"}))
        self.assertEqual(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "test_automation.recordless",
            ),
            "pong",
            "the record-less path must still expose the payload to the action",
        )

    def test_webhook_with_record_getter_that_finds_nothing(self):
        automation = self.Automation.create(
            {
                "name": "Getter Finds Nothing",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": "model.browse(0)",
            }
        )
        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "pass",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )
        with self.assertRaises(ValidationError):
            automation._execute_webhook({})

    def test_webhook_inactive_automation(self):
        _logger.info("Testing inactive webhook automation")

        automation = self.Automation.create(
            {
                "name": "Inactive Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
                "active": False,
            }
        )

        self.Action.create(
            {
                "name": "Test Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': 'Inactive executed'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        automation._execute_webhook({})

        self.assertEqual(self.test_lead.name, "Inactive executed")

    def test_webhook_with_large_payload(self):
        _logger.info("Testing webhook with large payload")

        automation = self.Automation.create(
            {
                "name": "Large Payload Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Payload Size Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": "record.write({'name': f'Payload size: {len(str(payload))}'})",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        large_payload = {f"item_{i}": f"value_{i}" for i in range(1000)}

        automation._execute_webhook(large_payload)

        self.assertTrue(self.test_lead.name)
        self.assertIn("Payload size:", self.test_lead.name)

    def test_webhook_payload_access_in_action(self):
        _logger.info("Testing payload access in action")

        automation = self.Automation.create(
            {
                "name": "Payload Access Webhook",
                "model_id": self.model_lead.id,
                "trigger": "on_webhook",
                "record_getter": f"model.browse({self.test_lead.id})",
            }
        )

        self.Action.create(
            {
                "name": "Payload Action",
                "model_id": self.model_lead.id,
                "state": "code",
                "code": """
event_type = payload.get('event_type', 'unknown')
record.write({'name': f'Event: {event_type}'})
""",
                "automation_rule_id": automation.id,
                "usage": "automation",
            }
        )

        automation._execute_webhook({"event_type": "lead.created"})

        self.assertEqual(self.test_lead.name, "Event: lead.created")
