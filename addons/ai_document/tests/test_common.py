from odoo import Command
from odoo.tests import Form, TransactionCase

from odoo.addons.ai_fields.tools import ai_field_insert


class TestAiDocumentsCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user_internal = cls.env["res.users"].create(
            {
                "name": "user_test",
                "login": "user_test",
                "group_ids": [
                    Command.set(cls.env.ref("base.group_user").ids),
                ],
            }
        )
        cls.ir_action_tools_childs = cls.env["ir.actions.server"].create(
            [
                {
                    "model_id": cls.env["ir.model"]._get_id("document.document"),
                    "state": "code",
                    "name": "Write Name",
                    "code": "record.write({'name': new_name})",
                },
                {
                    "model_id": cls.env["ir.model"]._get_id("document.document"),
                    "state": "code",
                    "name": "Return Count",
                    "code": "ai['result'] = 'action return value'",
                },
            ]
        )

        cls.folder, cls.target_folder, cls.other_folder = cls.env[
            "document.document"
        ].create(
            [
                {
                    "name": "Folder",
                    "type": "folder",
                },
                {
                    "name": "Target Folder",
                    "type": "folder",
                },
                {
                    "name": "Other Folder",
                    "type": "folder",
                },
            ]
        )

    def setUp(self):
        super().setUp()

        self.ir_action_tool = self.env["ir.actions.server"].create(
            {
                "model_id": self.env["ir.model"]._get_id("document.document"),
                "state": "multi",
                "name": "Rename and return count",
                "use_in_ai": False,
                "child_ids": self.ir_action_tools_childs.ids,
            }
        )

        Doc = self.env["document.document"]
        sort_wizard = Form(
            self.env["wizard.document.document.setup.ai.sort"].with_context(
                default_folder_id=self.folder.id
            )
        )
        sort_wizard.ai_sort_prompt = f"Execute the action then move in {Doc._ai_folder_insert(self.target_folder.id)} here is the name {ai_field_insert('name', 'Name')}"
        sort_wizard.ai_tool_ids.clear()
        sort_wizard.ai_tool_ids.add(
            self.env.ref("ai_document.ir_actions_server_move_in_folder")
        )
        sort_wizard.ai_tool_ids.add(self.ir_action_tool)
        sort_wizard.save().action_setup_folder()
        self.env["automation.rule"]._unregister_hook()
        self.env["automation.rule"]._register_hook()

    def tearDown(self):
        super().tearDown()
        self.env["automation.rule"].search(
            [("ai_autosort_folder_id", "!=", False)]
        ).unlink()
        self.env["automation.rule"]._unregister_hook()
        self.env["automation.rule"]._register_hook()
