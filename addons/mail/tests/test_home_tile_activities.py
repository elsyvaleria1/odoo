from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("mail_activity", "post_install", "-at_install")
class TestHomeTileActivities(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="tile_activities", groups="base.group_user"
        )
        cls.partners = cls.env["res.partner"].create(
            [{"name": f"Customer {index}"} for index in range(4)]
        )

    def _schedule(self, partner, days):
        self.env["mail.activity"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": partner.id,
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "date_deadline": fields.Date.context_today(partner)
                + timedelta(days=days),
                "user_id": self.user.id,
            }
        )

    def test_a_new_user_starts_with_activities_before_recent_records(self):
        self.user.company_id.web_config_id.home_tiles_default = False
        settings = self.env["res.users.settings"]._get_or_create_for_user(self.user)
        self.assertEqual(
            [
                tile["type"]
                for tile in settings.with_user(self.user)._home_tiles_default()["tiles"]
            ],
            ["activities", "recent_records"],
        )

    def test_the_activities_tile_totals_the_users_buckets(self):
        self._schedule(self.partners[0], -2)
        self._schedule(self.partners[1], 0)
        self._schedule(self.partners[2], 0)
        self._schedule(self.partners[3], 3)
        tiles = self.env["home.tile"].with_user(self.user)
        self.assertIn("activities", tiles.get_tile_types())
        data = tiles.get_tiles([{"id": "activities_1", "type": "activities"}])[
            "activities_1"
        ]["data"]
        self.assertEqual((data["overdue"], data["today"], data["planned"]), (1, 2, 1))
        self.assertEqual(data["groups"][0]["model"], "res.partner")
        self.assertEqual(
            (data["groups"][0]["overdue"], data["groups"][0]["today"]), (1, 2)
        )
        self.assertLessEqual(
            {"activity_ids", "view_type", "is_todo"},
            set(data["groups"][0]),
            "the tile opens a group with what the systray opens it with",
        )

    def _tile_groups(self):
        return (
            self.env["home.tile"]
            .with_user(self.user)
            .get_tiles([{"id": "activities_1", "type": "activities"}])["activities_1"][
                "data"
            ]["groups"]
        )

    def test_two_buckets_of_one_model_stay_apart_in_the_activities_tile(self):
        self._schedule(self.partners[0], -1)
        self._schedule(self.partners[1], -1)
        split_off = self.partners[0].id
        Users = self.registry["res.users"]

        def subkeys(users, model_name, res_ids):
            return {split_off: "split"} if split_off in res_ids else {}

        def apply_subkey(users, group, model_name, subkey, res_ids):
            return {**group, "domain": [("id", "in", res_ids)]}

        with (
            patch.object(Users, "_activity_bucket_subkeys", subkeys),
            patch.object(Users, "_apply_activity_bucket_subkey", apply_subkey),
        ):
            groups = self._tile_groups()
        self.assertEqual(
            sorted((g["model"], g["subkey"], str(g["domain"])) for g in groups),
            [
                ("res.partner", "", str([("id", "in", [self.partners[1].id])])),
                ("res.partner", "split", str([("id", "in", [split_off])])),
            ],
        )

    def test_the_activities_tile_lists_only_activity_buckets(self):
        self._schedule(self.partners[0], 0)
        Users = self.registry["res.users"]
        get_groups = Users._get_activity_groups
        meeting = {
            "id": self.env["ir.model"]._get_id("res.partner"),
            "type": "meeting",
            "name": "Today's Meetings",
            "model": "res.partner",
            "icon": False,
            "domain": [],
        }

        def with_meeting(users):
            return [meeting, *get_groups(users)]

        with patch.object(Users, "_get_activity_groups", with_meeting):
            groups = self._tile_groups()
        self.assertEqual([g["name"] for g in groups], ["Contact"])

    def test_a_portal_user_is_not_offered_the_activities_tile(self):
        portal = new_test_user(
            self.env, login="tile_portal", groups="base.group_portal"
        )
        self.assertNotIn(
            "activities", self.env["home.tile"].with_user(portal).get_tile_types()
        )

    def test_the_activities_tile_keeps_its_statement_count(self):
        request = [{"id": "activities_1", "type": "activities"}]
        self.env["home.tile"].with_user(self.user).get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(6):
            self.env["home.tile"].with_user(self.user).get_tiles(request)
