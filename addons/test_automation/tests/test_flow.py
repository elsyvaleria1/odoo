import datetime
import sys
from unittest.mock import patch

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import Form, WhitespaceInsensitive, common, tagged
from odoo.tools import mute_logger

from odoo.addons.base.tests.common import TransactionCaseWithUserDemo


def create_automation(self, **kwargs):
    vals = {"name": "Automation"}
    vals.update(kwargs)
    actions_data = vals.pop("_actions", [])
    if not isinstance(actions_data, list):
        actions_data = [actions_data]
    automation_id = self.env["automation.rule"].create(vals)
    action_ids = self.env["ir.actions.server"].create(
        [
            {
                "name": "Action",
                "automation_rule_id": automation_id.id,
                "model_id": automation_id.model_id.id,
                "usage": "automation",
                **action,
            }
            for action in actions_data
        ]
    )
    action_ids.flush_recordset()
    automation_id.write({"action_server_ids": [Command.set(action_ids.ids)]})
    self.addCleanup(automation_id.unlink)
    return automation_id


@tagged("post_install", "-at_install")
class AutomationRuleTest(TransactionCaseWithUserDemo):
    def setUp(self):
        super().setUp()
        self.user_root = self.env.ref("base.user_root")
        self.user_admin = self.env.ref("base.user_admin")
        self.lead_model = self.env.ref("test_automation.model_automation_lead_test")
        self.project_model = self.env.ref(
            "test_automation.model_test_automation_project"
        )
        self.test_mail_template_automation = self.env["mail.template"].create(
            {
                "name": "Template Automation",
                "model_id": self.env["ir.model"]._get_id("automation.lead.thread.test"),
                "body_html": """&lt;div&gt;Email automation&lt;/div&gt;""",
            }
        )
        self.res_partner_1 = self.env["res.partner"].create({"name": "My Partner"})

    def create_lead(self, **kwargs):
        vals = {
            "name": "Lead Test",
            "user_id": self.user_root.id,
        }
        vals.update(kwargs)
        lead = self.env["automation.lead.test"].create(vals)
        self.addCleanup(lead.unlink)
        return lead

    def create_line(self, **kwargs):
        vals = {
            "name": "Line Test",
            "user_id": self.user_root.id,
        }
        vals.update(kwargs)
        line = self.env["automation.line.test"].create(vals)
        self.addCleanup(line.unlink)
        return line

    def create_project(self, **kwargs):
        vals = {"name": "Project Test"}
        vals.update(kwargs)
        project = self.env["test_automation.project"].create(vals)
        self.addCleanup(project.unlink)
        return project

    def create_stage(self, **kwargs):
        vals = {"name": "Stage Test"}
        vals.update(kwargs)
        stage = self.env["test_automation.stage"].create(vals)
        self.addCleanup(stage.unlink)
        return stage

    def create_tag(self, **kwargs):
        vals = {"name": "Tag Test"}
        vals.update(kwargs)
        tag = self.env["test_automation.tag"].create(vals)
        self.addCleanup(tag.unlink)
        return tag

    def test_000_on_create_or_write(self):
        lead = self.create_lead()
        self.assertEqual(lead.state, "draft")
        self.assertEqual(lead.user_id, self.user_root)

        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        lead.write({"state": "open"})
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.user_id, self.user_demo)

        lead2 = self.create_lead()
        self.assertEqual(lead2.state, "draft")
        self.assertEqual(lead2.user_id, self.user_demo)

    def test_001_on_create_or_write(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            filter_domain="[('state', '=', 'draft')]",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        lead = self.create_lead(state="open")
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.user_id, self.user_root)

        lead.write({"state": "draft"})
        self.assertEqual(lead.state, "draft")
        self.assertEqual(lead.user_id, self.user_demo)

        lead_2 = self.create_lead()
        self.assertEqual(lead_2.state, "draft")
        self.assertEqual(lead_2.user_id, self.user_demo)

    def test_002_on_create_or_write(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            filter_pre_domain="[('state', '=', 'open')]",
            filter_domain="[('state', '=', 'done')]",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        lead = self.create_lead(state="open")
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.user_id, self.user_root)

        lead.write({"state": "pending"})
        self.assertEqual(lead.state, "pending")
        self.assertEqual(lead.user_id, self.user_root)
        lead.write({"state": "done"})
        self.assertEqual(lead.state, "done")
        self.assertEqual(lead.user_id, self.user_root)

        lead.write({"state": "open"})
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.user_id, self.user_root)
        lead.write({"state": "done"})
        self.assertEqual(lead.state, "done")
        self.assertEqual(lead.user_id, self.user_demo)

        lead_2 = self.create_lead(state="open")
        self.assertEqual(lead_2.state, "open")
        self.assertEqual(lead_2.user_id, self.user_root)
        lead_2.write({"state": "done"})
        self.assertEqual(lead_2.state, "done")
        self.assertEqual(lead_2.user_id, self.user_demo)

        lead_3 = self.create_lead(state="done")
        self.assertEqual(lead_3.state, "done")
        self.assertEqual(lead_3.user_id, self.user_demo)

    def test_003_on_create_or_write(self):
        lead_state_field = self.env.ref(
            "test_automation.field_automation_lead_test__state"
        )
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            trigger_field_ids=[Command.link(lead_state_field.id)],
            _actions={
                "state": "code",
                "code": """
if env.context.get('old_values', None): # on write only
    record = model.browse(env.context['active_id'])
    record['name'] = record.name + 'X'""",
            },
        )

        lead = self.create_lead(name="X")
        lead.priority = True
        partner1 = self.res_partner_1
        lead.partner_id = partner1
        self.assertEqual(lead.name, "X", "No update until now.")

        lead.state = "open"
        self.assertEqual(lead.name, "XX", "One update should have happened.")
        lead.state = "done"
        self.assertEqual(lead.name, "XXX", "One update should have happened.")
        lead.state = "done"
        self.assertEqual(lead.name, "XXX", "No update should have happened.")
        lead.state = "cancel"
        self.assertEqual(lead.name, "XXXX", "One update should have happened.")

        lead_partner_id_field = self.env.ref(
            "test_automation.field_automation_lead_test__partner_id"
        )
        automation.write(
            {"trigger_field_ids": [Command.set([lead_partner_id_field.id])]}
        )

        partner2 = self.env["res.partner"].create({"name": "A new partner"})
        lead.name = "X"
        lead.state = "open"
        self.assertEqual(lead.name, "X", "No update should have happened.")
        lead.partner_id = partner2
        self.assertEqual(lead.name, "XX", "One update should have happened.")
        lead.partner_id = partner2
        self.assertEqual(lead.name, "XX", "No update should have happened.")
        lead.partner_id = partner1
        self.assertEqual(lead.name, "XXX", "One update should have happened.")
        lead.partner_id = partner1
        self.assertEqual(lead.name, "XXX", "No update should have happened.")

    def test_010_recompute(self):
        partner = self.res_partner_1
        partner.write({"test_automation_employee": False})

        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            filter_domain="[('employee', '=', True)]",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        lead = self.create_lead(partner_id=partner.id)
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(lead.employee, False)
        self.assertEqual(lead.user_id, self.user_root)

        partner.write({"test_automation_employee": True})
        self.env.flush_all()
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(lead.employee, True)
        self.assertEqual(lead.user_id, self.user_demo)

    def test_011_recompute(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "code",
                "code": """
if env.context.get('old_values', None):  # on write
    if 'user_id' in env.context['old_values'][record.id]:
        record.write({'is_assigned_to_admin': (record.user_id.id == 1)})""",
            },
        )

        partner = self.res_partner_1
        lead = self.create_lead(state="draft", partner_id=partner.id)
        self.assertEqual(lead.deadline, False)
        self.assertEqual(lead.is_assigned_to_admin, False)

        lead.write({"priority": True, "user_id": self.user_root.id})
        self.assertNotEqual(lead.deadline, False)
        self.assertEqual(lead.is_assigned_to_admin, True)

    def test_012_recompute(self):
        active_field = self.env.ref(
            "test_automation.field_automation_lead_test__active"
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            trigger_field_ids=[Command.link(active_field.id)],
            _actions={
                "state": "code",
                "code": """
if not env.context.get('old_values', None):  # on create
    record.write({'state': 'open'})
else:
    record.write({'priority': not record.priority})""",
            },
        )

        lead = self.create_lead(state="draft", priority=False)
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.priority, False)

        lead.write({"state": "pending"})
        self.assertEqual(lead.state, "pending")
        self.assertEqual(lead.priority, False)

        lead.write({"active": False})
        self.assertEqual(lead.state, "pending")
        self.assertEqual(lead.priority, True)

        lead.write({"active": True})
        self.assertEqual(lead.state, "pending")
        self.assertEqual(lead.priority, False)

    def test_013_recompute(self):
        deadline_field = self.env.ref(
            "test_automation.field_automation_lead_test__deadline"
        )
        create_automation(
            self,
            model_id=self.env["ir.model"]._get_id("automation.lead.thread.test"),
            trigger="on_create_or_write",
            trigger_field_ids=[Command.link(deadline_field.id)],
            filter_pre_domain="[('deadline', '=', False)]",
            filter_domain="[('deadline', '!=', False)]",
            _actions={
                "state": "mail_post",
                "mail_post_method": "email",
                "template_id": self.test_mail_template_automation.id,
            },
        )

        Mail = self.env["mail.mail"].sudo()
        mails_before = Mail.search_count([])

        lead = self.env["automation.lead.thread.test"].create(
            {
                "name": "Lead Test",
                "user_id": self.user_root.id,
            }
        )
        self.addCleanup(lead.unlink)
        self.assertEqual(lead.priority, False)
        self.assertEqual(lead.deadline, False)
        self.assertEqual(Mail.search_count([]) - mails_before, 0)

        lead.write({"priority": True})
        self.assertEqual(lead.priority, True)
        self.assertNotEqual(lead.deadline, False)
        self.assertEqual(Mail.search_count([]) - mails_before, 1)

    def test_020_recursive(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "code",
                "code": """
if env.context.get('old_values', None):  # on write
    if 'partner_id' in env.context['old_values'][record.id]:
        record.write({'state': 'draft'})""",
            },
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            filter_domain="[('state', '=', 'draft')]",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        lead = self.create_lead(state="open")
        self.assertEqual(lead.state, "open")
        self.assertEqual(lead.user_id, self.user_root)

        partner = self.res_partner_1
        lead.write({"partner_id": partner.id})
        self.assertEqual(lead.state, "draft")
        self.assertEqual(lead.user_id, self.user_demo)

    def test_021_recursive(self):
        automations = [
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger="on_create_or_write",
                filter_domain="[('state', '=', 'draft')]",
                _actions={
                    "state": "code",
                    "code": "record.write({'state': 'pending'})",
                },
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger="on_create_or_write",
                filter_domain="[('state', '=', 'pending')]",
                _actions={"state": "code", "code": "record.write({'state': 'open'})"},
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger="on_create_or_write",
                filter_domain="[('state', '=', 'open')]",
                _actions={"state": "code", "code": "record.write({'state': 'done'})"},
            ),
            create_automation(
                self,
                model_id=self.lead_model.id,
                trigger="on_create_or_write",
                filter_domain="[('state', '=', 'done')]",
                _actions={"state": "code", "code": "record.write({'state': 'draft'})"},
            ),
        ]

        def _patch(*args, **kwargs):
            self.assertEqual(args[0], automations.pop(0))

        patcher = patch(
            "odoo.addons.automation.models.automation_rule.AutomationRule._process",
            _patch,
        )
        self.startPatcher(patcher)

        lead = self.create_lead(state="draft")
        self.assertEqual(lead.state, "draft")
        self.assertEqual(len(automations), 0)

    def test_030_submodel(self):
        line = self.create_line()
        self.assertEqual(line.user_id, self.user_root)

        lead = self.create_lead(
            line_ids=[(0, 0, {"name": "Line", "user_id": self.user_root.id})]
        )
        self.assertEqual(lead.user_id, self.user_root)
        self.assertEqual(lead.line_ids.user_id, self.user_root)

        comodel = self.env.ref("test_automation.model_automation_line_test")
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )
        create_automation(
            self,
            model_id=comodel.id,
            trigger="on_create_or_write",
            _actions={
                "state": "code",
                "code": "record.write({'user_id': %s})" % (self.user_demo.id),
            },
        )

        line = self.create_line(user_id=self.user_root.id)
        self.assertEqual(line.user_id, self.user_demo)

        lead = self.create_lead(
            line_ids=[(0, 0, {"name": "Line", "user_id": self.user_root.id})]
        )
        self.assertEqual(lead.user_id, self.user_demo)
        self.assertEqual(lead.line_ids.user_id, self.user_demo)

    def test_040_modelwithoutaccess(self):
        Model = self.env["automation.link.test"]
        model_id = self.env.ref("test_automation.model_automation_link_test")
        Comodel = self.env["automation.linked.test"]
        comodel_access = self.env.ref("test_automation.access_automation_linked_test")
        comodel_access.group_id = self.env["res.groups"].create(
            {
                "name": "Access to automation.linked.test",
                "user_ids": [Command.link(self.user_admin.id)],
            }
        )

        with self.assertRaises(AccessError):
            Comodel.with_user(self.user_demo).check_access("read")

        create_automation(
            self,
            model_id=model_id.id,
            trigger="on_create_or_write",
            filter_pre_domain="[('linked_id.another_field', '=', 'something')]",
            _actions={
                "state": "code",
                "code": "action = [rec.name for rec in records]",
            },
        )
        Comodel.create(
            [
                {"name": "a first record", "another_field": "something"},
                {"name": "another record", "another_field": "something different"},
            ]
        )
        rec1 = Model.create({"name": "a record"})
        rec1.write({"name": "a first record"})
        rec2 = Model.with_user(self.user_demo).create({"name": "another record"})
        rec2.write({"name": "another value"})

        create_automation(
            self,
            model_id=model_id.id,
            trigger="on_create_or_write",
            filter_pre_domain="[('linked_id', '=', 'whatever')]",
            _actions={
                "state": "code",
                "code": "action = [rec.name for rec in records]",
            },
        )
        rec3 = Model.create({"name": "a random record"})
        rec3.write({"name": "a first record"})
        rec4 = Model.with_user(self.user_demo).create({"name": "again another record"})
        rec4.write({"name": "another value"})

    def test_050_on_create_or_write_with_create_record(self):
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "object_create",
                "crud_model_id": self.project_model.id,
                "value": "foo",
            },
        )
        lead = self.create_lead()
        search_result = self.env["test_automation.project"].name_search("foo")
        self.assertEqual(
            len(search_result),
            1,
            "One record on the project model should have been created",
        )

        lead.write({"name": "renamed lead"})
        search_result = self.env["test_automation.project"].name_search("foo")
        self.assertEqual(
            len(search_result),
            2,
            "Another record on the project model should have been created",
        )

    def test_060_on_stage_set(self):
        stage_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.project_model.id),
                ("name", "=", "stage_id"),
            ]
        )
        stage1 = self.create_stage()
        stage2 = self.create_stage()
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_stage_set",
            trigger_field_ids=[stage_field.id],
            filter_domain="[('stage_id', '=', %s)]" % stage1.id,
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )
        project = self.create_project()
        self.assertEqual(project.name, "Project Test")
        project.write({"stage_id": stage1.id})
        self.assertEqual(project.name, "Project Test!")
        project.write({"stage_id": stage1.id})
        self.assertEqual(project.name, "Project Test!")
        project.write({"stage_id": stage2.id})
        self.assertEqual(project.name, "Project Test!")
        project.write({"stage_id": False})
        self.assertEqual(project.name, "Project Test!")
        project.write({"stage_id": stage1.id})
        self.assertEqual(project.name, "Project Test!!")

    def test_070_on_user_set(self):
        user_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.lead_model.id),
                ("name", "=", "user_id"),
            ]
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_user_set",
            trigger_field_ids=[user_field.id],
            filter_domain="[('user_id', '!=', False)]",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )

        lead = self.create_lead()
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"user_id": self.user_demo.id})
        self.assertEqual(lead.name, "Lead Test!!")
        lead.write({"user_id": self.user_demo.id})
        self.assertEqual(lead.name, "Lead Test!!")
        lead.write({"user_id": self.user_admin.id})
        self.assertEqual(lead.name, "Lead Test!!!")
        lead.write({"user_id": False})
        self.assertEqual(lead.name, "Lead Test!!!")
        lead.write({"user_id": self.user_demo.id})
        self.assertEqual(lead.name, "Lead Test!!!!")

    def test_071_on_user_set(self):
        user_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.project_model.id),
                ("name", "=", "user_ids"),
            ]
        )
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_user_set",
            trigger_field_ids=[user_field.id],
            filter_domain="[('user_ids', '!=', False)]",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )

        project = self.create_project()
        self.assertEqual(project.name, "Project Test")
        project.write({"user_ids": [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"user_ids": [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"user_ids": [Command.link(self.user_admin.id)]})
        self.assertEqual(project.name, "Project Test!!")
        project.write({"user_ids": [Command.unlink(self.user_admin.id)]})
        self.assertEqual(project.name, "Project Test!!!")
        project.write({"user_ids": [Command.set([])]})
        self.assertEqual(project.name, "Project Test!!!")
        project.write({"user_ids": [Command.set([self.user_demo.id])]})
        self.assertEqual(project.name, "Project Test!!!!")

    def test_080_on_tag_set(self):
        tag_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.project_model.id),
                ("name", "=", "tag_ids"),
            ]
        )
        tag1 = self.create_tag()
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_tag_set",
            trigger_field_ids=[tag_field.id],
            filter_pre_domain="[('tag_ids', 'not in', [%s])]" % tag1.id,
            filter_domain="[('tag_ids', 'in', [%s])]" % tag1.id,
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )
        project = self.create_project()
        self.assertEqual(project.name, "Project Test")
        project.write({"tag_ids": [Command.set([tag1.id])]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"tag_ids": [Command.set([tag1.id])]})
        self.assertEqual(project.name, "Project Test!")

        tag2 = self.create_tag()
        project.write({"tag_ids": [Command.link(tag2.id)]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"tag_ids": [Command.clear()]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"tag_ids": [Command.set([tag2.id])]})
        self.assertEqual(project.name, "Project Test!")
        project.write({"tag_ids": [Command.link(tag1.id)]})
        self.assertEqual(project.name, "Project Test!!")

    def test_090_on_state_set(self):
        state_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.lead_model.id),
                ("name", "=", "state"),
            ]
        )

        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_state_set",
            trigger_field_ids=[state_field.id],
            filter_domain="[('state', '=', 'done')]",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )

        lead = self.create_lead()
        self.assertEqual(lead.name, "Lead Test")
        lead.write({"state": "open"})
        self.assertEqual(lead.name, "Lead Test")
        lead.write({"state": "done"})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"state": "done"})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"state": "open"})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"state": "done"})
        self.assertEqual(lead.name, "Lead Test!!")

    def test_100_on_priority_set(self):
        priority_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.project_model.id),
                ("name", "=", "priority"),
            ]
        )
        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_priority_set",
            trigger_field_ids=[priority_field.id],
            filter_domain="[('priority', '=', '2')]",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )
        project = self.create_project()
        self.assertEqual(project.name, "Project Test")
        self.assertEqual(project.priority, "1")
        project.write({"priority": "0"})
        self.assertEqual(project.name, "Project Test")
        project.write({"priority": "2"})
        self.assertEqual(project.name, "Project Test!")
        project.write({"priority": "2"})
        self.assertEqual(project.name, "Project Test!")
        project.write({"priority": "0"})
        self.assertEqual(project.name, "Project Test!")
        project.write({"priority": "2"})
        self.assertEqual(project.name, "Project Test!!")

    def test_110_on_archive(self):
        active_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.lead_model.id),
                ("name", "=", "active"),
            ]
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_archive",
            trigger_field_ids=[active_field.id],
            filter_domain="[('active', '=', False)]",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )
        lead = self.create_lead()
        self.assertEqual(lead.name, "Lead Test")
        lead.write({"active": False})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"active": True})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"active": False})
        self.assertEqual(lead.name, "Lead Test!!")
        lead.write({"active": False})
        self.assertEqual(lead.name, "Lead Test!!")

    def test_110_on_unarchive(self):
        active_field = self.env["ir.model.fields"].search(
            [
                ("model_id", "=", self.lead_model.id),
                ("name", "=", "active"),
            ]
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_unarchive",
            trigger_field_ids=[active_field.id],
            filter_domain="[('active', '=', True)]",
            _actions={
                "state": "object_write",
                "evaluation_type": "equation",
                "update_path": "name",
                "value": "record.name + '!'",
            },
        )
        lead = self.create_lead()
        self.assertEqual(lead.name, "Lead Test")
        lead.write({"active": False})
        self.assertEqual(lead.name, "Lead Test")
        lead.write({"active": True})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"active": False})
        self.assertEqual(lead.name, "Lead Test!")
        lead.write({"active": True})
        self.assertEqual(lead.name, "Lead Test!!")
        lead.write({"active": True})
        self.assertEqual(lead.name, "Lead Test!!")

    def test_120_on_change(self):
        Model = self.env.get(self.lead_model.model)
        lead_name_field = self.env["ir.model.fields"]._get(
            self.lead_model.model, "name"
        )
        self.assertEqual(lead_name_field.name in Model._onchange_methods, False)
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_change",
            filter_domain="[('name', 'like', 'IMPORTANT')]",
            on_change_field_ids=[lead_name_field.id],
            _actions={
                "state": "code",
                "code": """
action = {
    'value': {
        'priority': '[IMPORTANT]' in record.name,
    }
}
            """,
            },
        )
        self.assertEqual(lead_name_field.name in Model._onchange_methods, True)

        with Form(self.env[self.lead_model.model]) as f:
            self.assertEqual(f.priority, False)
            f.name = "Lead Test"
            self.assertEqual(f.priority, False)

            f.name = "Lead Test [IMPORTANT]"
            self.assertEqual(f.priority, True)

            f.name = "Lead Test"
            self.assertEqual(f.priority, True)

            f.name = "Lead Test [NOT IMPORTANT]"
            self.assertEqual(f.priority, False)

            f.name = "Lead Test [IMPORTANT]"
            self.assertEqual(f.priority, True)

    def test_121_on_change_with_domain_field_not_in_view(self):
        lead_name_field = self.env["ir.model.fields"]._get(
            self.lead_model.model, "name"
        )
        create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_change",
            filter_domain="[('active', '!=', False)]",
            on_change_field_ids=[lead_name_field.id],
            _actions={
                "state": "code",
                "code": """
action = {
    'value': {
        'priority': '[IMPORTANT]' in record.name,
    }
}
            """,
            },
        )
        my_view = self.env["ir.ui.view"].create(
            {
                "name": "My View",
                "model": self.lead_model.model,
                "type": "form",
                "arch": """
                <form>
                    <field name='name'/>
                    <field name='priority'/>
                </form>
            """,
            }
        )
        record = self.env[self.lead_model.model].create(
            {
                "name": "Test Lead",
                "active": False,
                "priority": False,
            }
        )
        self.assertEqual(record.priority, False)
        with Form(record, view=my_view) as f:
            f.name = "[IMPORTANT] Lead"
        self.assertEqual(record.priority, False)

        record.name = "Test Lead"
        record.active = True
        self.assertEqual(record.priority, False)
        with Form(record, view=my_view) as f:
            f.name = "[IMPORTANT] Lead"
        self.assertEqual(record.priority, True)

    def test_130_on_unlink(self):
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_unlink",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )

        called_count = 0

        def _patch(*args, **kwargs):
            nonlocal called_count
            called_count += 1
            self.assertEqual(args[0], automation)

        patcher = patch(
            "odoo.addons.automation.models.automation_rule.AutomationRule._process",
            _patch,
        )
        self.startPatcher(patcher)

        lead = self.create_lead()
        self.assertEqual(called_count, 0)
        lead.unlink()
        self.assertEqual(called_count, 1)

    @property
    def automation_cron(self):
        return self.env.ref("automation.ir_cron_data_automation_check")

    def test_004_check_method_trigger_field(self):
        model = self.env["ir.model"]._get("automation.lead.test")
        TIME_TRIGGERS = [
            "on_time",
            "on_time_created",
            "on_time_updated",
        ]
        self.env["automation.rule"].search(
            [("trigger", "in", TIME_TRIGGERS)]
        ).active = False

        automation = self.env["automation.rule"].create(
            {
                "name": "Cron BaseAuto",
                "trigger": "on_time",
                "model_id": model.id,
            }
        )

        self.assertFalse(automation.last_run)
        with (
            self.assertLogs("odoo.addons.automation", "WARNING") as capture,
            self.sync_env_with_side_cursors(),
        ):
            self.automation_cron.method_direct_trigger()
        self.assertRegex(capture.output[0], r"Missing date trigger")
        automation.trg_date_id = model.field_id.filtered(
            lambda f: f.name == "date_automation_last"
        )

        with self.sync_env_with_side_cursors():
            self.automation_cron.method_direct_trigger()
        self.assertTrue(automation.last_run)

    @common.freeze_time("2020-01-01 03:00:00")
    def test_004_check_method_process(self):
        model = self.env["ir.model"]._get("automation.lead.test")
        TIME_TRIGGERS = [
            "on_time",
            "on_time_created",
            "on_time_updated",
        ]
        self.env["automation.rule"].search(
            [("trigger", "in", TIME_TRIGGERS)]
        ).active = False

        automation = self.env["automation.rule"].create(
            {
                "name": "Cron BaseAuto",
                "trigger": "on_time",
                "model_id": model.id,
                "trg_date_id": model.field_id.filtered(
                    lambda f: f.name == "date_automation_last"
                ).id,
                "trg_date_range": 2,
                "trg_date_range_type": "minute",
                "trg_date_range_mode": "after",
            }
        )

        with (
            patch.object(
                automation.__class__, "_process", side_effect=automation._process
            ) as mock,
            self.sync_env_with_side_cursors(),
        ):
            with patch.object(self.env.cr, "_now", now := datetime.datetime.now()):
                past_date = now - datetime.timedelta(1)
                self.env["automation.lead.test"].create(
                    [
                        {
                            "name": f"lead {i}",
                            "date_automation_last": False
                            if i < 2
                            else past_date
                            if i < 10
                            else now + datetime.timedelta(minutes=i),
                        }
                        for i in range(15)
                    ]
                )
            with (
                common.freeze_time("2020-01-01 03:02:01"),
                patch.object(self.env.cr, "_now", datetime.datetime.now()),
            ):
                self.automation_cron.method_direct_trigger()
                self.assertEqual(mock.call_count, 10)
                automation.invalidate_recordset(["last_run"])
                self.assertEqual(automation.last_run, self.env.cr.now())
            with (
                common.freeze_time("2020-01-01 03:13:59"),
                patch.object(self.env.cr, "_now", datetime.datetime.now()),
            ):
                self.automation_cron.method_direct_trigger()
                self.assertEqual(mock.call_count, 22)
                automation.invalidate_recordset(["last_run"])
                self.assertEqual(automation.last_run, self.env.cr.now())
                automation.trg_date_calendar_id = (
                    self.env["resource.calendar"].search([], limit=1).check_singleton()
                )
                automation.trg_date_range_type = "day"
                self.env["automation.lead.test"].create({"name": "calendar"})
            with (
                common.freeze_time("2020-02-02 03:11:00"),
                patch.object(self.env.cr, "_now", datetime.datetime.now()),
            ):
                self.automation_cron.method_direct_trigger()
                self.assertEqual(mock.call_count, 38)

    def test_005_check_model_with_different_rec_name_char(self):
        model = self.env["ir.model"]._get("automation.model.with.recname.char")

        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "object_create",
                "crud_model_id": model.id,
                "value": "Test _rec_name Automation",
            },
        )

        self.create_project()
        record_count = self.env[model.model].search_count(
            [("description", "=", "Test _rec_name Automation")]
        )
        self.assertEqual(record_count, 1, "Only one record should have been created")

    def test_006_check_model_with_different_m2o_name_create(self):
        model = self.env["ir.model"]._get("automation.model.with.recname.m2o")

        create_automation(
            self,
            model_id=self.project_model.id,
            trigger="on_create_or_write",
            _actions={
                "state": "object_create",
                "crud_model_id": model.id,
                "value": "Test _rec_name Automation",
            },
        )

        self.create_project()
        record_count = self.env[model.model].search_count(
            [("user_id", "=", "Test _rec_name Automation")]
        )
        self.assertEqual(record_count, 1, "Only one record should have been created")

    def test_140_copy_should_copy_actions(self):
        automation = create_automation(
            self,
            model_id=self.lead_model.id,
            trigger="on_change",
            _actions={
                "state": "code",
                "code": "record.write({'name': record.name + '!'})",
            },
        )
        action_ids = automation.action_server_ids

        copy_automation = automation.copy()
        copy_action_ids = copy_automation.action_server_ids
        self.assertEqual(len(action_ids), 1)
        self.assertEqual(len(copy_action_ids), len(action_ids))
        self.assertNotEqual(copy_action_ids, action_ids)

    def test_add_followers_1(self):
        create_automation(
            self,
            model_id=self.env["ir.model"]._get("automation.lead.thread.test").id,
            trigger="on_create",
            _actions={
                "state": "followers",
                "followers_type": "generic",
                "followers_partner_field_name": "user_id.partner_id",
            },
        )
        user = self.env["res.users"].create(
            {"login": "maggot_brain", "name": "Eddie Hazel"}
        )
        thread_test = self.env["automation.lead.thread.test"].create(
            {
                "name": "free your mind",
                "user_id": user.id,
            }
        )
        self.assertEqual(thread_test.message_follower_ids.partner_id, user.partner_id)

    def test_add_followers_2(self):
        user = self.env["res.users"].create(
            {"login": "maggot_brain", "name": "Eddie Hazel"}
        )
        create_automation(
            self,
            model_id=self.env["ir.model"]._get("automation.lead.thread.test").id,
            trigger="on_create",
            _actions={
                "state": "followers",
                "followers_type": "specific",
                "partner_ids": [Command.link(user.partner_id.id)],
            },
        )
        thread_test = self.env["automation.lead.thread.test"].create(
            {
                "name": "free your mind",
            }
        )
        self.assertEqual(thread_test.message_follower_ids.partner_id, user.partner_id)

    def test_cannot_have_actions_with_warnings(self):
        with self.assertRaises(ValidationError) as e:
            create_automation(
                self,
                model_id=self.env["ir.model"]._get("ir.actions.server").id,
                trigger="on_time",
                _actions={
                    "name": "Send Webhook Notification",
                    "state": "webhook",
                    "webhook_field_ids": [
                        self.env["ir.model.fields"]._get("ir.actions.server", "code").id
                    ],
                },
            )
        self.assertIn("Send Webhook Notification", e.exception.args[0])


