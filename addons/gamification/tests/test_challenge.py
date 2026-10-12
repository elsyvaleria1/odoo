import datetime
from datetime import timedelta

from freezegun import freeze_time
from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

from odoo.addons.gamification.tests.common import TransactionCaseGamification
from odoo.addons.mail.tests.common import mail_new_test_user


class TestGamificationCommon(TransactionCaseGamification):
    def setUp(self):
        super().setUp()
        employees_group = self.env.ref("base.group_user")
        self.user_ids = employees_group.all_user_ids

        self.env.ref("gamification.challenge_base_discover")._update_all()
        self.robot = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "R2D2",
                    "login": "r2d2@odoo.com",
                    "email": "r2d2@odoo.com",
                    "group_ids": [(6, 0, [employees_group.id])],
                }
            )
        )
        self.badge_good_job = self.env.ref("gamification.badge_good_job")


class test_challenge(TestGamificationCommon):
    def test_00_join_challenge(self):
        challenge = self.env.ref("gamification.challenge_base_discover")
        self.assertGreaterEqual(
            len(challenge.user_ids),
            len(self.user_ids),
            "Not enough users in base challenge",
        )
        challenge._update_all()
        self.assertGreaterEqual(
            len(challenge.user_ids),
            len(self.user_ids) + 1,
            "These are not droids you are looking for",
        )

    def test_10_reach_challenge(self):
        Goals = self.env["gamification.goal"]
        challenge = self.env.ref("gamification.challenge_base_discover")

        challenge.state = "inprogress"
        self.assertEqual(
            challenge.state, "inprogress", "Challenge failed the change of state"
        )

        goal_ids = Goals.search(
            [("challenge_id", "=", challenge.id), ("state", "!=", "draft")]
        )
        self.assertEqual(
            len(goal_ids),
            len(challenge.line_ids) * len(challenge.user_ids.ids),
            "Incorrect number of goals generated, should be 1 goal per user, per challenge line",
        )

        demo = self.user_demo
        demo.tz = "Europe/Brussels"
        goal_ids = Goals.search(
            [
                ("user_id", "=", demo.id),
                (
                    "definition_id",
                    "=",
                    self.env.ref("gamification.definition_base_timezone").id,
                ),
            ]
        )

        goal_ids.update_goal()

        missed = goal_ids.filtered(lambda g: g.state != "reached")
        self.assertFalse(missed, "Not every goal was reached after changing timezone")

        all_goals = Goals.search([("challenge_id", "=", challenge.id)])
        demo_goals = all_goals.filtered(lambda g, demo=demo: g.user_id == demo)
        other_goals = all_goals - demo_goals
        demo_goals.write({"state": "reached", "current": 9999})
        other_goals.write({"state": "reached", "current": 0})

        badge_id = self.badge_good_job.id
        challenge.write({"reward_first_id": badge_id, "reward_second_id": badge_id})
        challenge.write({"state": "done"})

        badge_ids = self.env["gamification.badge.user"].search(
            [("badge_id", "=", badge_id), ("user_id", "=", demo.id)]
        )
        self.assertEqual(len(badge_ids), 1, "Demo user has not received the badge")

    @mute_logger("odoo.models.unlink", "odoo.addons.mail", "odoo.addons.auth_signup")
    def test_20_update_all_goals_filter(self):
        (
            portal_last_active_old,
            portal_last_active_recent,
            internal_last_active_old,
            internal_last_active_recent,
        ) = all_test_users = self.env["res.users"].create(
            [
                {
                    "name": f"{kind} {age} login",
                    "login": f"{kind}_{age}",
                    "email": f"{kind}_{age}",
                    "group_ids": [(6, 0, group_ids)],
                }
                for kind, group_ids in (
                    ("Portal", []),
                    ("Internal", [self.env.ref("base.group_user").id]),
                )
                for age in ("Old", "Recent")
            ]
        )

        challenge = self.env.ref("gamification.challenge_base_discover")
        challenge.write(
            {
                "state": "inprogress",
                "user_domain": False,
                "manual_user_ids": [(6, 0, all_test_users.ids)],
            }
        )

        challenge.user_ids.presence_ids.unlink()

        for user in (
            portal_last_active_old,
            portal_last_active_recent,
            internal_last_active_old,
            internal_last_active_recent,
        ):
            self.env["mail.presence"]._update_presence(user, 20 * 60 * 1000)

        all_test_users.partner_id.tz = False

        self.env["gamification.goal"].search([]).unlink()
        self.assertFalse(self.env["gamification.goal"].search([]))

        challenge.action_check()
        goal_ids = self.env["gamification.goal"].search(
            [
                ("challenge_id", "=", challenge.id),
                ("state", "!=", "draft"),
                ("user_id", "in", challenge.user_ids.ids),
            ]
        )
        self.assertEqual(len(goal_ids), 4)
        self.assertEqual(set(goal_ids.mapped("state")), {"inprogress"})

        current_date = datetime.datetime.now() + timedelta(seconds=1)
        with freeze_time(current_date):
            self.env["mail.presence"]._update_presence(internal_last_active_recent)
            self.env["mail.presence"]._update_presence(portal_last_active_recent)

        all_test_users.partner_id.write({"tz": "Europe/Paris"})
        all_test_users.flush_recordset()

        challenge._update_all()
        unchanged_goal_ids = self.env["gamification.goal"].search(
            [
                ("challenge_id", "=", challenge.id),
                ("state", "=", "inprogress"),
                ("user_id", "in", challenge.user_ids.ids),
            ]
        )
        self.assertEqual(
            portal_last_active_old | internal_last_active_old,
            unchanged_goal_ids.user_id,
        )

    def test_30_create_challenge_with_sum_goal(self):
        challenge = self.env["gamification.challenge"].create(
            {
                "name": "test",
                "state": "draft",
                "user_domain": '[("active", "=", True)]',
                "reward_id": 1,
            }
        )

        model = self.env["ir.model"].search([("model", "=", "gamification.badge")])[0]
        field = self.env["ir.model.fields"].search(
            [("model", "=", "gamification.badge"), ("name", "=", "rule_max_number")]
        )[0]

        sum_goal = self.env["gamification.goal.definition"].create(
            {
                "name": "test",
                "computation_mode": "sum",
                "model_id": model.id,
                "field_id": field.id,
            }
        )

        self.env["gamification.challenge.line"].create(
            {
                "challenge_id": challenge.id,
                "definition_id": sum_goal.id,
                "condition": "higher",
                "target_goal": 1,
            }
        )

        challenge.action_start()

        self.assertEqual(
            challenge.state,
            "inprogress",
            "Challenge failed to start",
        )

    def test_40_create_challenge_with_sum_goal(self):
        challenge = self.env["gamification.challenge"].create(
            {
                "name": "Test Challenge",
                "state": "draft",
                "user_domain": '[("active", "=", True)]',
                "reward_id": 1,
            }
        )

        model = self.env["ir.model"].search(
            [("model", "=", "gamification.badge")], limit=1
        )

        field = self.env["ir.model.fields"].search(
            [("model", "=", "gamification.badge"), ("name", "=", "name")], limit=1
        )

        self.assertNotIn(
            field.ttype, {"integer", "float", "monetary"}, "Field should not be numeric"
        )

        sum_goal = self.env["gamification.goal.definition"].create(
            {
                "name": "Test Definition",
                "computation_mode": "sum",
                "model_id": model.id,
                "field_id": field.id,
            }
        )

        existing_badges_count = len(
            self.env["gamification.badge"].with_user(self.user_demo.id).search([])
        )

        self.env["gamification.challenge.line"].create(
            {
                "challenge_id": challenge.id,
                "definition_id": sum_goal.id,
                "condition": "higher",
                "target_goal": existing_badges_count + 1,
            }
        )

        challenge.action_start()
        self.assertEqual(challenge.state, "inprogress", "Challenge failed to start")

        goal = self.env["gamification.goal"].search(
            [("user_id", "=", self.user_demo.id), ("definition_id", "=", sum_goal.id)]
        )
        self.assertLess(
            goal.current,
            goal.target_goal,
            "Current goal should be less than the target goal",
        )
        self.assertEqual(goal.state, "inprogress")

        badge = self.env["gamification.badge"].create(
            {
                "name": self.user_demo.name + " triggered",
                "rule_auth": "users",
                "rule_auth_user_ids": self.user_demo,
            }
        )

        badge_user_wizard = self.env["wizard.gamification.badge.grant"].create(
            {
                "user_id": self.user_demo.id,
                "badge_id": badge.id,
            }
        )
        badge_user_wizard.action_grant_badge()

        goal.update_goal()
        self.assertEqual(
            goal.current,
            goal.target_goal,
            "Current goal should be equal to the target goal",
        )
        self.assertEqual(goal.state, "reached")

    def test_send_report_in_ranking(self):
        gamification_model = self.env["ir.model"]._get_id("gamification.badge")
        field = self.env["ir.model.fields"].search(
            [("model", "=", "gamification.badge"), ("name", "=", "rule_max_number")],
            limit=1,
        )

        sum_goal = self.env["gamification.goal.definition"].create(
            {
                "name": "test1",
                "computation_mode": "sum",
                "model_id": gamification_model,
                "field_id": field.id,
            }
        )

        challenge = self.env["gamification.challenge"].create(
            {
                "name": "test1",
                "state": "draft",
                "user_domain": '[("active", "=", True)]',
                "reward_id": 1,
                "visibility_mode": "ranking",
            }
        )

        self.env["gamification.challenge.line"].create(
            {
                "challenge_id": challenge.id,
                "definition_id": sum_goal.id,
                "condition": "higher",
                "target_goal": 1,
            }
        )

        challenge.action_start()
        current_date = datetime.datetime.now()

        with freeze_time(current_date):
            challenge.action_report_progress()

            self.assertEqual(
                challenge.state,
                "inprogress",
                "Challenge failed to start",
            )

            self.assertEqual(
                challenge.last_report_date,
                current_date.date(),
                "Challenge last report date is not as expected",
            )


