from collections import defaultdict
from uuid import uuid4

from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged


@tagged("post_install", "-at_install", "web_perf", "web_menu")
class TestPerfSessionInfo(common.HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Test Company",
            }
        )
        cls.user = common.new_test_user(
            cls.env,
            "session",
            email="session@in.fo",
            tz="UTC",
            company_id=cls.company.id,
        )

    def setUp(self):
        super().setUp()
        self.uid = self.user

    def test_performance_session_info(self):
        self.authenticate(self.user.login, "info")

        self.env.registry.clear_all_caches()
        with self.assertQueryCount(122):
            self.url_open(
                "/web/session/get_session_info",
                data=json_dumps(
                    {"jsonrpc": "2.0", "method": "call", "id": str(uuid4())}
                ),
                headers={"Content-Type": "application/json"},
            )

        with self.assertQueryCount(32):
            self.url_open(
                "/web/session/get_session_info",
                data=json_dumps(
                    {"jsonrpc": "2.0", "method": "call", "id": str(uuid4())}
                ),
                headers={"Content-Type": "application/json"},
            )

    def test_load_web_menus_perf(self):
        self.env.registry.clear_all_caches()
        self.env.invalidate_all()
        with self.assertQueryCount(57):
            self.env["ir.ui.menu"].load_web_menus(False)

        self.env.invalidate_all()
        with self.assertQueryCount(1):
            self.env["ir.ui.menu"].load_web_menus(False)

    def test_load_menus_perf(self):
        self.env.registry.clear_all_caches()
        self.env.invalidate_all()
        with self.assertQueryCount(57):
            self.env["ir.ui.menu"].load_menus(False)

        self.env.invalidate_all()
        with self.assertQueryCount(1):
            self.env["ir.ui.menu"].load_menus(False)

    def _cold_visible_menu_statements(self):
        self.env.registry.clear_all_caches()
        self.env.invalidate_all()
        self.env.flush_all()
        count0 = self.cr.sql_statement_count
        self.env["ir.ui.menu"]._get_visible_menu_ids()
        return self.cr.sql_statement_count - count0

    def _add_menus_over_visible_action_kinds(self, count):
        Menu = self.env["ir.ui.menu"].sudo()
        visible_ids = self.env["ir.ui.menu"]._get_visible_menu_ids()
        actions = Menu.search(
            [("id", "in", list(visible_ids)), ("action", "!=", False)]
        ).mapped("action")
        window_model = next(
            action.res_model
            for action in actions
            if action._name == "ir.actions.act_window"
        )
        new_windows = (
            self.env["ir.actions.act_window"]
            .sudo()
            .create(
                [
                    {"name": f"Probe window {i}", "res_model": window_model}
                    for i in range(count)
                ]
            )
        )
        by_kind = defaultdict(list)
        for action in actions:
            by_kind[action._name].append(action)
        reused = [
            action for same_kind in by_kind.values() for action in same_kind[:count]
        ]
        parent = Menu.create({"name": "Probe root"})
        Menu.create(
            [
                {
                    "name": f"Probe menu {i}",
                    "parent_id": parent.id,
                    "action": f"{action._name},{action.id}",
                }
                for i, action in enumerate([*new_windows, *reused])
            ]
        )

    def test_visible_menu_ids(self):
        # the cold cost is one fetch per action kind plus the access decision
        # per target model, so its absolute value is the installed set's; what
        # this method owns is that it does not grow with menus or actions.
        # The probe reuses only the kinds of the user's visible menus: a kind
        # none of their menus carries costs its own fetch, a new kind, not growth.
        # The first cold call also settles state clear_all_caches leaves alone.
        self._cold_visible_menu_statements()
        baseline = self._cold_visible_menu_statements()
        self.assertGreater(baseline, 0)
        self._add_menus_over_visible_action_kinds(20)

        self.assertEqual(self._cold_visible_menu_statements(), baseline)

        self.env.invalidate_all()
        with self.assertQueryCount(0):
            self.env["ir.ui.menu"]._get_visible_menu_ids()
