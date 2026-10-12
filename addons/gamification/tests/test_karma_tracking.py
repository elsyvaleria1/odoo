from datetime import datetime
from itertools import chain, repeat
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time

from odoo import exceptions, fields
from odoo.tests import common

from odoo.addons.mail.tests.common import mail_new_test_user


class TestKarmaTrackingCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = mail_new_test_user(
            cls.env,
            login="test",
            name="Test User",
            email="test@example.com",
            karma=0,
            groups="base.group_user",
        )
        cls.test_user_2 = mail_new_test_user(
            cls.env,
            login="test2",
            name="Test User 2",
            email="test2@example.com",
            karma=0,
            groups="base.group_user",
        )
        cls.env["gamification.karma.tracking"].search([]).unlink()

        cls.test_date = datetime(2021, 6, 1)
        cls.first_day_of_test_date_month = "2021-06-01"
        cls.first_day_of_test_date_next_month = "2021-07-01"

    @classmethod
    def _create_trackings(cls, user, karma, steps, track_date, days_delta=1):
        old_value = user.karma
        for _step in range(steps):
            new_value = old_value + karma
            cls.env["gamification.karma.tracking"].create(
                [
                    {
                        "user_id": user.id,
                        "old_value": old_value,
                        "new_value": new_value,
                        "consolidated": False,
                        "tracking_date": fields.Datetime.to_string(track_date),
                    }
                ]
            )
            old_value = new_value
            track_date += relativedelta(days=days_delta)

    def test_computation_gain(self):
        self._create_trackings(self.test_user, 20, 2, self.test_date, days_delta=30)
        self._create_trackings(self.test_user_2, 10, 20, self.test_date, days_delta=2)

        results = (self.test_user | self.test_user_2)._get_tracking_karma_gain_position(
            []
        )
        self.assertEqual(results[0]["user_id"], self.test_user_2.id)
        self.assertEqual(results[0]["karma_gain_total"], 200)
        self.assertEqual(results[0]["karma_position"], 1)
        self.assertEqual(results[1]["user_id"], self.test_user.id)
        self.assertEqual(results[1]["karma_gain_total"], 40)
        self.assertEqual(results[1]["karma_position"], 2)

        results = (self.test_user | self.test_user_2)._get_tracking_karma_gain_position(
            [], to_date=self.test_date + relativedelta(day=2)
        )
        self.assertEqual(results[0]["user_id"], self.test_user.id)
        self.assertEqual(results[0]["karma_gain_total"], 20)
        self.assertEqual(results[0]["karma_position"], 1)
        self.assertEqual(results[1]["user_id"], self.test_user_2.id)
        self.assertEqual(results[1]["karma_gain_total"], 10)
        self.assertEqual(results[1]["karma_position"], 2)

        results = (self.test_user | self.test_user_2)._get_tracking_karma_gain_position(
            [], from_date=self.test_date + relativedelta(months=1, day=1)
        )
        self.assertEqual(results[0]["user_id"], self.test_user_2.id)
        self.assertEqual(results[0]["karma_gain_total"], 50)
        self.assertEqual(results[0]["karma_position"], 1)
        self.assertEqual(results[1]["user_id"], self.test_user.id)
        self.assertEqual(results[1]["karma_gain_total"], 20)
        self.assertEqual(results[1]["karma_position"], 2)

        results = self.env["res.users"]._get_tracking_karma_gain_position([])
        self.assertEqual(len(results), 0)

    @freeze_time("2021-02-02")
    def test_consolidation_cron(self):
        Tracking = self.env["gamification.karma.tracking"]

        self.assertFalse(
            Tracking.search_count(
                [("user_id", "in", (self.test_user | self.test_user_2).ids)]
            )
        )

        test_date = datetime(2020, 12, 15)
        first_day_of_test_date_month = "2020-12-01"
        first_day_of_test_date_next_month = "2021-01-01"

        self._create_trackings(
            self.test_user, karma=20, steps=2, track_date=test_date, days_delta=30
        )
        self._create_trackings(
            self.test_user_2, karma=10, steps=20, track_date=test_date, days_delta=2
        )

        self.assertEqual(
            Tracking.search_count([("user_id", "=", self.test_user.id)]), 2
        )
        self.assertEqual(
            Tracking.search_count([("user_id", "=", self.test_user_2.id)]), 20
        )
        self.assertEqual(self.test_user.karma, 40)
        self.assertEqual(self.test_user_2.karma, 200)

        with (
            self.assertQueryCount(2),
            patch.object(self.registry["res.users"], "write") as patched_user_write,
        ):
            Tracking._consolidate_cron()

        self.assertFalse(
            patched_user_write.called,
            "User karma didn't change during consolidation, it should not be updated",
        )
        self.assertEqual(self.test_user.karma, 40)
        self.assertEqual(self.test_user_2.karma, 200)

        consolidated_1 = Tracking.search(
            [
                ("user_id", "=", self.test_user.id),
                ("tracking_date", ">=", first_day_of_test_date_month),
                ("tracking_date", "<", first_day_of_test_date_next_month),
            ]
        )
        self.assertEqual(len(consolidated_1), 1)
        self.assertTrue(consolidated_1.consolidated)
        self.assertEqual(consolidated_1.old_value, 0)
        self.assertEqual(consolidated_1.new_value, 20)
        self.assertEqual(
            consolidated_1.reason, "Consolidation from 2020-12-01 to 2020-12-31"
        )

        consolidated_2 = Tracking.search(
            [
                ("user_id", "=", self.test_user_2.id),
                ("tracking_date", ">=", first_day_of_test_date_month),
                ("tracking_date", "<", first_day_of_test_date_next_month),
            ]
        )
        self.assertEqual(len(consolidated_2), 1)
        self.assertTrue(consolidated_2.consolidated)
        self.assertEqual(consolidated_2.old_value, 0)
        self.assertEqual(consolidated_2.new_value, 10 * 9)
        self.assertEqual(
            consolidated_2.reason, "Consolidation from 2020-12-01 to 2020-12-31"
        )

        unconsolidated_1 = Tracking.search_count(
            [
                ("user_id", "=", self.test_user.id),
                ("consolidated", "=", False),
            ]
        )
        self.assertEqual(unconsolidated_1, 1)

        unconsolidated_2 = Tracking.search_count(
            [
                ("user_id", "=", self.test_user_2.id),
                ("consolidated", "=", False),
            ]
        )
        self.assertEqual(unconsolidated_2, 11)

    def test_consolidation_monthly(self):
        Tracking = self.env["gamification.karma.tracking"]
        base_test_user_karma = self.test_user.karma
        base_test_user_2_karma = self.test_user_2.karma
        self._create_trackings(self.test_user, 20, 2, self.test_date, days_delta=30)
        self._create_trackings(self.test_user_2, 10, 20, self.test_date, days_delta=2)

        Tracking._process_consolidate(self.test_date)
        consolidated = Tracking.search(
            [
                ("user_id", "=", self.test_user_2.id),
                ("tracking_date", ">=", self.first_day_of_test_date_month),
                ("tracking_date", "<", self.first_day_of_test_date_next_month),
            ]
        )
        self.assertEqual(len(consolidated), 1)
        self.assertTrue(consolidated.consolidated)
        self.assertEqual(consolidated.old_value, base_test_user_2_karma)
        self.assertEqual(consolidated.new_value, base_test_user_2_karma + 150)

        remaining = Tracking.search(
            [("user_id", "=", self.test_user_2.id), ("consolidated", "=", False)]
        )
        self.assertEqual(len(remaining), 5)
        self.assertEqual(
            remaining[0].tracking_date, self.test_date + relativedelta(months=1, day=9)
        )
        self.assertEqual(
            remaining[-1].tracking_date, self.test_date + relativedelta(months=1, day=1)
        )

        Tracking._process_consolidate(self.test_date + relativedelta(months=1))
        consolidated = Tracking.search(
            [
                ("user_id", "=", self.test_user_2.id),
                ("consolidated", "=", True),
            ]
        )
        self.assertEqual(len(consolidated), 2)
        self.assertEqual(consolidated[0].new_value, base_test_user_2_karma + 200)
        self.assertEqual(consolidated[0].old_value, base_test_user_2_karma + 150)
        self.assertEqual(
            consolidated[0].tracking_date.date(),
            self.test_date.date() + relativedelta(months=1),
        )
        self.assertEqual(consolidated[-1].new_value, base_test_user_2_karma + 150)
        self.assertEqual(consolidated[-1].old_value, base_test_user_2_karma)

        remaining = Tracking.search(
            [("user_id", "=", self.test_user_2.id), ("consolidated", "=", False)]
        )
        self.assertFalse(remaining)

        current_user_trackings = Tracking.search(
            [
                ("user_id", "=", self.test_user.id),
            ]
        )
        self.assertEqual(len(current_user_trackings), 2)
        self.assertEqual(current_user_trackings[0].new_value, base_test_user_karma + 40)
        self.assertEqual(current_user_trackings[-1].old_value, base_test_user_karma)

    def test_consolidation_preserves_origin_ref_model_name(self):
        Tracking = self.env["gamification.karma.tracking"]
        self._create_trackings(self.test_user, 20, 5, self.test_date, days_delta=3)

        Tracking._process_consolidate(self.test_date)

        consolidated = Tracking.search(
            [
                ("user_id", "=", self.test_user.id),
                ("consolidated", "=", True),
            ]
        )
        self.assertEqual(len(consolidated), 1)
        self.assertEqual(
            consolidated.origin_ref_model_name,
            "res.users",
            "Consolidated record should have origin_ref_model_name set",
        )

    def test_user_as_erp_manager(self):
        self.test_user.write(
            {
                "group_ids": [
                    (4, self.env.ref("base.group_partner_manager").id),
                    (4, self.env.ref("base.group_erp_manager").id),
                ]
            }
        )
        user = (
            self.env["res.users"]
            .with_user(self.test_user)
            .create(
                {
                    "name": "Test Ostérone",
                    "karma": "32",
                    "login": "dummy",
                    "email": "dummy@example.com",
                }
            )
        )
        with self.assertRaises(exceptions.AccessError):
            user.read(["karma_tracking_ids"])

        user._add_karma(38, source=self.test_user_2)
        self.assertEqual(user.karma, 70)
        trackings = (
            self.env["gamification.karma.tracking"]
            .sudo()
            .search([("user_id", "=", user.id)], order="create_date ASC, id ASC")
        )
        self.assertEqual(len(trackings), 2)
        self.assertEqual(trackings[0].origin_ref, self.test_user)
        self.assertIn(self.env._("User Creation"), trackings[0].reason)
        self.assertIn(str(self.test_user.id), trackings[0].reason)
        self.assertEqual(trackings[1].origin_ref, self.test_user_2)
        self.assertIn(self.env._("Add Manually"), trackings[1].reason)
        self.assertIn(self.test_user_2.display_name, trackings[1].reason)
        self.assertIn(str(self.test_user_2.id), trackings[1].reason)

    def test_user_tracking(self):
        self.test_user.write(
            {
                "group_ids": [
                    (4, self.env.ref("base.group_partner_manager").id),
                    (4, self.env.ref("base.group_system").id),
                ]
            }
        )
        user = (
            self.env["res.users"]
            .with_user(self.test_user)
            .create(
                {
                    "name": "Test Ostérone",
                    "karma": "32",
                    "login": "dummy",
                    "email": "dummy@example.com",
                }
            )
        )
        self.assertEqual(user.karma, 32)
        self.assertEqual(len(user.karma_tracking_ids), 1)
        self.assertEqual(user.karma_tracking_ids.old_value, 0)
        self.assertEqual(user.karma_tracking_ids.new_value, 32)

        user._add_karma(38)
        self.assertEqual(user.karma, 70)
        self.assertEqual(len(user.karma_tracking_ids), 2)
        latest = user.karma_tracking_ids.sorted("id")[1]
        self.assertEqual(latest.old_value, 32)
        self.assertEqual(latest.new_value, 70)
        self.assertIn(self.env._("Add Manually"), latest.reason)
        self.assertIn(self.test_user.display_name, latest.reason)
        self.assertIn(str(self.test_user.id), latest.reason)
        self.assertEqual(user.karma_tracking_ids.sorted("id")[0].old_value, 0)
        self.assertEqual(user.karma_tracking_ids.sorted("id")[0].new_value, 32)

        user._add_karma(69, user, self.env._("Test Reason"))
        self.assertEqual(len(user.karma_tracking_ids), 3)
        self.assertIn(
            self.env._("Test Reason"), user.karma_tracking_ids.sorted("id")[2].reason
        )
        self.assertEqual(user.karma, 139)

        tracking = self.env["gamification.karma.tracking"].create(
            {
                "user_id": user.id,
                "new_value": 150,
                "consolidated": False,
            }
        )
        self.assertEqual(tracking.old_value, 139)
        self.assertEqual(tracking.gain, 11)
        self.assertEqual(user.karma, 150)

        self.test_user_2.karma = 100
        last_tracking_3 = self.test_user_2.karma_tracking_ids.sorted("id")[-1]

        users = (user | self.test_user | self.test_user_2).with_user(self.test_user)
        with self.assertQueryCount(23):
            users.karma = 100

        tracking_1 = user.karma_tracking_ids.sorted("id")[-1]
        tracking_2 = self.test_user.karma_tracking_ids.sorted("id")[-1]
        tracking_3 = self.test_user_2.karma_tracking_ids.sorted("id")[-1]

        self.assertEqual(user.karma, 100)
        self.assertEqual(self.test_user.karma, 100)
        self.assertEqual(tracking_1.new_value, 100)
        self.assertEqual(tracking_1.old_value, 150)
        self.assertEqual(tracking_1.gain, -50)
        self.assertIn(self.env._("Add Manually"), tracking_1.reason)
        self.assertIn(str(self.test_user.id), tracking_1.reason)
        self.assertEqual(tracking_1.origin_ref, self.test_user)
        self.assertEqual(tracking_2.new_value, 100)
        self.assertEqual(tracking_2.old_value, 0)
        self.assertEqual(tracking_2.gain, 100)
        self.assertIn(self.env._("Add Manually"), tracking_2.reason)
        self.assertIn(str(self.test_user.id), tracking_2.reason)
        self.assertEqual(tracking_2.origin_ref, self.test_user)
        self.assertEqual(
            last_tracking_3,
            tracking_3,
            "Shouldn't have created a new tracking for the third user",
        )
        self.assertEqual(tracking_3.new_value, 100)
        self.assertEqual(tracking_3.old_value, 0)
        self.assertEqual(tracking_3.gain, 100)