class TestChallengeRewardNobodyBadge(TestGamificationCommon):
    def test_reward_nobody_badge_as_erp_manager(self):
        manager = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Challenge Manager",
                    "login": "challenge_mgr@odoo.com",
                    "email": "challenge_mgr@odoo.com",
                    "group_ids": [
                        (6, 0, [self.env.ref("base.group_erp_manager").id]),
                    ],
                }
            )
        )

        nobody_badge = self.env["gamification.badge"].create(
            {
                "name": "Challenge-Only Badge",
                "rule_auth": "nobody",
            }
        )

        challenge = self.env["gamification.challenge"].create(
            {
                "name": "Reward Nobody Test",
                "state": "draft",
                "reward_id": nobody_badge.id,
                "period": "once",
                "manual_user_ids": [(6, 0, [self.user_demo.id])],
            }
        )

        goal_def = self.env["gamification.goal.definition"].create(
            {
                "name": "Manual Test Goal",
                "computation_mode": "manually",
            }
        )
        self.env["gamification.challenge.line"].create(
            {
                "challenge_id": challenge.id,
                "definition_id": goal_def.id,
                "target_goal": 1,
            }
        )

        challenge.action_start()
        goal = self.env["gamification.goal"].search(
            [
                ("challenge_id", "=", challenge.id),
                ("user_id", "=", self.user_demo.id),
            ],
            limit=1,
        )
        self.assertTrue(goal, "Goal should have been created")
        goal.write({"current": 1, "state": "reached"})

        challenge.with_user(manager).write({"state": "done"})

        badge_grant = self.env["gamification.badge.user"].search(
            [
                ("badge_id", "=", nobody_badge.id),
                ("user_id", "=", self.user_demo.id),
                ("challenge_id", "=", challenge.id),
            ]
        )
        self.assertEqual(
            len(badge_grant),
            1,
            "Nobody badge should be granted via challenge reward even by non-admin manager",
        )


