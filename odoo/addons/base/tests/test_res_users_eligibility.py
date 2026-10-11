from datetime import timedelta
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestEligibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Grant = cls.env["res.users.grant"]
        cls.Eligibility = cls.env["res.users.eligibility"]
        cls.partner_manager = cls.env.ref("base.group_partner_manager")
        cls.break_glass = cls.env.ref("base.group_break_glass")
        cls.admin = new_test_user(
            cls.env, login="access_admin", groups="base.group_erp_manager"
        )
        cls.person = new_test_user(cls.env, login="eligible", groups="base.group_user")
        cls.other = new_test_user(cls.env, login="bystander", groups="base.group_user")
        cls.eligibility = cls.Eligibility.create(
            {
                "user_id": cls.person.id,
                "group_id": cls.partner_manager.id,
                "max_hours": 4,
                "reason": "keeps the partner data",
            }
        )

    def at(self, moment):
        return patch.object(type(self.env.cr), "now", lambda cr: moment)

    def activations(self, eligibility=None):
        eligibility = eligibility or self.eligibility
        return self.Grant.search(
            Domain("cause_model", "=", "res.users.eligibility")
            & Domain("cause_res_id", "=", eligibility.id)
        )

    def logged(self, event):
        return self.env["ir.access.log"].search(
            [("event", "=", event), ("subject_user_id", "=", self.person.id)]
        )

    def test_an_activation_grants_the_group_for_its_hours(self):
        now = self.env.cr.now()
        self.eligibility.with_user(self.person).action_activate(2, "fix a partner")
        grant = self.activations()
        self.assertEqual(grant.cause, "activation")
        self.assertEqual(grant.reason, "fix a partner")
        self.assertEqual(grant.date_to, now + timedelta(hours=2))
        self.assertEqual(grant.granted_by_id, self.person)
        self.assertTrue(self.person.has_group("base.group_partner_manager"))
        self.assertEqual(self.logged("elevation_activated").grant_id, grant)

    def test_an_activation_is_bounded_and_justified(self):
        mine = self.eligibility.with_user(self.person)
        with self.assertRaises(UserError):
            mine.action_activate(5, "too long")
        with self.assertRaises(UserError):
            mine.action_activate(1, "  ")
        mine.action_activate(1, "once")
        with self.assertRaises(UserError):
            mine.action_activate(1, "twice")

    def test_only_the_eligible_person_activates(self):
        with self.assertRaises(AccessError):
            self.eligibility.with_user(self.other).action_activate(1, "not mine")
        with self.assertRaises(AccessError):
            self.eligibility.with_user(self.admin).action_activate(1, "not mine")
        self.assertFalse(self.activations())

    def test_an_activation_grant_is_made_only_by_activating(self):
        for env in (self.env, self.env(user=self.admin)):
            with self.assertRaises(ValidationError):
                env["res.users.grant"].create(
                    {
                        "user_id": self.person.id,
                        "group_id": self.partner_manager.id,
                        "cause": "activation",
                    }
                )

    def test_the_activation_ends_by_itself_and_early_on_demand(self):
        start = self.env.cr.now()
        self.eligibility.with_user(self.person).action_activate(1, "a while")
        with self.at(start + timedelta(hours=2)):
            self.Grant._cron_cross_boundaries()
        self.assertEqual(self.activations().state, "expired")
        self.assertFalse(self.person.has_group("base.group_partner_manager"))
        self.assertEqual(len(self.logged("elevation_ended")), 1)
        mine = self.eligibility.with_user(self.person)
        mine.action_activate(1, "again")
        mine.action_stop()
        self.assertEqual(
            sorted(self.activations().mapped("state")), ["expired", "revoked"]
        )
        self.assertFalse(self.person.has_group("base.group_partner_manager"))
        self.assertEqual(len(self.logged("elevation_ended")), 2)

    def test_revoking_the_eligibility_ends_its_activation(self):
        self.eligibility.with_user(self.person).action_activate(1, "a while")
        self.eligibility.with_user(self.admin).action_revoke("left the team")
        self.assertEqual(self.eligibility.state, "revoked")
        self.assertEqual(self.activations().state, "revoked")
        with self.assertRaises(UserError):
            self.eligibility.with_user(self.person).action_activate(1, "after")

    def test_break_glass_is_held_only_through_an_activation(self):
        with self.assertRaises(ValidationError):
            self.person.group_ids = [Command.link(self.break_glass.id)]
        glass = self.Eligibility.create(
            {"user_id": self.person.id, "group_id": self.break_glass.id}
        )
        glass.with_user(self.person).action_activate(1, "the payroll run is stuck")
        self.assertEqual(self.activations(glass).cause, "break_glass")
        self.assertTrue(self.logged("break_glass_opened"))
        glass.with_user(self.person).action_stop()
        self.assertTrue(self.logged("break_glass_closed"))

    def test_a_group_held_standing_is_not_made_eligible(self):
        with self.assertRaises(ValidationError):
            self.Eligibility.create(
                {
                    "user_id": self.person.id,
                    "group_id": self.env.ref("base.group_user").id,
                }
            )
        implying = self.env["res.groups"].create(
            {"name": "Probe: implies partner manager"}
        )
        implying.implied_ids = [Command.link(self.partner_manager.id)]
        self.other.group_ids = [Command.link(implying.id)]
        with self.assertRaises(ValidationError):
            self.Eligibility.create(
                {"user_id": self.other.id, "group_id": self.partner_manager.id}
            )

    def test_an_activation_ends_or_stretches_only_through_its_own_verbs(self):
        glass = self.Eligibility.create(
            {"user_id": self.person.id, "group_id": self.break_glass.id}
        )
        glass.with_user(self.person).action_activate(1, "the payroll run is stuck")
        grant = self.activations(glass).with_user(self.admin)
        for date_to in (False, self.env.cr.now() + timedelta(days=365)):
            with self.subTest(date_to=date_to), self.assertRaises(UserError):
                grant.write({"date_to": date_to})
        with self.assertRaises(UserError):
            grant.write({"date_from": self.env.cr.now() + timedelta(hours=1)})
        self.assertEqual(grant.state, "active")