@common.tagged("post_install", "-at_install")
class TestCompute(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.user_admin").write(
            {
                "email": "mitchell.admin@example.com",
            }
        )

    def test_automation_form_view(self):
        automation_form = Form(
            self.env["automation.rule"],
            view="automation.view_automation_form",
        )

        automation_form.name = "Test Automation"
        automation_form.model_id = self.env.ref(
            "test_automation.model_test_automation_project"
        )
        automation_form.trigger = "on_create_or_write"
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        self.assertEqual(automation_form.filter_domain, False)
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.model_id = self.env.ref(
            "test_automation.model_automation_lead_test"
        )
        self.assertEqual(automation_form.trigger, False)
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        self.assertEqual(automation_form.filter_domain, False)

        automation_form.trigger = "on_state_set"
        state_field_id = self.env.ref(
            "test_automation.field_automation_lead_test__state"
        ).id
        self.assertEqual(automation_form.trigger_field_ids.ids, [state_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        automation_form.trg_selection_field_id = self.env[
            "ir.model.fields.selection"
        ].search(
            [
                ("field_id", "=", state_field_id),
                ("value", "=", "pending"),
            ]
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [state_field_id])
        self.assertEqual(
            automation_form.filter_domain, repr([("state", "=", "pending")])
        )
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.model_id = self.env.ref(
            "test_automation.model_test_automation_project"
        )
        automation_form.trigger = "on_priority_set"
        priority_field_id = self.env.ref(
            "test_automation.field_test_automation_project__priority"
        ).id
        self.assertEqual(automation_form.trigger_field_ids.ids, [priority_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        automation_form.trg_selection_field_id = self.env[
            "ir.model.fields.selection"
        ].search(
            [
                ("field_id", "=", priority_field_id),
                ("value", "=", "2"),
            ]
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [priority_field_id])
        self.assertEqual(automation_form.filter_domain, repr([("priority", "=", "2")]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.model_id = self.env.ref(
            "test_automation.model_automation_lead_test"
        )
        automation_form.trigger = "on_stage_set"
        stage_field_id = self.env.ref(
            "test_automation.field_automation_lead_test__stage_id"
        ).id
        self.assertEqual(automation_form.trigger_field_ids.ids, [stage_field_id])
        self.assertEqual(automation_form.filter_domain, False)
        new_lead_stage = self.env["test_automation.stage"].create({"name": "New"})
        automation_form.trg_field_ref = new_lead_stage.id
        self.assertEqual(
            automation_form.filter_domain, repr([("stage_id", "=", new_lead_stage.id)])
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [stage_field_id])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.trigger = "on_user_set"
        self.assertEqual(
            automation_form.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__user_id").id],
        )
        self.assertEqual(
            automation_form.filter_domain, repr([("user_id", "!=", False)])
        )
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.trigger = "on_archive"
        self.assertEqual(
            automation_form.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__active").id],
        )
        self.assertEqual(automation_form.filter_domain, repr([("active", "=", False)]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.trigger = "on_unarchive"
        self.assertEqual(
            automation_form.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__active").id],
        )
        self.assertEqual(automation_form.filter_domain, repr([("active", "=", True)]))
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation_form.trigger = "on_tag_set"
        a_lead_tag = self.env["test_automation.tag"].create({"name": "*AWESOME*"})
        automation_form.trg_field_ref = a_lead_tag.id
        self.assertEqual(
            automation_form.filter_domain, repr([("tag_ids", "in", [a_lead_tag.id])])
        )
        self.assertEqual(
            automation_form.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__tag_ids").id],
        )
        automation = automation_form.save()
        self.assertEqual(
            automation.filter_pre_domain, repr([("tag_ids", "not in", [a_lead_tag.id])])
        )

    def test_automation_form_view_on_change_filter_domain(self):
        a_lead_tag = self.env["test_automation.tag"].create({"name": "*AWESOME*"})
        automation = self.env["automation.rule"].create(
            {
                "name": "Test Automation",
                "model_id": self.env.ref(
                    "test_automation.model_automation_lead_test"
                ).id,
                "trigger": "on_tag_set",
                "trg_field_ref": a_lead_tag.id,
            }
        )
        self.assertEqual(
            automation.filter_pre_domain, repr([("tag_ids", "not in", [a_lead_tag.id])])
        )
        self.assertEqual(
            automation.filter_domain, repr([("tag_ids", "in", [a_lead_tag.id])])
        )
        self.assertEqual(
            automation.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__tag_ids").id],
        )
        self.assertEqual(automation.on_change_field_ids.ids, [])

        automation_form = Form(automation, view="automation.view_automation_form")
        automation_form.trigger = "on_create_or_write"
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, False)
        self.assertEqual(automation.trigger_field_ids.ids, [])
        self.assertEqual(automation.on_change_field_ids.ids, [])

        automation_form.filter_domain = repr(
            [("priority", "=", True), ("employee", "=", False)]
        )
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(
            automation.filter_domain,
            repr([("priority", "=", True), ("employee", "=", False)]),
        )
        self.assertSetEqual(
            set(automation.trigger_field_ids.ids),
            {
                self.env.ref("test_automation.field_automation_lead_test__priority").id,
                self.env.ref("test_automation.field_automation_lead_test__employee").id,
            },
        )
        self.assertEqual(automation.on_change_field_ids.ids, [])

        automation_form.trigger_field_ids.add(
            self.env.ref("test_automation.field_automation_lead_test__tag_ids")
        )
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(
            automation.filter_domain,
            repr([("priority", "=", True), ("employee", "=", False)]),
        )
        self.assertItemsEqual(
            automation.trigger_field_ids.ids,
            [
                self.env.ref("test_automation.field_automation_lead_test__priority").id,
                self.env.ref("test_automation.field_automation_lead_test__employee").id,
                self.env.ref("test_automation.field_automation_lead_test__tag_ids").id,
            ],
        )
        self.assertEqual(automation.on_change_field_ids.ids, [])

        automation_form.filter_domain = False
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, False)
        self.assertEqual(
            automation.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__tag_ids").id],
        )
        self.assertEqual(automation.on_change_field_ids.ids, [])

    def test_automation_form_view_time_triggers(self):
        on_save_automation = self.env["automation.rule"].create(
            {
                "name": "Test Automation",
                "model_id": self.env.ref(
                    "test_automation.model_automation_lead_test"
                ).id,
                "trigger": "on_create_or_write",
                "filter_domain": repr([("employee", "=", False)]),
                "trigger_field_ids": self.env.ref(
                    "test_automation.field_automation_lead_test__employee"
                ),
            }
        )

        automation = on_save_automation.copy()
        self.assertEqual(automation.filter_pre_domain, False)
        self.assertEqual(automation.filter_domain, repr([("employee", "=", False)]))
        self.assertEqual(automation.trg_date_id.id, False)
        self.assertEqual(
            automation.trigger_field_ids.ids,
            [self.env.ref("test_automation.field_automation_lead_test__employee").id],
        )

        automation_form = Form(automation, view="automation.view_automation_form")
        automation_form.trigger = "on_time_created"
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(
            automation_form.trg_date_id,
            self.env.ref("test_automation.field_automation_lead_test__create_date"),
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation = on_save_automation.copy()
        automation_form = Form(automation, view="automation.view_automation_form")
        automation_form.trigger = "on_time_updated"
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(
            automation_form.trg_date_id,
            self.env.ref("test_automation.field_automation_lead_test__write_date"),
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

        automation = on_save_automation.copy()
        automation_form = Form(automation, view="automation.view_automation_form")
        automation_form.trigger = "on_time"
        automation_form.trg_date_id = self.env.ref(
            "test_automation.field_automation_lead_test__create_date"
        )
        self.assertEqual(automation_form.filter_domain, False)
        self.assertEqual(
            automation_form.trg_date_id,
            self.env.ref("test_automation.field_automation_lead_test__create_date"),
        )
        self.assertEqual(automation_form.trigger_field_ids.ids, [])
        automation = automation_form.save()
        self.assertEqual(automation.filter_pre_domain, False)

    def test_automation_form_view_with_default_values_in_context(self):
        context = {
            "default_name": "Test Automation",
            "default_model_id": self.env.ref(
                "test_automation.model_automation_lead_test"
            ).id,
            "default_trigger": "on_create_or_write",
            "default_filter_domain": repr([("state", "=", "draft")]),
        }
        automation = self.env["automation.rule"].with_context(context)
        default_trigger_field_ids = [
            self.env.ref("test_automation.field_automation_lead_test__state").id
        ]
        automation_form = Form(automation, view="automation.view_automation_form")
        self.assertEqual(automation_form.name, context.get("default_name"))
        self.assertEqual(automation_form.model_id.id, context.get("default_model_id"))
        self.assertEqual(automation_form.trigger, context.get("default_trigger"))
        self.assertEqual(
            automation_form.trigger_field_ids.ids,
            default_trigger_field_ids,
            "trigger_field_ids should match the fields in the default filter domain.",
        )

        automation_form.trigger = "on_stage_set"
        self.assertNotEqual(
            automation_form.trigger_field_ids.ids,
            default_trigger_field_ids,
            "When user changes trigger, the trigger_field_ids field should be updated",
        )

    def test_inversion(self):
        company1 = self.env["res.partner"].create(
            {
                "name": "Gorofy",
                "is_company": True,
            }
        )
        company2 = self.env["res.partner"].create(
            {"name": "Awiclo", "is_company": True}
        )
        r = self.env["res.partner"].create(
            {"name": "Bob", "is_company": False, "parent_id": company1.id}
        )
        self.assertEqual(r.display_name, "Gorofy, Bob")
        r.parent_id = company2
        self.assertEqual(r.display_name, "Awiclo, Bob")

        create_automation(
            self,
            model_id=self.env.ref("base.model_res_partner").id,
            filter_pre_domain=False,
            trigger="on_create_or_write",
            _actions={"state": "code"},
        )
        r.parent_id = company1
        self.assertEqual(r.display_name, "Gorofy, Bob")

        create_automation(
            self,
            model_id=self.env.ref("base.model_res_partner").id,
            filter_pre_domain="[]",
            trigger="on_create_or_write",
            _actions={"state": "code"},
        )
        r.parent_id = company2
        self.assertEqual(r.display_name, "Awiclo, Bob")

    def test_computation_sequence(self):
        project = self.env["test_automation.project"].create({})
        task = self.env["test_automation.task"].create(
            {
                "project_id": project.id,
                "allocated_hours": 100,
            }
        )

        create_automation(
            self,
            model_id=self.env.ref("test_automation.model_test_automation_task").id,
            trigger="on_create_or_write",
            filter_pre_domain="[('remaining_hours', '>', 0)]",
            _actions={"state": "code"},
        )

        task.trigger_hours = 5
        self.assertRecordValues(
            task,
            [
                {
                    "effective_hours": 5,
                    "remaining_hours": 95,
                }
            ],
        )

    def test_recursion(self):
        project = self.env["test_automation.project"].create({})

        create_automation(
            self,
            model_id=self.env.ref("test_automation.model_test_automation_task").id,
            trigger="on_create_or_write",
            filter_domain=repr([("project_id", "=", project.id)]),
            _actions={"state": "code"},
        )

        task = self.env["test_automation.task"].create({"project_id": project.id})
        subtasks = task.create([{"parent_id": task.id} for _ in range(10)])
        subtasks.flush_model()

        limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(100)
            task.unlink()
        finally:
            sys.setrecursionlimit(limit)

    def test_mail_triggers(self):
        lead_model = self.env["ir.model"]._get("automation.lead.test")
        with self.assertRaises(ValidationError):
            create_automation(self, trigger="on_message_sent", model_id=lead_model.id)

        lead_thread_model = self.env["ir.model"]._get("automation.lead.thread.test")
        automation = create_automation(
            self,
            trigger="on_message_sent",
            model_id=lead_thread_model.id,
            _actions={
                "state": "object_write",
                "update_path": "active",
                "update_boolean_value": "false",
            },
        )

        ext_partner = self.env["res.partner"].create(
            {"name": "ext", "email": "email@server.com"}
        )
        internal_partner = self.env["res.users"].browse(2).partner_id

        obj = self.env["automation.lead.thread.test"].create({"name": "test"})
        obj.message_subscribe([ext_partner.id, internal_partner.id])

        obj.message_post(
            author_id=internal_partner.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertFalse(obj.active)

        obj.active = True
        obj.message_post(author_id=internal_partner.id, subtype_xmlid="mail.mt_comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=ext_partner.id, message_type="comment")
        self.assertTrue(obj.active)

        obj.message_post(author_id=internal_partner.id, message_type="comment")
        self.assertTrue(obj.active)
        obj.message_post(
            author_id=internal_partner.id,
            subtype_xmlid="mail.mt_comment",
            message_type="comment",
        )
        self.assertFalse(obj.active)

        obj.active = True
        obj.message_post(
            author_id=False,
            email_from="test_abla@test.test",
            message_type="email",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertTrue(obj.active)

        automation.trigger = "on_message_received"
        obj.active = True
        obj.message_post(
            author_id=internal_partner.id,
            subtype_xmlid="mail.mt_comment",
            message_type="comment",
        )
        self.assertTrue(obj.active)

        obj.message_post(author_id=ext_partner.id, message_type="comment")
        self.assertTrue(obj.active)

        obj.message_post(
            author_id=ext_partner.id,
            subtype_xmlid="mail.mt_comment",
            message_type="comment",
        )
        self.assertFalse(obj.active)

        obj.active = True
        obj.message_post(author_id=ext_partner.id, subtype_xmlid="mail.mt_comment")
        self.assertTrue(obj.active)

        obj.message_post(
            author_id=False,
            email_from="test_abla@test.test",
            message_type="email",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertFalse(obj.active)

    def test_multiple_mail_triggers(self):
        lead_model = self.env["ir.model"]._get("automation.lead.test")
        with self.assertRaises(ValidationError):
            create_automation(self, trigger="on_message_sent", model_id=lead_model.id)

        lead_thread_model = self.env["ir.model"]._get("automation.lead.thread.test")

        create_automation(
            self,
            trigger="on_message_sent",
            model_id=lead_thread_model.id,
            _actions={
                "state": "object_write",
                "update_path": "active",
                "update_boolean_value": "false",
            },
        )
        create_automation(
            self,
            trigger="on_message_sent",
            model_id=lead_thread_model.id,
            _actions={
                "state": "object_write",
                "evaluation_type": "equation",
                "update_path": "name",
                "value": "record.name + '!'",
            },
        )

        ext_partner = self.env["res.partner"].create(
            {"name": "ext", "email": "email@server.com"}
        )
        internal_partner = self.env["res.users"].browse(2).partner_id

        obj = self.env["automation.lead.thread.test"].create({"name": "test"})
        obj.message_subscribe([ext_partner.id, internal_partner.id])

        obj.message_post(
            author_id=internal_partner.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertFalse(obj.active)
        self.assertEqual(obj.name, "test!")

    def test_compute_on_create(self):
        lead_model = self.env["ir.model"]._get("automation.lead.test")
        stage_field = self.env["ir.model.fields"]._get(
            "automation.lead.test", "stage_id"
        )
        new_stage = self.env["test_automation.stage"].create({"name": "New"})

        create_automation(
            self,
            model_id=lead_model.id,
            trigger="on_stage_set",
            trigger_field_ids=[stage_field.id],
            _actions={
                "state": "object_create",
                "crud_model_id": self.env["ir.model"]._get("res.partner").id,
                "value": "Test Partner Automation",
            },
            filter_domain=repr([("stage_id", "=", new_stage.id)]),
        )

        self.env["automation.lead.test"].create(
            {
                "name": "Test Lead",
            }
        )

        partner_count = self.env["res.partner"].search_count(
            [("name", "=", "Test Partner Automation")]
        )
        self.assertEqual(partner_count, 1, "Only one partner should have been created")

    def test_00_form_save_update_related_model_id(self):
        with Form(
            self.env["ir.actions.server"], view="base.view_server_action_form"
        ) as f:
            f.name = "Test Action"
            f.model_id = self.env["ir.model"]._get("res.partner")
            f.state = "object_write"
            f.update_path = "user_id"
            f.evaluation_type = "value"
            f.resource_ref = "res.users,2"

        res_users_model = self.env["ir.model"]._get("res.users")
        self.assertEqual(f.update_related_model_id, res_users_model)

    def test_01_form_object_write_o2m_field(self):
        aks_partner = self.env["res.partner"].create({"name": "A Kind Shepherd"})
        bs_partner = self.env["res.partner"].create({"name": "Black Sheep"})

        f = Form(self.env["ir.actions.server"], view="base.view_server_action_form")
        f.name = "Adopt The Black Sheep"
        f.model_id = self.env["ir.model"]._get("res.partner")
        f.state = "object_write"
        f.evaluation_type = "value"
        f.update_path = "child_ids"
        self.assertEqual(f.update_m2m_operation, "add")
        self.assertEqual(f.value_field_to_show, "resource_ref")
        f.resource_ref = f"res.partner,{bs_partner.id}"
        action = f.save()

        action.with_context(
            active_model="res.partner",
            active_id=aks_partner.id,
        ).run()
        self.assertEqual(aks_partner.child_ids, bs_partner)
        self.assertEqual(bs_partner.parent_id, aks_partner)

        f.update_m2m_operation = "remove"
        action = f.save()
        action.with_context(
            active_model="res.partner",
            active_id=aks_partner.id,
        ).run()
        self.assertEqual(aks_partner.child_ids.ids, [])
        self.assertEqual(bs_partner.parent_id.id, False)

    def test_02_form_object_write_with_sequence(self):
        test_partner = self.env["res.partner"].create({"name": "Test Partner"})
        test_sequence = self.env["ir.sequence"].create(
            {
                "name": "Test Sequence",
                "padding": 4,
                "prefix": "PARTNER/",
                "suffix": "/TEST",
            }
        )

        f = Form(self.env["ir.actions.server"], view="base.view_server_action_form")
        f.model_id = self.env["ir.model"]._get("res.partner")
        f.state = "object_write"
        f.evaluation_type = "sequence"
        missing = "Choose the sequence the value is drawn from."
        self.assertEqual(f.warning, missing)
        f.update_path = "active"
        self.assertEqual(
            f.warning,
            f"A sequence must only be used with character fields.\n\n{missing}",
        )
        f.update_path = "ref"
        self.assertEqual(f.warning, missing)
        f.sequence_id = test_sequence
        self.assertEqual(f.warning, False)

        action = f.save()
        self.assertEqual(test_partner.ref, False)
        action.with_context(
            active_model="res.partner",
            active_id=test_partner.id,
        ).run()
        self.assertEqual(test_partner.ref, "PARTNER/0001/TEST")

    def test_03_server_action_code_history_wizard(self):
        self.env.user.tz = "Europe/Brussels"

        def get_history(action):
            return self.env["ir.actions.server.history"].search(
                [("action_id", "=", action.id)]
            )

        def assert_history(action, expected):
            history = get_history(action)
            self.assertRecordValues(history, expected)

        expected = []

        with freeze_time("2025-05-01 08:00:00"):
            self.env.cr._now = datetime.datetime.now()
            action = self.env["ir.actions.server"].create(
                {
                    "name": "Test Action",
                    "model_id": self.env["ir.model"]._get("res.partner").id,
                    "state": "code",
                    "code": "pass",
                }
            )
        expected.insert(
            0,
            {
                "code": "pass",
                "display_name": WhitespaceInsensitive(
                    f"May 1, 2025, 10:00:00 AM - {self.env.ref('base.user_root').name}"
                ),
            },
        )
        assert_history(action, expected)

        with freeze_time("2025-05-01 08:30:00"):
            self.env.cr._now = datetime.datetime.now()
            action.with_user(self.env.ref("base.user_admin")).write({"code": "hello"})
        expected.insert(
            0,
            {
                "code": "hello",
                "display_name": WhitespaceInsensitive(
                    f"May 1, 2025, 10:30:00 AM - {self.env.ref('base.user_admin').name}"
                ),
            },
        )
        assert_history(action, expected)

        with freeze_time("2025-05-05 11:30:00"):
            self.env.cr._now = datetime.datetime.now()
            action.with_user(self.env.ref("base.user_admin")).write({"code": "coucou"})
        expected.insert(
            0,
            {
                "code": "coucou",
                "display_name": WhitespaceInsensitive(
                    f"May 5, 2025, 1:30:00 PM - {self.env.ref('base.user_admin').name}"
                ),
            },
        )
        assert_history(action, expected)

        with freeze_time("2025-05-12 09:30:00"):
            self.env.cr._now = datetime.datetime.now()
            with Form(
                self.env["wizard.ir.actions.server.restore.revision"].with_context(
                    default_action_id=action.id
                )
            ) as wizard_form:
                self.assertRecordValues(
                    wizard_form.revision,
                    [
                        {
                            "code": "hello",
                            "display_name": WhitespaceInsensitive(
                                f"May 1, 2025, 10:30:00 AM - {self.env.ref('base.user_admin').name}"
                            ),
                        }
                    ],
                )
                first_diff = str(wizard_form.code_diff)
                wizard_form.revision = get_history(action)[-1]
                second_diff = str(wizard_form.code_diff)
                self.assertNotEqual(first_diff, second_diff)
            wizard_form.record.restore_revision()

        self.assertEqual(action.code, "pass")
        expected.insert(
            0,
            {
                "code": "pass",
                "display_name": WhitespaceInsensitive(
                    f"May 12, 2025, 11:30:00 AM - {self.env.ref('base.user_root').name}"
                ),
            },
        )
        assert_history(action, expected)

    def test_server_action_code_history_wizard_with_no_timezone(self):
        self.env.user.tz = False

        def get_history(action):
            return self.env["ir.actions.server.history"].search(
                [("action_id", "=", action.id)]
            )

        def assert_history(action, expected):
            history = get_history(action)
            self.assertRecordValues(history, expected)

        expected = []

        with freeze_time("2025-05-01 10:00:00"):
            self.env.cr._now = datetime.datetime.now()
            action = self.env["ir.actions.server"].create(
                {
                    "name": "Test Action",
                    "model_id": self.env["ir.model"]._get("res.partner").id,
                    "state": "code",
                    "code": "pass",
                }
            )
        expected.insert(
            0,
            {
                "code": "pass",
                "display_name": WhitespaceInsensitive(
                    f"May 1, 2025, 10:00:00 AM - {self.env.ref('base.user_root').name}"
                ),
            },
        )
        assert_history(action, expected)

        with freeze_time("2025-05-01 10:00:00"):
            self.env.cr._now = datetime.datetime.now()
            action.with_user(self.env.ref("base.user_admin")).write({"code": "hello"})
        expected.insert(
            0,
            {
                "code": "hello",
                "display_name": WhitespaceInsensitive(
                    f"May 1, 2025, 10:00:00 AM - {self.env.ref('base.user_admin').name}"
                ),
            },
        )
        assert_history(action, expected)

        with freeze_time("2025-05-12 10:00:00"):
            self.env.cr._now = datetime.datetime.now()
            with Form(
                self.env["wizard.ir.actions.server.restore.revision"].with_context(
                    default_action_id=action.id
                )
            ) as wizard_form:
                self.assertRecordValues(
                    wizard_form.revision,
                    [
                        {
                            "code": "pass",
                            "display_name": WhitespaceInsensitive(
                                f"May 1, 2025, 10:00:00 AM - {self.env.ref('base.user_root').name}"
                            ),
                        }
                    ],
                )
                first_diff = str(wizard_form.code_diff)
                wizard_form.revision = get_history(action)[-1]
                second_diff = str(wizard_form.code_diff)
                self.assertNotEqual(first_diff, second_diff)
            wizard_form.record.restore_revision()

        self.assertEqual(action.code, "pass")
        expected.insert(
            0,
            {
                "code": "pass",
                "display_name": WhitespaceInsensitive(
                    f"May 12, 2025, 10:00:00 AM - {self.env.ref('base.user_root').name}"
                ),
            },
        )
        assert_history(action, expected)


@common.tagged("post_install", "-at_install")
class TestHttp(common.HttpCase):
    def test_webhook_trigger(self):
        model = self.env["ir.model"]._get("automation.linked.test")
        record_getter = "model.search([('name', '=', payload['name'])]) if payload.get('name') else None"
        automation = create_automation(
            self,
            trigger="on_webhook",
            auth_type="none",
            model_id=model.id,
            record_getter=record_getter,
            _actions={
                "state": "object_write",
                "update_path": "another_field",
                "value": "written",
            },
        )

        obj = self.env[model.model].create({"name": "some name"})
        response = self.url_open(automation.url, data=json_dumps({"name": "some name"}))
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(obj.another_field, "written")

        obj.another_field = False
        with mute_logger("odoo.addons.automation.models.automation_rule"):
            response = self.url_open(automation.url, data=json_dumps({}))
        self.assertEqual(response.json()["error"], "webhook_failed")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(obj.another_field, False)

        response = self.url_open(
            "/web/hook/0123456789", data=json_dumps({"name": "some name"})
        )
        self.assertEqual(response.json()["error"], "endpoint_not_found")
        self.assertEqual(response.status_code, 404)

    def test_payload_in_action_server(self):
        model = self.env["ir.model"]._get("automation.linked.test")
        record_getter = "model.search([('name', '=', payload['name'])]) if payload.get('name') else None"
        automation = create_automation(
            self,
            trigger="on_webhook",
            auth_type="none",
            model_id=model.id,
            record_getter=record_getter,
            _actions={
                "state": "code",
                "code": "record.write({'another_field': json.dumps(payload)})",
            },
        )

        obj = self.env[model.model].create({"name": "some name"})
        self.url_open(
            automation.url,
            data=json_dumps({"name": "some name", "test_key": "test_value"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(
            json_loads(obj.another_field),
            {
                "name": "some name",
                "test_key": "test_value",
            },
        )

        obj.another_field = ""
        self.url_open(automation.url + "?test_param=test_value&name=some%20name")
        self.assertEqual(
            json_loads(obj.another_field),
            {
                "name": "some name",
                "test_param": "test_value",
            },
        )

    def test_webhook_send_and_receive(self):
        model = self.env["ir.model"]._get("automation.linked.test")
        obj = self.env[model.model].create({"name": "some name"})

        automation_receiver = create_automation(
            self,
            trigger="on_webhook",
            auth_type="none",
            model_id=model.id,
            record_getter="model.env[payload.get('_model')].browse(int(payload.get('_id')))",
            _actions={
                "state": "code",
                "code": "record.write({'another_field': json.dumps(payload)})",
            },
        )
        name_field_id = self.env.ref(
            "test_automation.field_automation_linked_test__name"
        )
        automation_sender = create_automation(
            self,
            trigger="on_write",
            model_id=model.id,
            trigger_field_ids=[(6, 0, [name_field_id.id])],
            _actions={
                "name": "Send Webhook Notification",
                "state": "webhook",
                "webhook_url": automation_receiver.url,
            },
        )

        self.env["ir.config_parameter"].set_param(
            "base.egress_allowed_networks", "127.0.0.0/8, ::1/128"
        )
        obj.name = "new_name"
        self.cr.flush()
        with self.allow_requests(all_requests=True):
            self.cr.postcommit.run()
        self.cr.clear()
        self._wait_remaining_requests()
        self.assertEqual(
            json_loads(obj.another_field),
            {
                "_action": f"Send Webhook Notification(#{automation_sender.action_server_ids[0].id})",
                "_id": obj.id,
                "_model": obj._name,
                "id": obj.id,
            },
        )

    def test_webhook_refuses_loopback_target(self):
        model = self.env["ir.model"]._get("automation.linked.test")
        obj = self.env[model.model].create({"name": "loopback probe"})
        automation = create_automation(
            self,
            trigger="on_hand",
            model_id=model.id,
            _actions={
                "name": "Send Webhook Notification",
                "state": "webhook",
                "webhook_url": "http://127.0.0.1:8069/web/hook/whatever",
            },
        )
        with self.assertRaises(UserError) as caught:
            automation.action_server_ids.with_context(
                active_model=obj._name,
                active_id=obj.id,
                active_ids=obj.ids,
            ).run()
        self.assertIn("127.0.0.1 is a loopback address", str(caught.exception))

    def test_on_change_get_views_cache(self):
        model_name = "automation.lead.test"
        my_view = self.env["ir.ui.view"].create(
            {
                "name": "My View",
                "model": model_name,
                "type": "form",
                "arch": "<form><field name='active'/></form>",
            }
        )
        self.assertEqual(
            self.env[model_name].get_view(my_view.id)["arch"],
            '<form><field name="active"/></form>',
        )
        model = self.env["ir.model"]._get(model_name)
        active_field = self.env["ir.model.fields"]._get(model_name, "active")
        create_automation(
            self,
            trigger="on_change",
            model_id=model.id,
            on_change_field_ids=[Command.set([active_field.id])],
            _actions={
                "state": "code",
                "code": "",
            },
        )
        self.assertEqual(
            self.env[model_name].get_view(my_view.id)["arch"],
            '<form><field name="active" on_change="1"/></form>',
        )