class TestCompletionCap(TestGamificationCommon):
    def test_topN_caps_completion_at_100(self):
        goal_def = self.env["gamification.goal.definition"].create(
            {
                "name": "Cap Test Def",
                "computation_mode": "manually",
                "condition": "higher",
            }
        )
        challenge = self.env["gamification.challenge"].create(
            {
                "name": "Cap Test Challenge",
                "state": "draft",
                "period": "once",
                "visibility_mode": "ranking",
                "manual_user_ids": [(6, 0, [self.user_demo.id, self.robot.id])],
            }
        )
        self.env["gamification.challenge.line"].create(
            {
                "challenge_id": challenge.id,
                "definition_id": goal_def.id,
                "target_goal": 10,
            }
        )
        challenge.action_start()

        goals = self.env["gamification.goal"].search(
            [("challenge_id", "=", challenge.id)]
        )
        for goal in goals:
            if goal.user_id == self.robot:
                goal.write({"current": 50, "state": "reached"})
            else:
                goal.write({"current": 10, "state": "reached"})

        challengers = challenge._get_top_users(3)
        ranked_users = [c for c in challengers if c]
        self.assertGreaterEqual(len(ranked_users), 2, "At least 2 users should qualify")
        self.assertIn(self.user_demo, ranked_users[:2], "Demo should be in top 2")

    def test_challenge_line_name_is_readonly(self):
        field = self.env["gamification.challenge.line"]._fields["name"]
        self.assertTrue(
            field.readonly,
            "Challenge line 'name' related field must be readonly to prevent "
            "accidental rename of the global goal definition",
        )


