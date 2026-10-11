from unittest.mock import patch

from odoo import Command
from odoo.libs.colors import hex_to_rgb
from odoo.libs.colors.contrast import WCAG_AA_TEXT, contrast_ratio
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.base.models.ir_ui_menu import ACCENT_SURFACES, IrUiMenu


class TestMenu(TransactionCase):
    def test_00_menu_deletion(self):
        Menu = self.env["ir.ui.menu"]
        root = Menu.create({"name": "Test root"})
        child1 = Menu.create({"name": "Test child 1", "parent_id": root.id})
        child2 = Menu.create({"name": "Test child 2", "parent_id": root.id})
        child21 = Menu.create({"name": "Test child 2-1", "parent_id": child2.id})
        all_ids = [root.id, child1.id, child2.id, child21.id]

        root.unlink()

        remaining = Menu.search([("id", "in", all_ids)], order="id")
        self.assertEqual([child1.id, child2.id, child21.id], remaining.ids)

        orphans = Menu.search(
            [("id", "in", all_ids), ("parent_id", "=", False)], order="id"
        )
        self.assertEqual([child1.id, child2.id], orphans.ids)

    def test_display_name_recomputed_on_ancestor_rename(self):
        Menu = self.env["ir.ui.menu"]
        root = Menu.create({"name": "Path root"})
        child = Menu.create({"name": "Child", "parent_id": root.id})
        grandchild = Menu.create({"name": "Leaf", "parent_id": child.id})
        self.assertEqual(grandchild.display_name, "Path root/Child/Leaf")

        root.name = "Renamed root"
        self.assertEqual(grandchild.display_name, "Renamed root/Child/Leaf")
        self.assertEqual(grandchild.complete_name, "Renamed root/Child/Leaf")


class TestMenuVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Menu = cls.env["ir.ui.menu"]
        cls.Action = cls.env["ir.actions.act_window"]
        cls.employee = new_test_user(
            cls.env, login="menu_employee", groups="base.group_user"
        )

    def _act_window(self, res_model):
        return self.Action.create(
            {
                "name": f"action {res_model}",
                "res_model": res_model,
                "view_ids": [Command.create({"view_mode": "form"})],
            }
        )

    def test_visible_menu_ids_action_acl_gate(self):
        readable = self._act_window("res.partner")
        restricted = self._act_window("ir.config_parameter")
        root = self.Menu.create({"name": "ACL root"})
        menu_readable = self.Menu.create(
            {
                "name": "Readable",
                "parent_id": root.id,
                "action": f"{readable._name},{readable.id}",
            }
        )
        menu_restricted = self.Menu.create(
            {
                "name": "Restricted",
                "parent_id": root.id,
                "action": f"{restricted._name},{restricted.id}",
            }
        )

        admin_visible = self.Menu._get_visible_menu_ids()
        self.assertIn(menu_readable.id, admin_visible)
        self.assertIn(menu_restricted.id, admin_visible)
        self.assertIn(root.id, admin_visible)

        emp_visible = self.Menu.with_user(self.employee)._get_visible_menu_ids()
        self.assertIn(menu_readable.id, emp_visible)
        self.assertNotIn(menu_restricted.id, emp_visible)
        self.assertIn(root.id, emp_visible)

    def test_visible_menu_ids_client_action_without_a_model(self):
        action = self.env["ir.actions.client"].create(
            {"name": "modelless client action", "tag": "test_tag"}
        )
        self.assertFalse(action.res_model, "the case under test")
        root = self.Menu.create({"name": "Client root"})
        menu = self.Menu.create(
            {
                "name": "Client",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )

        visible = self.Menu.with_user(self.employee)._get_visible_menu_ids()
        self.assertIn(menu.id, visible, "no model named means no model-level gate")
        self.assertIn(root.id, visible)

    def test_visible_menu_ids_client_action_with_a_model_is_still_gated(self):
        action = self.env["ir.actions.client"].create(
            {
                "name": "restricted client action",
                "tag": "test_tag",
                "res_model": "ir.config_parameter",
            }
        )
        root = self.Menu.create({"name": "Gated client root"})
        menu = self.Menu.create(
            {
                "name": "Gated client",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )

        self.assertIn(menu.id, self.Menu._get_visible_menu_ids())
        self.assertNotIn(
            menu.id, self.Menu.with_user(self.employee)._get_visible_menu_ids()
        )

    def test_visible_menu_ids_deleted_action_hidden(self):
        action = self._act_window("res.partner")
        root = self.Menu.create({"name": "Dangling root"})
        menu = self.Menu.create(
            {
                "name": "Dangling",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )
        self.assertIn(menu.id, self.Menu._get_visible_menu_ids())

        action.unlink()
        visible = self.Menu._get_visible_menu_ids()
        self.assertNotIn(menu.id, visible)
        self.assertNotIn(root.id, visible)

    def test_visible_menu_ids_group_gate(self):
        group = self.env["res.groups"].create({"name": "Menu test group"})
        action = self._act_window("res.partner")
        parent = self.Menu.create(
            {"name": "Gated parent", "group_ids": [Command.set(group.ids)]}
        )
        child = self.Menu.create(
            {
                "name": "Child",
                "parent_id": parent.id,
                "action": f"{action._name},{action.id}",
            }
        )

        emp_visible = self.Menu.with_user(self.employee)._get_visible_menu_ids()
        self.assertNotIn(child.id, emp_visible)
        self.assertNotIn(parent.id, emp_visible)

        self.employee.write({"group_ids": [Command.link(group.id)]})
        emp_visible = self.Menu.with_user(self.employee)._get_visible_menu_ids()
        self.assertIn(child.id, emp_visible)
        self.assertIn(parent.id, emp_visible)

    def test_visible_menu_ids_cache_keyed_by_group_set(self):
        action = self._act_window("ir.config_parameter")
        root = self.Menu.create({"name": "Cache root"})
        menu = self.Menu.create(
            {
                "name": "Needs system",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )

        self.assertNotIn(
            menu.id, self.Menu.with_user(self.employee)._get_visible_menu_ids()
        )

        self.employee.write(
            {"group_ids": [Command.link(self.env.ref("base.group_system").id)]}
        )
        self.assertIn(
            menu.id, self.Menu.with_user(self.employee)._get_visible_menu_ids()
        )

    def test_visible_menu_ids_keyed_on_debug(self):
        action = self._act_window("res.partner")
        debug_root = self.Menu.create(
            {
                "name": "Debug only root",
                "group_ids": [Command.set(self.env.ref("base.group_no_one").ids)],
                "action": f"{action._name},{action.id}",
            }
        )

        self.assertNotIn(debug_root.id, self.Menu._get_visible_menu_ids(False))
        self.assertIn(debug_root.id, self.Menu._get_visible_menu_ids(True))

    def test_load_menus_root_keyed_on_debug(self):
        self.assertIn(
            "bool(self._get_session_debug())", IrUiMenu.load_menus_root.__cache__.args
        )

        action = self._act_window("res.partner")
        debug_root = self.Menu.create(
            {
                "name": "Debug only root",
                "group_ids": [Command.set(self.env.ref("base.group_no_one").ids)],
                "action": f"{action._name},{action.id}",
            }
        )
        self.assertFalse(self.Menu._get_session_debug())

        roots_no_debug = self.Menu.load_menus_root()
        self.assertNotIn(debug_root.id, roots_no_debug["all_menu_ids"])

        with self.debug_mode():
            self.assertEqual(self.Menu._get_session_debug(), "1")
            roots_debug = self.Menu.load_menus_root()
            self.assertIn(debug_root.id, roots_debug["all_menu_ids"])

        roots_again = self.Menu.load_menus_root()
        self.assertNotIn(debug_root.id, roots_again["all_menu_ids"])

    def test_load_menus_answers_the_debug_flag_it_is_keyed_on(self):
        action = self._act_window("res.partner")
        debug_root = self.Menu.create(
            {
                "name": "Debug only root",
                "group_ids": [Command.set(self.env.ref("base.group_no_one").ids)],
                "action": f"{action._name},{action.id}",
            }
        )
        self.assertFalse(self.Menu._get_session_debug())

        self.assertIn(
            debug_root.id,
            self.Menu.load_menus(True),
            "load_menus(True) outside a debug session is cached under the debug "
            "key, so it must be the debug answer",
        )
        self.assertNotIn(debug_root.id, self.Menu.load_menus(False))
        with self.debug_mode():
            self.assertNotIn(
                debug_root.id,
                self.Menu.load_menus(False),
                "load_menus(False) inside a debug session must not leak the "
                "debug-only menus into the non-debug cache entry",
            )
            self.assertIn(debug_root.id, self.Menu.load_menus(True))

    def test_a_sudo_caller_does_not_widen_the_cached_set(self):
        action = self._act_window("ir.config_parameter")
        menu = self.Menu.create(
            {"name": "Needs system", "action": f"{action._name},{action.id}"}
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertNotIn(menu.id, employee_menus.sudo()._get_visible_menu_ids())
        self.assertNotIn(menu.id, employee_menus._get_visible_menu_ids())
        self.assertNotIn(menu.id, employee_menus.sudo().load_menus(False))

    def test_an_action_restricted_to_other_groups_hides_its_menu(self):
        action = self._act_window("res.partner")
        action.group_ids = self.env.ref("base.group_system")
        menu = self.Menu.create(
            {"name": "Admins only", "action": f"{action._name},{action.id}"}
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertNotIn(menu.id, employee_menus._get_visible_menu_ids())
        self.assertNotIn(menu.id, employee_menus.load_menus(False))

        action.group_ids = False
        self.assertIn(menu.id, employee_menus._get_visible_menu_ids())

    def test_a_menu_under_a_parent_the_user_cannot_open_is_not_visible(self):
        action = self._act_window("res.partner")
        root = self.Menu.create({"name": "Open root"})
        closed = self.Menu.create(
            {
                "name": "Administrators only",
                "parent_id": root.id,
                "group_ids": [Command.set(self.env.ref("base.group_system").ids)],
            }
        )
        leaf = self.Menu.create(
            {
                "name": "Open leaf",
                "parent_id": closed.id,
                "action": f"{action._name},{action.id}",
            }
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertIn(leaf.id, self.Menu._get_visible_menu_ids())
        for visible in (
            employee_menus._get_visible_menu_ids(),
            employee_menus.load_menus(False),
            set(employee_menus.browse([root.id, leaf.id])._filter_visible_menus()._ids),
        ):
            self.assertNotIn(leaf.id, visible)
            self.assertNotIn(root.id, visible)

        closed.group_ids = False
        for visible in (
            employee_menus._get_visible_menu_ids(),
            employee_menus.load_menus(False),
        ):
            self.assertIn(leaf.id, visible)
            self.assertIn(root.id, visible)

    def test_a_hidden_folder_takes_its_subtree_with_it(self):
        action = self._act_window("res.partner")
        root = self.Menu.create({"name": "Root"})
        folder = self.Menu.create({"name": "Folder", "parent_id": root.id})
        leaf = self.Menu.create(
            {
                "name": "Leaf",
                "parent_id": folder.id,
                "action": f"{action._name},{action.id}",
            }
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertIn(leaf.id, employee_menus.load_menus(False))
        self.addCleanup(self.env.registry.clear_cache)
        with patch.object(IrUiMenu, "_get_hidden_menu_ids", lambda menus: {folder.id}):
            self.env.registry.clear_cache()
            visible = employee_menus._get_visible_menu_ids()
            loaded = employee_menus.load_menus(False)
        for menu in (root, folder, leaf):
            self.assertNotIn(menu.id, visible)
            self.assertNotIn(menu.id, loaded)

    def test_menus_are_hidden_through_the_hook_not_by_overriding_the_set(self):
        self.assertIs(
            type(self.Menu)._get_visible_menu_ids,
            IrUiMenu._get_visible_menu_ids,
            "an override applied after the cached set would run after the pruning "
            "and leave orphans; extend _get_hidden_menu_ids instead",
        )

    def test_a_blacklisted_menu_hides_what_lies_under_it(self):
        action = self._act_window("res.partner")
        root = self.Menu.create({"name": "Root"})
        branch = self.Menu.create({"name": "Branch", "parent_id": root.id})
        leaf = self.Menu.create(
            {
                "name": "Leaf",
                "parent_id": branch.id,
                "action": f"{action._name},{action.id}",
            }
        )
        sibling = self.Menu.create(
            {
                "name": "Sibling",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertIn(leaf.id, employee_menus.load_menus(False))
        self.addCleanup(self.env.registry.clear_cache)
        with patch.object(
            IrUiMenu, "_get_blacklisted_menu_ids", lambda menus: [branch.id]
        ):
            self.env.registry.clear_cache()
            self.assertFalse(employee_menus.browse(leaf.id)._filter_visible_menus())
            loaded = employee_menus.load_menus(False)
        self.assertNotIn(branch.id, loaded)
        self.assertNotIn(leaf.id, loaded)
        self.assertEqual(loaded[root.id]["children"], [sibling.id])

    def test_an_app_whose_only_entry_is_blacklisted_is_not_drawn(self):
        action = self._act_window("res.partner")
        root = self.Menu.create({"name": "App"})
        entry = self.Menu.create(
            {
                "name": "Only entry",
                "parent_id": root.id,
                "action": f"{action._name},{action.id}",
            }
        )
        employee_menus = self.Menu.with_user(self.employee)
        self.assertIn(root.id, employee_menus.load_menus_root()["all_menu_ids"])
        self.addCleanup(self.env.registry.clear_cache)
        with patch.object(
            IrUiMenu, "_get_blacklisted_menu_ids", lambda menus: [entry.id]
        ):
            self.env.registry.clear_cache()
            loaded = employee_menus.load_menus(False)
            roots = employee_menus.load_menus_root()["all_menu_ids"]
            filtered = employee_menus.browse(root.id)._filter_visible_menus()
        self.assertNotIn(entry.id, loaded)
        self.assertNotIn(root.id, loaded)
        self.assertNotIn(root.id, loaded["root"]["children"])
        self.assertNotIn(root.id, roots)
        self.assertFalse(filtered)

    def test_every_debug_spelling_shares_one_entry(self):
        self.assertIs(
            self.Menu._get_visible_menu_ids("assets"),
            self.Menu._get_visible_menu_ids(True),
        )
        self.assertIs(
            self.Menu._get_visible_menu_ids(""), self.Menu._get_visible_menu_ids(False)
        )
        self.assertIs(self.Menu.load_menus("1"), self.Menu.load_menus(True))


class TestMenuMisc(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Menu = self.env["ir.ui.menu"]

    def test_copy_suffixes_name(self):
        menu = self.Menu.create({"name": "Original"})
        copy1 = menu.copy()
        self.assertEqual(copy1.name, "Original (1)")

        copy2 = copy1.copy()
        self.assertEqual(copy2.name, "Original (2)")

    def test_copy_ignores_mid_name_number(self):
        menu = self.Menu.create({"name": "Budget (2025) Plan"})
        copy1 = menu.copy()
        self.assertEqual(copy1.name, "Budget (2025) Plan (1)")

        copy2 = copy1.copy()
        self.assertEqual(copy2.name, "Budget (2025) Plan (2)")

    def _count_cache_clears(self):
        registry_class = type(self.env.registry)
        calls = []
        original = registry_class.clear_cache

        def counting(reg, *cache_names):
            calls.append(cache_names)
            return original(reg, *cache_names)

        return patch.object(registry_class, "clear_cache", counting), calls

    def test_multi_copy_names_and_single_invalidation(self):
        menus = self.Menu.create([{"name": f"Multi {i}"} for i in range(3)])
        patcher, calls = self._count_cache_clears()
        with patcher:
            copies = menus.copy()
        self.assertEqual(
            copies.mapped("name"), ["Multi 0 (1)", "Multi 1 (1)", "Multi 2 (1)"]
        )
        self.assertEqual(
            len(calls),
            1,
            "copying N menus must invalidate the cache once (the batched "
            "create), not once per copied menu",
        )

    def test_copy_suffixes_explicit_default_name(self):
        menu = self.Menu.create({"name": "Original"})
        copy = menu.copy({"name": "Custom"})
        self.assertEqual(copy.name, "Custom (1)")

    def test_empty_operations_do_not_invalidate_cache(self):
        patcher, calls = self._count_cache_clears()
        with patcher:
            self.assertFalse(self.Menu.create([]))
            self.assertTrue(self.Menu.browse().write({"name": "x"}))
            self.assertTrue(self.Menu.browse().unlink())
        self.assertEqual(calls, [])

    def test_web_icon_data_built_icon(self):
        menu3 = self.Menu.create(
            {"name": "Built 3", "web_icon": "fa fa-cog,#000000,#ffffff"}
        )
        self.assertFalse(menu3.web_icon_data)

        menu2 = self.Menu.create({"name": "Built 2", "web_icon": "fa fa-cog,#000000"})
        self.assertFalse(menu2.web_icon_data)

    def test_web_icon_data_image_icon(self):
        menu = self.Menu.create(
            {"name": "Image icon", "web_icon": "base,static/img/main_partner-image.png"}
        )
        self.assertTrue(menu.web_icon_data)

    def test_read_image_malformed_path(self):
        self.assertFalse(self.Menu._read_image(""))
        self.assertFalse(self.Menu._read_image("only_one_part"))
        self.assertFalse(self.Menu._read_image("a,b,c"))


class TestMenuAccent(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Menu = self.env["ir.ui.menu"]

    def _assert_readable(self, menu):
        for scheme, surfaces in ACCENT_SURFACES.items():
            accent = hex_to_rgb(menu[f"web_accent_{scheme}"])
            for surface in surfaces:
                self.assertGreaterEqual(
                    contrast_ratio(accent, hex_to_rgb(surface)),
                    WCAG_AA_TEXT,
                    f"{menu.name}: {scheme} accent on {surface}",
                )

    def test_accent_is_read_from_the_icon_image(self):
        menu = self.Menu.create(
            {"name": "Settings", "web_icon": "base,static/description/settings.png"}
        )
        self.assertRegex(menu.web_accent, r"^#[0-9a-f]{6}$")
        self._assert_readable(menu)

    def test_a_built_icon_lends_its_background(self):
        menu = self.Menu.create(
            {"name": "Built", "web_icon": "fa fa-cog,#ffffff,#FCBA45"}
        )
        self.assertEqual(menu.web_accent, "#fcba45")
        self.assertEqual(
            menu.web_accent_dark, "#fcba45", "already readable on dark: unchanged"
        )
        self.assertNotEqual(menu.web_accent_light, "#fcba45")
        self._assert_readable(menu)

    def test_no_icon_no_accent(self):
        menu = self.Menu.create({"name": "Plain"})
        self.assertFalse(menu.web_accent)
        self.assertFalse(menu.web_accent_light)
        self.assertFalse(menu.web_accent_dark)

    def test_a_set_accent_wins_over_the_icon_and_follows_a_new_icon(self):
        menu = self.Menu.create(
            {
                "name": "Chosen",
                "web_icon": "fa fa-cog,#ffffff,#f06050",
                "web_accent": "#0071e3",
            }
        )
        self.assertEqual(menu.web_accent, "#0071e3")
        self._assert_readable(menu)
        menu.web_icon = "fa fa-cog,#ffffff,#1ad3bb"
        self.assertEqual(menu.web_accent, "#1ad3bb")

    def test_load_menus_carries_the_scheme_accents(self):
        action = self.env["ir.actions.act_window"].create(
            {"name": "Tinted", "res_model": "res.partner"}
        )
        menu = self.Menu.create(
            {
                "name": "Tinted",
                "web_icon": "fa fa-cog,#ffffff,#f06050",
                "action": f"{action._name},{action.id}",
            }
        )
        entry = self.Menu.load_menus(False)[menu.id]
        self.assertEqual(entry["web_accent_light"], menu.web_accent_light)
        self.assertEqual(entry["web_accent_dark"], menu.web_accent_dark)