class TestComputeRankCommon(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def _patched_send_mail(*args, **kwargs):
            pass

        patch_email = patch(
            "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
            _patched_send_mail,
        )
        cls.startClassPatcher(patch_email)

        cls.users = cls.env["res.users"]
        for k in range(-5, 1030, 30):
            cls.users += mail_new_test_user(
                cls.env,
                name=str(k),
                login="test_recompute_rank_%s" % k,
                karma=k,
            )

        cls.env["gamification.karma.rank"].search([]).unlink()

        cls.rank_1 = cls.env["gamification.karma.rank"].create(
            {
                "name": "rank 1",
                "karma_min": 1,
            }
        )

        cls.rank_2 = cls.env["gamification.karma.rank"].create(
            {
                "name": "rank 2",
                "karma_min": 250,
            }
        )

        cls.rank_3 = cls.env["gamification.karma.rank"].create(
            {
                "name": "rank 3",
                "karma_min": 500,
            }
        )
        cls.rank_4 = cls.env["gamification.karma.rank"].create(
            {
                "name": "rank 4",
                "karma_min": 1000,
            }
        )

    def test_00_initial_compute(self):

        self.assertEqual(len(self.users), 35)

        self.assertEqual(
            len(self.rank_1.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_1.karma_min
                    and u.karma < self.rank_2.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_2.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_2.karma_min
                    and u.karma < self.rank_3.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_3.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_3.karma_min
                    and u.karma < self.rank_4.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_4.user_ids & self.users),
            len([u for u in self.users if u.karma >= self.rank_4.karma_min]),
        )

    def test_01_switch_rank(self):

        self.assertEqual(len(self.users), 35)

        self.rank_3.karma_min = 100

        self.assertEqual(
            len(self.rank_1.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_1.karma_min
                    and u.karma < self.rank_3.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_3.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_3.karma_min
                    and u.karma < self.rank_2.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_2.user_ids & self.users),
            len(
                [
                    u
                    for u in self.users
                    if u.karma >= self.rank_2.karma_min
                    and u.karma < self.rank_4.karma_min
                ]
            ),
        )
        self.assertEqual(
            len(self.rank_4.user_ids & self.users),
            len([u for u in self.users if u.karma >= self.rank_4.karma_min]),
        )

    def test_02_update_rank_without_switch(self):
        number_of_users = False

        def _patched_recompute_rank(_self, *args, **kwargs):
            nonlocal number_of_users
            number_of_users = len(_self & self.users)

        patch_bulk = patch(
            "odoo.addons.gamification.models.res_users.ResUsers._recompute_rank",
            _patched_recompute_rank,
        )
        self.startPatcher(patch_bulk)
        self.rank_3.karma_min = 700
        self.assertEqual(
            number_of_users,
            7,
            "Should just recompute for the 7 users between 500 and 700",
        )

    def test_03_reranking_writes_once_per_rank_not_once_per_user(self):
        self.assertEqual(len(self.users), 35)
        self.users.sudo().write({"rank_id": False, "next_rank_id": False})
        self.env.flush_all()

        calls = []
        real_write = type(self.env["res.users"]).write

        def counting_write(records, vals):
            if "rank_id" in vals:
                calls.append(len(records))
            return real_write(records, vals)

        self.patch(type(self.env["res.users"]), "write", counting_write)
        self.users._recompute_rank()

        ranks = self.env["gamification.karma.rank"].search_count([])
        self.assertTrue(calls, "re-ranking wrote nothing at all")
        self.assertLessEqual(
            len(calls),
            ranks + 1,
            f"re-ranking 35 users made {len(calls)} rank writes over {ranks} "
            f"ranks; it should group them, not write per user",
        )
        self.assertEqual(
            sum(calls),
            len(self.users),
            "every user must still be written exactly once",
        )

    def test_get_next_rank(self):
        for user, expected_next_rank in chain(
            ((self.users[0], self.rank_1),),
            zip(self.users[1:8], repeat(self.rank_2)),
            zip(self.users[9:16], repeat(self.rank_3)),
            zip(self.users[17:33], repeat(self.rank_4)),
            ((self.users[34], self.env["gamification.karma.rank"]),),
        ):
            user.next_rank_id = False
            self.assertEqual(user._get_next_rank(), expected_next_rank)


class TestKarmaRankTieBreak(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        def _patched_send_mail(*args, **kwargs):
            pass

        cls.startClassPatcher(
            patch(
                "odoo.addons.mail.models.mail_template.MailTemplate.send_mail",
                _patched_send_mail,
            )
        )
        cls.env["gamification.karma.rank"].search([]).unlink()
        cls.rank_low_id = cls.env["gamification.karma.rank"].create(
            {"name": "Tied A (low id)", "karma_min": 100}
        )
        cls.rank_high_id = cls.env["gamification.karma.rank"].create(
            {"name": "Tied B (high id)", "karma_min": 100}
        )

    def test_tied_karma_min_orders_by_id(self):
        ranks = self.env["gamification.karma.rank"].search(
            [("id", "in", (self.rank_low_id | self.rank_high_id).ids)],
            order="karma_min DESC, id",
        )
        self.assertEqual(
            ranks.ids,
            [self.rank_low_id.id, self.rank_high_id.id],
            "on a karma_min tie, the lowest id must sort first",
        )

    def test_recompute_rank_assigns_deterministically_on_tie(self):
        user = mail_new_test_user(
            self.env,
            login="tie_user",
            name="Tie User",
            karma=0,
            groups="base.group_user",
        )
        user.karma = 100
        assigned = []
        for _i in range(3):
            user.rank_id = False
            user.next_rank_id = False
            user._recompute_rank()
            assigned.append(user.rank_id.id)
        self.assertEqual(
            assigned,
            [self.rank_low_id.id] * 3,
            "rank assignment on a karma_min tie must be deterministic across calls",
        )