class TestChallengeStartRefreshButtonAccess(TestGamificationCommon):
    def setUp(self):
        super().setUp()
        self.employee_only_user = mail_new_test_user(
            self.env,
            login="challenge_employee_only",
            name="Challenge Employee Only",
            email="challenge_employee_only@example.com",
            groups="base.group_user,gamification.group_gamification_user",
        )
        self.challenge = self.env.ref("gamification.challenge_base_discover")

    def test_employee_direct_action_start_raises_access_error(self):
        with self.assertRaises(AccessError):
            self.challenge.with_user(self.employee_only_user).action_start()

    def test_employee_direct_action_check_raises_access_error(self):
        with self.assertRaises(AccessError):
            self.challenge.with_user(self.employee_only_user).action_check()

    def test_start_and_refresh_buttons_are_manager_only_in_view(self):
        view = self.env.ref("gamification.challenge_form_view")
        arch = etree.fromstring(view.arch_db)
        for name in ("action_start", "action_check"):
            button = arch.find(f'.//button[@name="{name}"]')
            self.assertIsNotNone(button, f"button {name} not found in view")
            self.assertEqual(
                button.get("groups"),
                "gamification.group_gamification_manager",
                f"button {name} must be restricted to managers",
            )


class test_badge_wizard(TestGamificationCommon):
    def test_grant_badge(self):
        wiz = self.env["wizard.gamification.badge.grant"].create(
            {
                "user_id": self.env.user.id,
                "badge_id": self.badge_good_job.id,
            }
        )
        with self.assertRaises(UserError, msg="A user cannot grant a badge to himself"):
            wiz.action_grant_badge()
        wiz.user_id = self.robot.id
        self.assertTrue(wiz.action_grant_badge(), "Could not grant badge")

        self.assertEqual(self.badge_good_job.stat_this_month, 1)
