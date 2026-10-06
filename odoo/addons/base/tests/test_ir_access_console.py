from odoo.fields import Command
from odoo.service.model import calling
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAccessConsole(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="console_admin", groups="base.group_erp_manager"
        )
        cls.system = new_test_user(
            cls.env, login="console_system", groups="base.group_system"
        )
        cls.readers = cls.env["res.groups"].create({"name": "Probe: industry desk"})
        cls.model_id = cls.env["ir.model"]._get_id("res.partner.industry")
        Access = cls.env["ir.access"]
        cls.read_own = Access.create(
            {
                "name": "Probe: the desk reads its own industries",
                "model_id": cls.model_id,
                "group_id": cls.readers.id,
                "kind": "permission",
                "operation": "r",
                "reach": "own",
                "anchor": "creator",
            }
        )
        cls.write_all = Access.create(
            {
                "name": "Probe: the desk updates every industry",
                "model_id": cls.model_id,
                "group_id": cls.readers.id,
                "kind": "permission",
                "operation": "ru",
            }
        )
        cls.guard = Access.create(
            {
                "name": "Probe: nobody reads a retired industry",
                "model_id": cls.model_id,
                "group_id": cls.env.ref("base.group_everyone").id,
                "kind": "guard",
                "operation": "r",
                "domain": "[('name', 'not like', 'retired')]",
            }
        )

    def cell(self, group=None):
        return (
            self.env["ir.access.matrix"]
            .with_user(self.admin)
            .search(
                [
                    ("model_id", "=", self.model_id),
                    ("group_id", "=", (group or self.readers).id),
                ]
            )
        )

    def test_every_console_page_opens_for_whoever_its_menu_names(self):
        root = self.env.ref("base.menu_access")
        self.assertEqual(root.parent_id, self.env.ref("base.menu_administration"))
        leaves = (
            self.env["ir.ui.menu"]
            .search([("id", "child_of", root.id)])
            .filtered(lambda menu: not menu.child_id)
        )
        self.assertGreaterEqual(len(leaves), 14)
        for menu in leaves:
            with self.subTest(menu=menu.complete_name):
                user = (
                    self.system
                    if self.env.ref("base.group_system") in menu.group_ids
                    else self.admin
                )
                visible = self.env["ir.ui.menu"].with_user(user)._get_visible_menu_ids()
                self.assertIn(menu.id, visible)
                action = menu.action
                if action._name == "ir.actions.server":
                    action = action.with_user(user).run()
                    res_model, view_mode = action["res_model"], action["view_mode"]
                else:
                    self.assertEqual(action._name, "ir.actions.act_window")
                    res_model, view_mode = action.res_model, action.view_mode
                Model = self.env[res_model].with_user(user)
                modes = [mode for mode in view_mode.split(",") if mode]
                views = Model.get_views(
                    [(False, mode) for mode in modes] + [(False, "search")]
                )
                self.assertEqual(set(views["views"]), {*modes, "search"})
                if "list" in modes and not Model._transient:
                    Model.web_search_read([], {"display_name": {}}, limit=5)

    def test_a_cell_holds_each_operations_reach_and_the_models_guards(self):
        cell = self.cell()
        self.assertEqual(len(cell), 1)
        self.assertEqual(cell.read_reach, "All, Own")
        self.assertEqual(cell.write_reach, "All")
        self.assertFalse(cell.create_reach)
        self.assertFalse(cell.unlink_reach)
        self.assertEqual(cell.operation_count, 2)
        self.assertEqual(cell.permission_count, 2)
        self.assertIn(self.guard.name, cell.guard_names)
        self.assertGreaterEqual(cell.guard_count, 1)

    def test_an_inactive_row_is_not_in_the_matrix(self):
        self.write_all.active = False
        cell = self.cell()
        self.assertEqual(cell.read_reach, "Own")
        self.assertFalse(cell.write_reach)

    def test_a_verbs_reach_is_its_own(self):
        changeset_model = self.env["ir.model"]._get_id("ir.access.changeset")
        self.env["ir.access"].create(
            {
                "name": "Probe: the desk activates every change set",
                "model_id": changeset_model,
                "group_id": self.readers.id,
                "kind": "permission",
                "verbs": "activate",
            }
        )
        cell = self.env["ir.access.matrix"].search(
            [("model_id", "=", changeset_model), ("group_id", "=", self.readers.id)]
        )
        self.assertEqual(cell.verb_reach, "activate: All")
        self.assertEqual(cell.operation_count, 0)

    def test_a_privilege_is_filtered_apart(self):
        privilege = self.env.ref("base.privilege_apply_review")
        Matrix = self.env["ir.access.matrix"].with_user(self.admin)
        cells = Matrix.search([("is_privilege", "=", True)])
        self.assertIn(privilege, cells.group_id)
        self.assertNotIn(self.readers, cells.group_id)

    def test_a_staged_change_marks_its_cells_until_activation(self):
        with calling("ir.access"):
            self.write_all.with_user(self.admin).write({"operation": "rud"})
        changeset = self.env["ir.access.changeset"].search(
            [("author_id", "=", self.admin.id), ("state", "=", "draft")]
        )
        Matrix = self.env["ir.access.matrix"].with_user(self.admin)
        self.assertEqual(
            Matrix.search([("changeset_ids", "in", changeset.ids)]), self.cell()
        )
        self.assertIn(self.cell(), Matrix.search([("changeset_ids", "!=", False)]))
        self.assertEqual(self.cell().changeset_ids, changeset)
        self.assertFalse(self.cell().unlink_reach, "staged, not live")
        action = changeset.with_user(self.admin).action_open_matrix()
        self.assertEqual(Matrix.search(action["domain"]), self.cell())
        changeset.action_activate()
        self.assertEqual(self.cell().unlink_reach, "All")
        self.assertFalse(self.cell().changeset_ids, "no open change set touches it")
        self.assertNotIn(self.cell(), Matrix.search([("changeset_ids", "!=", False)]))
        self.assertEqual(
            Matrix.search(action["domain"]), self.cell(), "what it changed, still"
        )

    def test_a_group_implication_in_a_change_set_marks_the_groups_column(self):
        implied = self.env.ref("base.group_partner_manager")
        with calling("res.groups"):
            self.readers.with_user(self.admin).implied_ids = [Command.link(implied.id)]
        changeset = self.env["ir.access.changeset"].search(
            [("author_id", "=", self.admin.id), ("state", "=", "draft")]
        )
        Matrix = self.env["ir.access.matrix"].with_user(self.admin)
        self.assertEqual(
            Matrix.search([("changeset_ids", "in", changeset.ids)]).group_id,
            self.readers,
        )

    def test_a_grant_shows_the_duties_its_holder_holds_in_conflict(self):
        payers = self.env["res.groups"].create({"name": "Probe: payers"})
        approvers = self.env["res.groups"].create({"name": "Probe: approvers"})
        Function = self.env["ir.access.sod.function"]
        rule = self.env["ir.access.sod.rule"].create(
            {
                "name": "Probe: pay and approve",
                "function_a_id": Function.create(
                    {"name": "pay", "group_ids": [Command.link(payers.id)]}
                ).id,
                "function_b_id": Function.create(
                    {"name": "approve", "group_ids": [Command.link(approvers.id)]}
                ).id,
                "action": "warn",
            }
        )
        clerk = new_test_user(self.env, login="console_clerk", groups="base.group_user")
        Grant = self.env["res.users.grant"]
        with mute_logger("odoo.addons.base.models.ir_access_sod"):
            first = Grant.create({"user_id": clerk.id, "group_id": payers.id})
            self.assertFalse(first.sod_rule_ids)
            second = Grant.create({"user_id": clerk.id, "group_id": approvers.id})
        first.invalidate_recordset(["sod_rule_ids"])
        self.assertEqual(first.sod_rule_ids, rule)
        self.assertEqual(second.sod_rule_ids, rule)
        found = Grant.with_user(self.admin).search([("sod_rule_ids", "!=", False)])
        self.assertIn(first, found)
        self.assertEqual(
            Grant.search([("sod_rule_ids", "in", rule.ids)]).user_id, clerk
        )
