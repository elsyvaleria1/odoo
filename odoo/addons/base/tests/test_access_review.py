from datetime import timedelta
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAccessReview(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Campaign = cls.env["access.review.campaign"]
        cls.admin = new_test_user(
            cls.env,
            login="access_admin",
            groups="base.group_erp_manager,base.group_partner_manager",
        )
        cls.reviewer = new_test_user(
            cls.env, login="reviewer", groups="base.group_user"
        )
        cls.holder = new_test_user(cls.env, login="holder", groups="base.group_user")
        cls.group = cls.env["res.groups"].create({"name": "Probe: reviewed group"})
        cls.holder.group_ids = [Command.link(cls.group.id)]
        cls.grant = cls.env["res.users.grant"].search(
            [("user_id", "=", cls.holder.id), ("group_id", "=", cls.group.id)]
        )

    def campaign(self, **values):
        return self.Campaign.with_user(self.admin).create(
            {
                "name": "Probe review",
                "kind": "memberships",
                "group_ids": [Command.set(self.group.ids)],
                "reviewer": "named",
                "reviewer_ids": [Command.set([self.reviewer.id, self.holder.id])],
            }
            | values
        )

    def item_of(self, campaign, record):
        return campaign.item_ids.filtered(
            lambda item: item.res_model == record._name and item.res_id == record.id
        )

    def test_a_membership_review_lists_the_holders_and_never_as_their_reviewer(self):
        campaign = self.campaign()
        campaign.action_start()
        item = self.item_of(campaign, self.grant)
        self.assertEqual(item.subject_user_id, self.holder)
        self.assertEqual(item.reviewer_ids, self.reviewer)
        with self.assertRaises(ValidationError):
            self.env["access.review.item"].browse(item.id).reviewer_ids = [
                Command.link(self.holder.id)
            ]

    def test_who_gave_an_access_does_not_certify_it(self):
        holder = new_test_user(self.env, login="holder_given", groups="base.group_user")
        grant = (
            self.env["res.users.grant"]
            .with_user(self.admin)
            .create({"user_id": holder.id, "group_id": self.group.id})
        )
        campaign = self.campaign(
            reviewer_ids=[Command.set([self.reviewer.id, self.admin.id])]
        )

        campaign.action_start()

        self.assertEqual(self.item_of(campaign, grant).reviewer_ids, self.reviewer)

    def test_a_reviewer_who_administers_nothing_revokes_what_they_review(self):
        campaign = self.campaign()
        campaign.action_start()
        item = self.item_of(campaign, self.grant)
        item.with_user(self.reviewer).action_revoke("left the team")
        self.assertEqual(item.decision, "revoked")
        self.assertTrue(item.applied_at)
        self.assertEqual(self.grant.state, "revoked")
        self.assertNotIn(self.group, self.holder.group_ids)
        self.assertTrue(
            self.env["ir.access.log"].search(
                [("event", "=", "review_revoked"), ("actor_id", "=", self.reviewer.id)]
            )
        )
        other = new_test_user(self.env, login="other", groups="base.group_user")
        other.group_ids = [Command.link(self.group.id)]
        other_grant = self.env["res.users.grant"].search(
            [("user_id", "=", other.id), ("group_id", "=", self.group.id)]
        )
        with self.assertRaises(AccessError):
            other_grant.with_user(self.reviewer).with_privilege(
                "base.privilege_apply_review", reason="not reviewed"
            ).action_revoke("not mine to revoke")

    def test_only_a_reviewer_decides_and_only_through_the_verb(self):
        campaign = self.campaign()
        campaign.action_start()
        item = self.item_of(campaign, self.grant)
        with self.assertRaises(AccessError):
            item.with_user(self.holder).action_certify()
        with self.assertRaises(UserError):
            item.with_user(self.reviewer).write({"decision": "certified"})
        item.with_user(self.reviewer).action_certify("still needed")
        self.assertEqual(item.decision, "certified")
        self.assertEqual(self.grant.state, "active")

    def test_the_deadline_revokes_or_keeps_by_kind_and_the_review_repeats(self):
        campaign = self.campaign(recurrence_months=3)
        self.assertEqual(campaign.on_deadline, "keep")
        campaign.action_start()
        item = self.item_of(campaign, self.grant)
        today = fields.Date.context_today(campaign)
        with patch.object(
            fields.Date, "context_today", lambda *a, **k: today + timedelta(days=15)
        ):
            self.Campaign._cron_close_due()
        self.assertEqual(campaign.state, "closed")
        self.assertEqual(item.decision, "pending")
        self.assertTrue(item.escalated)
        self.assertEqual(self.grant.state, "active")
        following = self.Campaign.search(
            [("name", "=", "Probe review"), ("state", "=", "draft")]
        )
        self.assertEqual(following.date_planned, today + relativedelta(months=3))
        self.assertEqual(
            following.date_deadline, today + relativedelta(months=3, days=14)
        )
        links = self.campaign(kind="links")
        self.assertEqual(links.on_deadline, "revoke")

    def test_an_exception_left_pending_is_revoked_at_the_deadline(self):
        exception = self.env["ir.access.exception"].create(
            {
                "user_id": self.holder.id,
                "kind": "sod",
                "res_model": "res.groups",
                "res_id": self.group.id,
                "reason": "probe",
                "reviewer_ids": [Command.set(self.admin.ids)],
                "date_to": fields.Datetime.now() + timedelta(days=10),
            }
        )
        campaign = self.campaign(kind="exceptions", reviewer="issuer")
        self.assertEqual(campaign.on_deadline, "revoke")
        campaign.action_start()
        item = self.item_of(campaign, exception)
        self.assertEqual(item.reviewer_ids, self.admin)
        campaign.action_close()
        self.assertEqual(item.decision, "revoked")
        self.assertTrue(exception.revoked_at)

    def test_the_deadline_decides_an_administrator_s_own_access_when_they_close(self):
        self.admin.group_ids = [Command.link(self.group.id)]
        own_grant = self.env["res.users.grant"].search(
            [("user_id", "=", self.admin.id), ("group_id", "=", self.group.id)]
        )
        campaign = self.campaign(on_deadline="revoke")
        campaign.action_start()
        own = self.item_of(campaign, own_grant)
        self.assertEqual(own.subject_user_id, self.admin)

        campaign.action_close()

        self.assertEqual(campaign.state, "closed")
        self.assertEqual(own.decision, "revoked")
        self.assertEqual(self.item_of(campaign, self.grant).decision, "revoked")
        self.assertEqual(own_grant.state, "revoked")

    def test_a_closed_break_glass_session_is_reviewed_by_another_administrator(self):
        glass = self.env["res.users.eligibility"].create(
            {
                "user_id": self.holder.id,
                "group_id": self.env.ref("base.group_break_glass").id,
            }
        )
        glass.with_user(self.holder).action_activate(1, "payroll is stuck")
        glass.with_user(self.holder).action_stop()
        item = self.env["access.review.item"].search(
            [("res_model", "=", glass._name), ("res_id", "=", glass.id)]
        )
        self.assertEqual(item.kind, "break_glass")
        self.assertIn("payroll is stuck", item.name)
        self.assertIn(self.admin, item.reviewer_ids)
        self.assertNotIn(self.holder, item.reviewer_ids)
        item.with_user(self.admin).action_revoke("not an emergency")
        self.assertEqual(glass.state, "revoked")

    def test_a_links_review_asks_whoever_shared_each_link_by_hand(self):
        record = self.env["res.partner"].create({"name": "Shared partner"})
        Link = self.env["access.link"].with_user(self.admin)
        by_hand, _token = Link._issue(record, role="view", cause="share")
        by_code, _token = Link._issue(record, role="comment", cause="notification")
        campaign = self.campaign(kind="links", reviewer="issuer")
        campaign.action_start()
        item = self.item_of(campaign, by_hand)
        self.assertEqual(item.reviewer_ids, self.admin)
        self.assertFalse(item.subject_user_id)
        self.assertFalse(self.item_of(campaign, by_code))
