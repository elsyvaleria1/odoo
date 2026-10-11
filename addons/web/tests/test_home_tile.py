import re
from pathlib import Path
from unittest.mock import patch

from odoo import Command, api
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools.misc import file_path


@tagged("web_unit", "web_users")
class TestHomeTile(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="tile_user", groups="base.group_user")
        cls.other = new_test_user(cls.env, login="tile_other", groups="base.group_user")
        cls.partners = cls.env["res.partner"].create(
            [{"name": "First"}, {"name": "Second"}, {"name": "Third"}]
        )
        cls.user.company_id.web_config_id.home_tiles_default = {
            "version": 1,
            "tiles": [],
        }
        cls.tiles = cls.env["home.tile"].with_user(cls.user)
        cls.recent = cls.env["web.recent.record"].with_user(cls.user)
        cls.settings = (
            cls.env["res.users.settings"]
            ._get_or_create_for_user(cls.user)
            .with_user(cls.user)
        )

    def _open(self, *partners, user=None):
        recent = self.env["web.recent.record"].with_user(user or self.user)
        recent.note_opened(
            [{"res_model": "res.partner", "res_id": partner.id} for partner in partners]
        )

    def test_a_tile_request_returns_each_tile_by_its_id(self):
        self._open(self.partners[0])
        result = self.tiles.get_tiles(
            [
                {"id": "recent_records_1", "type": "recent_records"},
                {"id": "gone_1", "type": "no_such_type"},
            ]
        )
        self.assertEqual(result["gone_1"], {"error": "unavailable"})
        records = result["recent_records_1"]["data"]["records"]
        self.assertEqual(
            [(r["res_model"], r["res_id"]) for r in records],
            [("res.partner", self.partners[0].id)],
        )
        self.assertEqual(records[0]["display_name"], "First")

    def test_a_failing_tile_is_isolated_and_access_errors_are_not(self):
        with (
            patch.object(
                type(self.tiles),
                "_get_tile_recent_records_data",
                side_effect=ZeroDivisionError,
            ),
            self.assertLogs("odoo.addons.web.models.home_tile", "ERROR"),
        ):
            result = self.tiles.get_tiles(
                [{"id": "recent_records_1", "type": "recent_records"}]
            )
        self.assertEqual(result, {"recent_records_1": {"error": "failed"}})

    def test_a_tile_the_user_may_not_read_is_unavailable_and_the_others_render(self):
        with patch.object(
            type(self.tiles),
            "_get_tile_recent_records_data",
            side_effect=AccessError("no"),
        ):
            result = self.tiles.get_tiles(
                [
                    {"id": "recent_records_1", "type": "recent_records"},
                    {"id": "metric_1", "type": "metric"},
                ]
            )
        self.assertEqual(
            result,
            {
                "recent_records_1": {"error": "unavailable"},
                "metric_1": {"data": {"configured": False}},
            },
        )

    def test_a_tile_out_of_reach_for_now_survives_other_changes(self):
        self.settings.update_home_tiles(
            [
                {"operation": "add", "type": "recent_records"},
                {"operation": "add", "type": "metric"},
            ]
        )
        may_use = type(self.tiles)._may_use
        with patch.object(
            type(self.tiles),
            "_may_use",
            lambda tiles, spec: (
                spec.get("model") != "ir.filters" and may_use(tiles, spec)
            ),
        ):
            self.settings.update_home_tiles(
                [
                    {"operation": "background", "value": "teal"},
                    {"operation": "resize", "id": "metric_1", "size": "2x1"},
                ]
            )
        self.assertEqual(
            [(tile["id"], tile["size"]) for tile in self.settings.home_tiles["tiles"]],
            [("recent_records_1", "1x1"), ("metric_1", "2x1")],
        )

    def test_the_dashboard_reads_on_a_read_only_cursor(self):
        for method in ("get_tile_types", "get_tiles"):
            with self.subTest(method=method):
                self.assertTrue(api.is_readonly(type(self.tiles), method))

    def test_malformed_tile_requests_are_refused(self):
        for requests in (
            {},
            [None],
            [{"id": "has space", "type": "recent_records"}],
            [{"id": "tile_1", "type": ["recent_records"]}],
            [{"id": f"tile_{index}", "type": "recent_records"} for index in range(51)],
        ):
            with self.subTest(requests=requests), self.assertRaises(ValidationError):
                self.tiles.get_tiles(requests)

    def test_a_tile_type_reading_an_unreadable_model_is_unavailable(self):
        original = type(self.tiles)._get_tile_types

        def with_gated(model):
            types = original(model)
            types["recent_records"] = {
                **types["recent_records"],
                "model": "ir.config_parameter",
            }
            return types

        with patch.object(type(self.tiles), "_get_tile_types", with_gated):
            self.assertNotIn("recent_records", self.tiles.get_tile_types())
            result = self.tiles.get_tiles(
                [{"id": "recent_records_1", "type": "recent_records"}]
            )
        self.assertEqual(result["recent_records_1"], {"error": "unavailable"})

    def test_a_tile_whose_menu_sits_under_a_closed_parent_is_unavailable(self):
        Menu = self.env["ir.ui.menu"]
        action = self.env["ir.actions.act_window"].create(
            {"name": "Tile screen", "res_model": "res.partner"}
        )
        parent = Menu.create(
            {
                "name": "Administrators only",
                "group_ids": [Command.set(self.env.ref("base.group_system").ids)],
            }
        )
        menu = Menu.create(
            {
                "name": "Tile screen",
                "parent_id": parent.id,
                "action": f"{action._name},{action.id}",
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "web",
                "name": "test_tile_screen_menu",
                "model": "ir.ui.menu",
                "res_id": menu.id,
            }
        )
        original = type(self.tiles)._get_tile_types

        def with_menu(model):
            types = original(model)
            types["recent_records"] = {
                **types["recent_records"],
                "menu": "web.test_tile_screen_menu",
            }
            return types

        with patch.object(type(self.tiles), "_get_tile_types", with_menu):
            self.assertNotIn(menu.id, Menu.with_user(self.user).load_menus(False))
            self.assertNotIn("recent_records", self.tiles.get_tile_types())

            parent.group_ids = False
            self.assertIn(menu.id, Menu.with_user(self.user).load_menus(False))
            self.assertIn("recent_records", self.tiles.get_tile_types())

    def test_the_dashboard_offers_nothing_outside_the_backend(self):
        portal = new_test_user(
            self.env, login="tile_portal", groups="base.group_portal"
        )
        tiles = self.env["home.tile"].with_user(portal)
        self.assertEqual(tiles.get_tile_types(), {})
        self.assertEqual(
            tiles.get_tiles([{"id": "recent_records_1", "type": "recent_records"}]),
            {"recent_records_1": {"error": "unavailable"}},
        )

    def test_opening_a_record_again_moves_it_first_and_counts_it(self):
        self._open(self.partners[0])
        self._open(self.partners[1])
        self._open(self.partners[0])
        rows = self.recent.search([])
        self.assertEqual(
            rows.mapped("res_id"), [self.partners[0].id, self.partners[1].id]
        )
        self.assertEqual(rows.mapped("count"), [2, 1])

    def test_only_existing_readable_records_are_noted_and_listed(self):
        self._open(self.partners[0], self.partners[1])
        self.partners[1].unlink()
        self.assertEqual(
            [r["res_id"] for r in self.recent._get_recent(10)], [self.partners[0].id]
        )
        self._open(self.partners[1])
        self.assertEqual(len(self.recent.search([])), 2)

    def test_malformed_openings_are_refused(self):
        for entries in (
            {},
            [None],
            [{"res_model": "no.such.model", "res_id": 1}],
            [{"res_model": "res.partner", "res_id": 0}],
            [{"res_model": "res.partner", "res_id": True}],
            [{"res_model": "res.partner", "res_id": "1"}],
        ):
            with self.subTest(entries=entries), self.assertRaises(ValidationError):
                self.recent.note_opened(entries)

    def test_a_user_sees_only_their_own_recent_records(self):
        self._open(self.partners[0])
        self._open(self.partners[2], user=self.other)
        self.assertEqual(self.recent.search([]).mapped("res_id"), [self.partners[0].id])
        self.assertEqual(
            [r["res_id"] for r in self.recent._get_recent(10)], [self.partners[0].id]
        )

    def test_the_vacuum_keeps_the_most_recent_per_user(self):
        Recent = self.env["web.recent.record"]
        Recent.create(
            [
                {
                    "user_id": self.user.id,
                    "res_model": "res.partner",
                    "res_id": index,
                    "recency": index,
                }
                for index in range(1, Recent._KEPT_PER_USER + 3)
            ]
        )
        Recent._gc_keep_the_most_recent_per_user()
        kept = Recent.search([("user_id", "=", self.user.id)])
        self.assertEqual(len(kept), Recent._KEPT_PER_USER)
        self.assertNotIn(1, kept.mapped("res_id"))

    def test_a_dashboard_is_arranged_by_changes(self):
        result = self.settings.update_home_tiles(
            [
                {"operation": "add", "type": "recent_records"},
                {"operation": "add", "type": "recent_records", "size": "2x1"},
            ]
        )
        self.assertEqual(
            result["home_tiles"]["tiles"],
            [
                {"id": "recent_records_1", "type": "recent_records", "size": "1x1"},
                {"id": "recent_records_2", "type": "recent_records", "size": "2x1"},
            ],
        )
        self.settings.update_home_tiles(
            [
                {"operation": "move", "id": "recent_records_2", "index": 0},
                {"operation": "resize", "id": "recent_records_1", "size": "2x1"},
                {"operation": "remove", "id": "recent_records_2"},
            ]
        )
        self.assertEqual(
            self.settings.home_tiles["tiles"],
            [{"id": "recent_records_1", "type": "recent_records", "size": "2x1"}],
        )

    def test_invalid_or_foreign_dashboard_changes_are_refused(self):
        with self.assertRaises(AccessError):
            self.env["res.users.settings"]._get_or_create_for_user(
                self.other
            ).with_user(self.user).update_home_tiles([])
        for changes in (
            {},
            [None],
            [{"operation": "add", "type": "no_such_type"}],
            [{"operation": "add", "type": "recent_records", "size": "9x9"}],
            [{"operation": "remove", "id": "recent_records_1"}],
            [{"operation": "add", "type": ["recent_records"]}],
            [{"operation": "remove", "id": ["recent_records_1"]}],
            [{"operation": "unknown"}],
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.settings.update_home_tiles(changes)

    def test_generic_settings_writer_cannot_store_a_dashboard(self):
        self.settings.set_res_users_settings(
            {"home_tiles": {"tiles": [{"id": "x", "type": "recent_records"}]}}
        )
        self.assertFalse(self.settings.home_tiles)

    def test_a_stored_dashboard_drops_what_it_cannot_show(self):
        normalized = self.settings._normalize_home_tiles(
            {
                "tiles": [
                    {"id": "recent_records_1", "type": "recent_records", "size": "9x9"},
                    {"id": "recent_records_1", "type": "recent_records"},
                    {"id": "gone_1", "type": "uninstalled_type"},
                    {"id": "listed_1", "type": ["recent_records"]},
                    "junk",
                ]
            }
        )
        self.assertEqual(
            normalized["tiles"],
            [{"id": "recent_records_1", "type": "recent_records", "size": "1x1"}],
        )

    def _favourite(self, name, domain, **values):
        return self.env["ir.filters"].create(
            {
                "name": name,
                "model_id": "res.partner",
                "domain": repr(domain),
                "user_ids": [(6, 0, self.user.ids)],
                **values,
            }
        )

    def _metric(self, **settings):
        return self.tiles.get_tiles(
            [{"id": "metric_1", "type": "metric", "settings": settings}]
        )["metric_1"]

    def test_a_metric_counts_or_sums_what_a_favourite_selects(self):
        self.partners[0].partner_latitude = 1.5
        self.partners[1].partner_latitude = 2.0
        favourite = self._favourite(
            "Numbered", [("name", "in", ["First", "Second", "Third"])]
        )
        counted = self._metric(filter_id=favourite.id)["data"]
        self.assertEqual(
            (counted["configured"], counted["value"], counted["model"]),
            (True, 3, "res.partner"),
        )
        self.assertEqual(len(counted["spark"]), self.tiles._METRIC_WEEKS)
        self.assertEqual(counted["spark"][-1], 3)
        self.assertEqual(sum(counted["spark"]), 3)
        summed = self._metric(filter_id=favourite.id, measure="partner_latitude")
        self.assertEqual(summed["data"]["value"], 3.5)

    def test_a_favourite_over_the_current_user_is_a_metric(self):
        self.partners[0].user_id = self.user
        favourite = self.env["ir.filters"].create(
            {
                "name": "Mine",
                "model_id": "res.partner",
                "domain": '[("user_id", "=", uid)]',
                "user_ids": [(6, 0, self.user.ids)],
            }
        )
        self.assertIn(favourite.id, [c["id"] for c in self.tiles.get_metric_choices()])
        self.assertEqual(self._metric(filter_id=favourite.id)["data"]["value"], 1)

    def test_an_unconfigured_metric_asks_for_a_favourite(self):
        self.assertEqual(self._metric(), {"data": {"configured": False}})

    def test_a_metric_over_a_favourite_or_field_it_cannot_read_is_unavailable(self):
        private = self._favourite("Theirs", [], user_ids=[(6, 0, self.other.ids)])
        mine = self._favourite("Mine", [])
        for settings in (
            {"filter_id": private.id},
            {"filter_id": mine.id, "measure": "name"},
            {"filter_id": mine.id, "measure": "no_such_field"},
            {"filter_id": 10**9},
        ):
            with self.subTest(settings=settings):
                self.assertEqual(self._metric(**settings), {"error": "unavailable"})

    def test_a_metric_tile_is_configured_through_the_dashboard(self):
        favourite = self._favourite("Mine", [])
        self.settings.update_home_tiles([{"operation": "add", "type": "metric"}])
        self.settings.update_home_tiles(
            [
                {
                    "operation": "configure",
                    "id": "metric_1",
                    "settings": {
                        "filter_id": favourite.id,
                        "measure": "partner_latitude",
                    },
                }
            ]
        )
        self.assertEqual(
            self.settings.home_tiles["tiles"],
            [
                {
                    "id": "metric_1",
                    "type": "metric",
                    "size": "1x1",
                    "settings": {
                        "filter_id": favourite.id,
                        "measure": "partner_latitude",
                    },
                }
            ],
        )
        for settings in (
            "junk",
            {"filter_id": "1"},
            {"filter_id": favourite.id, "measure": "bad name"},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValidationError):
                self.settings.update_home_tiles(
                    [{"operation": "configure", "id": "metric_1", "settings": settings}]
                )

    def test_metric_choices_list_readable_favourites_with_their_measures(self):
        mine = self._favourite("Mine", [])
        self._favourite("Theirs", [], user_ids=[(6, 0, self.other.ids)])
        choices = {choice["id"]: choice for choice in self.tiles.get_metric_choices()}
        self.assertIn(mine.id, choices)
        self.assertNotIn("Theirs", [choice["name"] for choice in choices.values()])
        measures = [measure["name"] for measure in choices[mine.id]["measures"]]
        self.assertEqual(measures[0], "__count")
        self.assertIn("partner_latitude", measures)
        self.assertNotIn("name", measures)

    def _company_default(self, *tiles):
        self.user.company_id.web_config_id.home_tiles_default = {
            "version": 1,
            "tiles": list(tiles),
        }

    def test_with_no_layout_anywhere_a_user_starts_from_the_starter_tiles(self):
        self.user.company_id.web_config_id.home_tiles_default = False
        usable = self.tiles.get_tile_types()
        self.assertEqual(
            self.settings._home_tiles_default()["tiles"],
            [
                tile
                for tile in self.tiles._get_starter_tiles()
                if tile["type"] in usable
            ],
        )
        self.assertIn(
            {"id": "recent_records_1", "type": "recent_records", "size": "2x1"},
            self.settings._home_tiles_default()["tiles"],
        )

    def test_a_user_without_tiles_of_their_own_follows_the_company(self):
        self._company_default(
            {"id": "recent_records_1", "type": "recent_records", "size": "2x1"}
        )
        self.assertEqual(
            self.settings._home_tiles_default()["tiles"],
            [{"id": "recent_records_1", "type": "recent_records", "size": "2x1"}],
        )
        self.settings.update_home_tiles([{"operation": "add", "type": "metric"}])
        self.assertEqual(
            [tile["id"] for tile in self.settings.home_tiles["tiles"]],
            ["recent_records_1", "metric_1"],
        )
        result = self.settings.update_home_tiles([{"operation": "reset"}])
        self.assertFalse(result["home_tiles"])
        self.assertFalse(self.settings.home_tiles)

    def test_a_reset_followed_by_changes_forks_the_company_layout_again(self):
        self._company_default(
            {"id": "recent_records_1", "type": "recent_records", "size": "1x1"}
        )
        self.settings.update_home_tiles([{"operation": "add", "type": "metric"}])
        self.settings.update_home_tiles(
            [
                {"operation": "reset"},
                {"operation": "resize", "id": "recent_records_1", "size": "2x1"},
            ]
        )
        self.assertEqual(
            self.settings.home_tiles["tiles"],
            [{"id": "recent_records_1", "type": "recent_records", "size": "2x1"}],
        )

    def test_only_an_administrator_sets_the_company_tiles(self):
        tiles = {
            "version": 1,
            "tiles": [
                {"id": "recent_records_1", "type": "recent_records", "size": "1x1"}
            ],
        }
        with self.assertRaises(AccessError):
            self.env["web.config"].with_user(self.user).set_home_tiles_default(tiles)
        admin = new_test_user(
            self.env, login="tile_admin", groups="base.group_user,base.group_system"
        )
        stored = (
            self.env["web.config"]
            .with_user(admin)
            .with_company(admin.company_id)
            .set_home_tiles_default({**tiles, "junk": 1})
        )
        self.assertEqual(stored, tiles)
        self.assertEqual(admin.company_id.web_config_id.home_tiles_default, tiles)

    def test_every_tint_the_server_accepts_is_painted_by_the_stylesheet(self):
        scss = Path(
            file_path("web/static/src/webclient/home_menu/home_menu.variables.scss")
        ).read_text(encoding="utf-8")
        tint_map = scss.split("$o-home-menu-tints: (", 1)[1].split("\n);", 1)[0]
        painted = re.findall(r"^    (\w+): \($", tint_map, re.MULTILINE)
        self.assertEqual(painted, list(self.settings._home_tints()))

    def test_a_dashboard_carries_a_background_tint(self):
        self.settings.update_home_tiles([{"operation": "background", "value": "teal"}])
        self.assertEqual(self.settings.home_tiles["background"], "teal")
        self.settings.update_home_tiles([{"operation": "background", "value": None}])
        self.assertNotIn("background", self.settings.home_tiles)
        with self.assertRaises(ValidationError):
            self.settings.update_home_tiles(
                [{"operation": "background", "value": "url(evil)"}]
            )
        self.assertEqual(
            self.settings._normalize_home_tiles({"tiles": [], "background": "neon"}),
            {"version": 1, "tiles": []},
        )

    def test_a_reset_returns_to_the_company_background(self):
        self._company_default()
        self.user.company_id.web_config_id.home_tiles_default = {
            "version": 1,
            "tiles": [],
            "background": "rose",
        }
        self.settings.update_home_tiles([{"operation": "background", "value": "teal"}])
        self.assertEqual(self.settings.home_tiles["background"], "teal")
        self.settings.update_home_tiles([{"operation": "reset"}])
        self.assertFalse(self.settings.home_tiles)
        self.assertEqual(self.settings._home_tiles_default()["background"], "rose")

    def test_the_recent_records_tile_keeps_its_statement_count(self):
        request = [{"id": "recent_records_1", "type": "recent_records"}]
        self.tiles.get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(3):
            self.tiles.get_tiles(request)

    def test_the_metric_tile_keeps_its_statement_count(self):
        request = [{"id": "metric_1", "type": "metric"}]
        self.tiles.get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(2):
            self.tiles.get_tiles(request)
