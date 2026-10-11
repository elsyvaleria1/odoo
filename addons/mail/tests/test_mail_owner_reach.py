import random
from unittest.mock import patch

from odoo.tests.common import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestMailOwnerReach(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_b = cls.env["res.company"].create({"name": "Mail Reach B"})
        cls.user = new_test_user(
            cls.env, login="mail_reach_a", groups="base.group_user"
        )
        cls.other = new_test_user(
            cls.env,
            login="mail_reach_b",
            groups="base.group_user",
            company_id=company_b.id,
            company_ids=[(6, 0, company_b.ids)],
        )
        Partner = cls.env["res.partner"]
        cls.partners = Partner.create(
            [{"name": f"mail-reach-open-{i}"} for i in range(3)]
        ) | Partner.create(
            [
                {"name": f"mail-reach-b-{i}", "company_id": company_b.id}
                for i in range(3)
            ]
        )
        gone = Partner.create({"name": "mail-reach-gone"})
        gone_id = gone.id
        gone.unlink()
        documents = [("res.partner", p.id) for p in cls.partners]
        documents.append(("res.partner", gone_id))
        people = (cls.user | cls.other).partner_id
        rng = random.Random(5)
        Message = cls.env["mail.message"].sudo()
        values = []
        for i in range(80):
            model, res_id = rng.choice(documents) if rng.random() < 0.9 else (False, 0)
            values.append(
                {
                    "body": f"mail-reach-{i}",
                    "model": model,
                    "res_id": res_id,
                    "message_type": rng.choice(
                        ["comment", "notification", "user_notification", "email"]
                    ),
                    "author_id": rng.choice([False, *people.ids]),
                    "partner_ids": [(6, 0, rng.sample(people.ids, rng.randrange(2)))],
                    "reply_to": "reach@example.com",
                }
            )
        cls.messages = Message.create(values)
        for message in cls.messages.filtered(lambda m: rng.random() < 0.2):
            cls.env["mail.notification"].sudo().create(
                {
                    "mail_message_id": message.id,
                    "res_partner_id": rng.choice(people.ids),
                    "notification_type": "inbox",
                }
            )
        for partner in cls.partners:
            partner.message_subscribe(partner_ids=people.ids)
        cls.followers = (
            cls.env["mail.followers"]
            .sudo()
            .search(
                [("res_model", "=", "res.partner"), ("res_id", "in", cls.partners.ids)]
            )
        )
        cls.env.flush_all()

    def assert_paths(self, records, field_model):
        ordered = records.sorted("id", reverse=True).ids
        for user in (self.user, self.other):
            Model = self.env[records._name].with_user(user)
            expected = Model.browse(ordered)._filtered_access("read").ids
            domain = [("id", "in", ordered)]
            with self.subTest(model=records._name, user=user.login, path="by ids"):
                self.assertEqual(Model.search(domain, order="id desc").ids, expected)
                self.assertEqual(Model.search_count(domain), len(expected))
            with self.subTest(model=records._name, user=user.login, path="pages"):
                unpinned = [("id", ">=", min(ordered))]
                found = []
                with patch("odoo.tools.owner_reach.CHUNK", 5):
                    while page := Model.search(
                        unpinned, offset=len(found), limit=6, order="id desc"
                    ).ids:
                        found += page
                mine = set(ordered)
                self.assertEqual([i for i in found if i in mine], expected)
            with self.subTest(model=records._name, user=user.login, path="pinned"):
                pinned = domain + [(field_model, "=", "res.partner")]
                on_partner = records.filtered(lambda r: r[field_model] == "res.partner")
                self.assertEqual(
                    Model.search(pinned, order="id desc").ids,
                    Model.browse(on_partner.sorted("id", reverse=True).ids)
                    ._filtered_access("read")
                    .ids,
                )

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models")
    def test_message_search_finds_what_the_check_reads(self):
        self.assert_paths(self.messages, "model")

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models")
    def test_follower_search_finds_what_the_check_reads(self):
        self.assert_paths(self.followers, "res_model")


@tagged("post_install", "-at_install")
class TestActivityOwnerReach(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company_b = cls.env["res.company"].create({"name": "Activity Reach B"})
        cls.user = new_test_user(
            cls.env, login="activity_reach_a", groups="base.group_user"
        )
        cls.other = new_test_user(
            cls.env,
            login="activity_reach_b",
            groups="base.group_user",
            company_id=company_b.id,
            company_ids=[(6, 0, company_b.ids)],
        )
        Partner = cls.env["res.partner"]
        partners = Partner.create(
            [
                {"name": f"activity-reach-a-{i}", "company_id": cls.env.company.id}
                for i in range(3)
            ]
        ) | Partner.create(
            [
                {"name": f"activity-reach-b-{i}", "company_id": company_b.id}
                for i in range(3)
            ]
        )
        rng = random.Random(7)
        Activity = cls.env["mail.activity"].sudo()
        partner_model = cls.env["ir.model"]._get_id("res.partner")
        activity_model = cls.env["ir.model"]._get_id("mail.activity")
        todo = cls.env.ref("mail.mail_activity_data_todo").id
        assignees = [cls.user.id, cls.other.id, cls.env.ref("base.user_admin").id]
        cls.on_documents = Activity.create(
            [
                {
                    "activity_type_id": todo,
                    "res_model_id": partner_model,
                    "res_id": rng.choice(partners.ids),
                    "user_id": rng.choice(assignees),
                    "summary": f"activity-reach-{i}",
                }
                for i in range(40)
            ]
        )
        cls.on_activities = Activity.create(
            [
                {
                    "activity_type_id": todo,
                    "res_model_id": activity_model,
                    "res_id": rng.choice(cls.on_documents.ids),
                    "user_id": rng.choice(assignees),
                    "summary": f"activity-reach-nested-{i}",
                }
                for i in range(15)
            ]
        )
        cls.env.flush_all()

    def expected(self, user, activities):
        partners = self.env["res.partner"].with_user(user)

        def reached(activity):
            if activity.user_id == user:
                return True
            if activity.res_model == "mail.activity":
                return reached(self.env["mail.activity"].browse(activity.res_id))
            return bool(partners.browse(activity.res_id)._filtered_access("read"))

        return [a.id for a in activities if reached(a.sudo())]

    @mute_logger("odoo.addons.base.models.ir_access", "odoo.models")
    def test_activity_search_finds_the_documents_the_user_reads(self):
        activities = (self.on_documents | self.on_activities).sorted("id", reverse=True)
        domain = [("id", "in", activities.ids)]
        for user in (self.user, self.other):
            Activity = self.env["mail.activity"].with_user(user)
            expected = self.expected(user, activities)
            with self.subTest(user=user.login):
                self.assertTrue(0 < len(expected) < len(activities))
                self.assertEqual(Activity.search(domain, order="id desc").ids, expected)
                self.assertEqual(Activity.search_count(domain), len(expected))
                self.assertEqual(
                    Activity.search(domain, order="id desc", limit=7).ids,
                    expected[:7],
                )
                self.assertEqual(
                    Activity.browse(activities.ids)._filtered_access("read").ids,
                    expected,
                )
                pinned = domain + [("res_model", "=", "res.partner")]
                self.assertEqual(
                    Activity.search(pinned, order="id desc").ids,
                    self.expected(user, self.on_documents.sorted("id", reverse=True)),
                )
