from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.base.models.access_link import (
    LinkLoginRequired,
    LinkRefused,
    hash_token,
)


class AccessLinkCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, "link_owner", groups="base.group_user")
        cls.stranger = new_test_user(cls.env, "link_stranger", groups="base.group_user")
        cls.portal = new_test_user(cls.env, "link_portal", groups="base.group_portal")
        cls.customer = cls.env["res.partner"].create({"name": "Link Customer"})
        cls.doc = (
            cls.env["test_access_right.shared_doc"]
            .with_user(cls.owner)
            .create({"name": "Quotation 7"})
        )
        cls.other = (
            cls.env["test_access_right.shared_doc"]
            .with_user(cls.owner)
            .create({"name": "Quotation 8"})
        )
        cls.Link = cls.env["access.link"]

    def _issue(self, record=None, **kwargs):
        record = (record or self.doc).with_user(self.owner)
        return self.Link.with_user(self.owner)._issue(record, **kwargs)


@tagged("post_install", "-at_install", "access_link")
class TestAccessLink(AccessLinkCase):
    def test_the_token_is_stored_as_its_hash_only(self):
        link, token = self._issue(partner=self.customer)
        self.env.cr.execute(
            "SELECT token_hash, token_nonce FROM access_link WHERE id = %s", [link.id]
        )
        stored_hash, nonce = self.env.cr.fetchone()
        self.assertEqual(stored_hash, hash_token(token))
        self.assertNotIn(token, (stored_hash, nonce))
        self.assertGreaterEqual(len(token), 32)

    def test_a_link_resolves_to_its_record(self):
        link, token = self._issue(partner=self.customer)
        resolution = self.Link.with_user(self.env.ref("base.public_user"))._resolve(
            token, model=self.doc._name, res_id=self.doc.id
        )
        self.assertEqual(resolution.record, self.doc)
        self.assertEqual(resolution.link, link)
        self.assertEqual(resolution.partner, self.customer)

    def test_every_refusal_is_the_same(self):
        _link, token = self._issue(partner=self.customer)
        public = self.Link.with_user(self.env.ref("base.public_user"))
        guessed = token[:-1] + ("A" if token[-1] != "A" else "B")
        doc = (self.doc._name, self.doc.id)
        refused = {
            "guessed": (guessed, *doc, "view"),
            "other record": (token, self.doc._name, self.other.id, "view"),
            "other model": (token, "res.partner", self.doc.id, "view"),
            "non-ascii": ("é" * 32, *doc, "view"),
            "too short": (token[:8], *doc, "view"),
            "not a string": (["x"] * 32, *doc, "view"),
            "higher role": (token, *doc, "edit"),
        }
        for label, (presented, model, res_id, role) in refused.items():
            with self.subTest(label), self.assertRaises(LinkRefused):
                public._resolve(presented, model=model, res_id=res_id, role=role)

    def test_revoked_and_expired_links_open_nothing(self):
        public = self.Link.with_user(self.env.ref("base.public_user"))
        revoked, revoked_token = self._issue(partner=self.customer)
        revoked.with_user(self.owner).action_revoke("sent to the wrong person")
        with self.assertRaises(LinkRefused):
            public._resolve(revoked_token)
        self.assertEqual(revoked.state, "revoked")

        expired, expired_token = self._issue(
            partner=self.env["res.partner"].create({"name": "Other"}),
            date_to=fields.Datetime.now() + timedelta(days=1),
        )
        public._resolve(expired_token)
        expired.sudo().date_to = fields.Datetime.now() - timedelta(seconds=1)
        with self.assertRaises(LinkRefused):
            public._resolve(expired_token)
        self.assertIn(expired, self.Link.sudo().search([("state", "=", "expired")]))

    def test_the_same_recipient_gets_the_same_link_back(self):
        first, token = self._issue(partner=self.customer, cause="notification")
        again, token_again = self._issue(partner=self.customer, cause="notification")
        self.assertEqual(first, again)
        self.assertEqual(token, token_again)
        other, other_token = self._issue(
            partner=self.env["res.partner"].create({"name": "Someone Else"}),
            cause="notification",
        )
        self.assertNotEqual(other, first)
        self.assertNotEqual(other_token, token)
        first.with_user(self.owner).action_revoke()
        fresh, fresh_token = self._issue(partner=self.customer, cause="notification")
        self.assertNotEqual(fresh, first)
        self.assertNotEqual(fresh_token, token)

    def test_a_link_anyone_can_use_expires_by_its_purpose(self):
        now = fields.Datetime.now()
        shared, _token = self._issue(cause="share")
        self.assertAlmostEqual(
            shared.date_to, now + timedelta(days=30), delta=timedelta(minutes=5)
        )
        sent, _token = self._issue(partner=self.customer, cause="notification")
        self.assertAlmostEqual(
            sent.date_to, now + timedelta(days=365), delta=timedelta(minutes=5)
        )

    def test_only_an_administrator_waives_the_expiry(self):
        with self.assertRaises(AccessError):
            self._issue(waive_expiry=True)
        admin = self.env.ref("base.user_admin")
        self.doc.sudo().reader_ids = admin
        link, _token = self.Link.with_user(admin)._issue(
            self.doc.with_user(admin), waive_expiry=True
        )
        self.assertFalse(link.date_to)
        self.assertTrue(link.expiry_waived)

    def test_a_waived_expiry_is_never_answered_with_an_expiring_link(self):
        admin = self.env.ref("base.user_admin")
        self.doc.sudo().reader_ids = admin
        Link = self.Link.with_user(admin)
        expiring, _token = Link._issue(self.doc.with_user(admin))
        self.assertTrue(expiring.date_to)
        waived, _token = Link._issue(self.doc.with_user(admin), waive_expiry=True)
        self.assertNotEqual(waived, expiring)
        self.assertFalse(waived.date_to)

    def test_an_expiring_request_is_never_answered_with_a_waived_link(self):
        admin = self.env.ref("base.user_admin")
        self.doc.sudo().reader_ids = admin
        waived, _token = self.Link.with_user(admin)._issue(
            self.doc.with_user(admin), waive_expiry=True
        )
        asked, _token = self._issue()
        self.assertNotEqual(asked, waived)
        self.assertTrue(asked.date_to)

    def test_each_record_gets_its_own_link_in_one_batch_and_gets_it_back(self):
        people = self.env["res.partner"].create(
            [{"name": "Invitee one"}, {"name": "Invitee two"}]
        )
        Link = self.Link.with_user(self.owner)
        tokens = Link._issue_each(
            people.with_user(self.owner), partner_field="commercial_partner_id"
        )
        links = self.Link.sudo().search(
            [("res_model", "=", "res.partner"), ("res_id", "in", people.ids)]
        )
        self.assertEqual(sorted(links.mapped("res_id")), sorted(people.ids))
        self.assertEqual(
            {link.res_id: link.partner_id.id for link in links},
            {person.id: person.id for person in people},
        )
        for link in links:
            self.assertEqual(link.token_hash, hash_token(tokens[link.res_id]))
        again = Link._issue_each(
            people.with_user(self.owner), partner_field="commercial_partner_id"
        )
        self.assertEqual(again, tokens, "the live links are reused")
        links[:1].with_user(self.owner).action_revoke()
        renewed = Link._issue_each(
            people.with_user(self.owner), partner_field="commercial_partner_id"
        )
        self.assertNotEqual(renewed[links[:1].res_id], tokens[links[:1].res_id])
        self.assertEqual(renewed[links[1:].res_id], tokens[links[1:].res_id])

    def test_records_that_hold_no_link_get_theirs_without_a_lookup(self):
        people = self.env["res.partner"].create(
            [{"name": "Newcomer one"}, {"name": "Newcomer two"}]
        )
        Link = self.Link.with_user(self.owner)
        with patch.object(
            type(self.Link), "search", side_effect=AssertionError("looked up")
        ):
            tokens = Link._issue_each_new(
                people.with_user(self.owner), partner_field="commercial_partner_id"
            )
        links = self.Link.sudo().search(
            [("res_model", "=", "res.partner"), ("res_id", "in", people.ids)]
        )
        self.assertEqual(
            {link.res_id: link.partner_id.id for link in links},
            {person.id: person.id for person in people},
        )
        for link in links:
            self.assertEqual(link.token_hash, hash_token(tokens[link.res_id]))

    def test_a_link_issued_for_a_cause_record_is_reused_for_that_record_only(self):
        first, token = self._issue(cause="notification", cause_record=self.other)
        again, token_again = self._issue(cause="notification", cause_record=self.other)
        self.assertEqual((again, token_again), (first, token))
        self.assertEqual(
            (first.cause_model, first.cause_res_id), (self.other._name, self.other.id)
        )
        elsewhere, elsewhere_token = self._issue(
            cause="notification", cause_record=self.doc
        )
        self.assertNotEqual(elsewhere, first)
        self.assertNotEqual(elsewhere_token, token)
        plain, __ = self._issue(cause="notification")
        self.assertNotIn(plain, first | elsewhere)

    def test_issuing_needs_the_right_the_link_hands_out(self):
        with self.assertRaises(AccessError):
            self.Link.with_user(self.stranger)._issue(self.doc.with_user(self.stranger))
        self.env["test_access_right.shared_doc"].browse(
            self.doc.id
        ).sudo().reader_ids = self.stranger
        self.Link.with_user(self.stranger)._issue(self.doc.with_user(self.stranger))
        with self.assertRaises(AccessError):
            self.Link.with_user(self.stranger)._issue(
                self.doc.with_user(self.stranger), role="edit"
            )

    def test_code_holding_the_manage_privilege_vouches_for_the_record(self):
        company = self.env["res.company"].create({"name": "Link Co"})
        self.doc.sudo().company_id = company
        stranger_links = self.Link.with_user(self.stranger)
        with self.assertRaises(AccessError):
            stranger_links._issue(self.doc.with_user(self.stranger))
        vouched = stranger_links.with_privilege(
            "base.privilege_manage_links", reason="a folder reached its subtree"
        )
        link, _token = vouched._issue(self.doc.with_user(self.stranger))
        self.assertEqual(link.sudo().company_id, company)
        vouched._update_record_links(
            self.doc.with_user(self.stranger), {"role": "edit"}
        )
        vouched._revoke_record_links(self.doc.with_user(self.stranger), "moved")
        self.assertEqual(link.sudo().state, "revoked")

    def test_nobody_picks_a_token_or_a_record(self):
        link, _token = self._issue()
        chosen = {
            "token_hash": hash_token("A" * 32),
            "res_id": self.other.id,
            "revoked_at": False,
            "use_count": 0,
        }
        for field_name, value in chosen.items():
            with self.subTest(field_name), self.assertRaises(AccessError):
                link.with_user(self.env.ref("base.user_admin")).write(
                    {field_name: value}
                )
        with self.assertRaises(AccessError):
            self.Link.with_user(self.env.ref("base.user_admin")).create(
                {
                    "res_model": self.doc._name,
                    "res_id": self.doc.id,
                    "token_hash": hash_token("A" * 32),
                }
            )
        with self.assertRaises(UserError):
            link.with_user(self.env.ref("base.user_admin")).unlink()

    def test_a_sharer_cannot_rewrite_what_a_link_grants(self):
        link, token = self._issue(partner=self.customer)
        someone = self.env["res.partner"].create({"name": "Someone Else"})
        rewrites = {
            "role": "edit",
            "audience": "signed_in",
            "partner_id": someone.id,
            "audience_partner_ids": [(6, 0, someone.ids)],
            "company_id": self.env.company.id,
        }
        for field_name, value in rewrites.items():
            with self.subTest(field_name), self.assertRaises(AccessError):
                link.with_user(self.owner).write({field_name: value})

        public = self.Link.with_user(self.env.ref("base.public_user"))
        resolution = public._resolve(token, model=self.doc._name, res_id=self.doc.id)
        self.assertEqual(resolution.partner, self.customer)
        with self.assertRaises(LinkRefused):
            public._resolve(
                token, model=self.doc._name, res_id=self.doc.id, role="edit"
            )

    def test_a_sharer_moves_the_expiry_within_the_link_s_lifetime(self):
        link, _token = self._issue()
        now = fields.Datetime.now()
        sharer = link.with_user(self.owner)

        sharer.write({"date_to": now + timedelta(days=10)})

        self.assertAlmostEqual(
            link.date_to, now + timedelta(days=10), delta=timedelta(minutes=5)
        )
        self.assertIn(
            "link_extended",
            self.env["ir.access.log"]
            .sudo()
            .search([("link_id", "=", link.id)])
            .mapped("event"),
        )
        far = now + timedelta(days=400)
        with self.assertRaises(UserError):
            sharer.write({"date_to": far})
        with self.assertRaises(UserError):
            sharer.action_extend(far)
        with self.assertRaises(UserError):
            sharer.write({"date_to": False})
        administrator = link.with_user(self.env.ref("base.user_admin"))
        with self.assertRaises(ValidationError):
            administrator.action_extend(far)
        administrator.write({"date_to": far, "expiry_waived": True})
        self.assertAlmostEqual(link.date_to, far, delta=timedelta(seconds=1))

    def test_an_expiry_typed_as_text_is_saved_and_logged(self):
        link, _token = self._issue()
        later = fields.Datetime.now() + timedelta(days=10)
        latest = fields.Datetime.now() + timedelta(days=20)

        link.with_user(self.owner).write({"date_to": fields.Datetime.to_string(later)})
        self.Link.with_user(self.owner)._update_record_links(
            self.doc.with_user(self.owner),
            {"date_to": fields.Datetime.to_string(latest)},
        )

        self.assertEqual(link.date_to, latest)
        self.assertEqual(
            self.env["ir.access.log"]
            .sudo()
            .search(
                [("link_id", "=", link.id), ("event", "=", "link_extended")],
                order="id",
            )
            .mapped("reason"),
            [fields.Datetime.to_string(later), fields.Datetime.to_string(latest)],
        )

    def test_a_link_is_reused_only_when_it_is_the_one_asked_for(self):
        month, _token = self._issue()
        hour, _token = self._issue(date_to=fields.Datetime.now() + timedelta(hours=1))
        self.assertNotEqual(hour, month)

        people = self.env["res.partner"].create(
            [{"name": "Ann"}, {"name": "Ben"}, {"name": "Cid"}]
        )
        two, _token = self._issue(audience="partners", audience_partners=people[:2])
        third, _token = self._issue(audience="partners", audience_partners=people[2])
        again, _token = self._issue(audience="partners", audience_partners=people[:2])

        self.assertNotEqual(third, two)
        self.assertEqual(again, two)

    def test_only_the_sharer_or_an_administrator_revokes(self):
        link, _token = self._issue()
        with self.assertRaises(AccessError):
            link.with_user(self.stranger).action_revoke()
        link.with_user(self.owner).action_revoke()
        self.assertEqual(link.revoked_by_id, self.owner)

        other, _token = self._issue(partner=self.customer)
        admin = self.env.ref("base.user_admin")
        other.with_user(admin).action_revoke("left the company")
        self.assertEqual(other.revoked_by_id, admin)

    def test_a_record_writer_revokes_every_link_of_the_record(self):
        first, _token = self._issue(partner=self.customer)
        second, _token = self._issue()
        self.doc.sudo().reader_ids = self.stranger
        with self.assertRaises(AccessError):
            self.Link.with_user(self.stranger)._revoke_record_links(
                self.doc.with_user(self.stranger), "not theirs"
            )
        self.Link.with_user(self.owner)._revoke_record_links(
            self.doc.with_user(self.owner), "the quotation was cancelled"
        )
        self.assertEqual((first | second).mapped("state"), ["revoked", "revoked"])

    def test_a_records_links_are_listed_to_its_readers_only(self):
        link, _token = self._issue(partner=self.customer)
        stranger_view = self.Link.with_user(self.stranger)
        self.assertFalse(stranger_view._record_links(self.doc.with_user(self.stranger)))
        self.doc.sudo().reader_ids = self.stranger
        self.assertEqual(
            stranger_view._record_links(self.doc.with_user(self.stranger)), link
        )

    def test_a_record_writer_changes_role_and_expiry_and_the_url_stays(self):
        link, token = self._issue(partner=self.customer)
        self.doc.sudo().reader_ids = self.stranger
        later = fields.Datetime.now() + timedelta(days=20)
        with self.assertRaises(AccessError):
            self.Link.with_user(self.stranger)._update_record_links(
                self.doc.with_user(self.stranger), {"role": "edit"}
            )
        with self.assertRaises(UserError):
            self.Link.with_user(self.owner)._update_record_links(
                self.doc.with_user(self.owner), {"token_hash": "x"}
            )
        self.Link.with_user(self.owner)._update_record_links(
            self.doc.with_user(self.owner), {"role": "edit", "date_to": later}
        )
        resolution = self.Link.with_user(self.env.ref("base.public_user"))._resolve(
            token, role="edit"
        )
        self.assertEqual(resolution.link, link)
        self.assertEqual(link.date_to, later.replace(microsecond=0))
        self.assertEqual(
            self.Link.with_user(self.stranger)._record_links(
                self.doc.with_user(self.stranger)
            ),
            link,
        )

    def test_the_audience_is_checked_against_the_session(self):
        partners_link, partners_token = self._issue(
            partner=self.portal.partner_id, audience="partners"
        )
        with self.assertRaises(LinkLoginRequired):
            self.Link.with_user(self.env.ref("base.public_user"))._resolve(
                partners_token
            )
        with self.assertRaises(LinkRefused):
            self.Link.with_user(self.stranger)._resolve(partners_token)
        resolution = self.Link.with_user(self.portal)._resolve(partners_token)
        self.assertEqual(resolution.link, partners_link)

        _signed, signed_token = self._issue(audience="signed_in")
        with self.assertRaises(LinkLoginRequired):
            self.Link.with_user(self.env.ref("base.public_user"))._resolve(signed_token)
        self.Link.with_user(self.stranger)._resolve(signed_token)

    def _organization(self):
        acme = self.env["res.partner"].create({"name": "ACME", "is_company": True})
        ann, bob = (
            new_test_user(
                self.env,
                login,
                groups="base.group_portal",
                partner_id=self.env["res.partner"]
                .create({"name": login, "parent_id": acme.id})
                .id,
            )
            for login in ("link_ann", "link_bob")
        )
        return acme, ann, bob

    def test_a_link_for_named_people_admits_those_people_only(self):
        acme, ann, bob = self._organization()
        _link, for_ann = self._issue(partner=ann.partner_id, audience="partners")
        _link, for_acme = self._issue(partner=acme, audience="partners")
        self.assertTrue(self.Link.with_user(ann)._resolve(for_ann))
        for token in (for_ann, for_acme):
            with self.subTest(token=token), self.assertRaises(LinkRefused):
                self.Link.with_user(bob)._resolve(token)

    def test_a_link_for_their_organizations_admits_their_colleagues(self):
        _acme, ann, bob = self._organization()
        link, token = self._issue(partner=ann.partner_id, audience="organizations")
        self.assertEqual(link.audience_partner_ids, ann.partner_id)
        for colleague in (ann, bob):
            self.assertEqual(self.Link.with_user(colleague)._resolve(token).link, link)
        with self.assertRaises(LinkRefused):
            self.Link.with_user(self.portal)._resolve(token)
        with self.assertRaises(LinkLoginRequired):
            self.Link.with_user(self.env.ref("base.public_user"))._resolve(token)
        again, _token = self._issue(partner=ann.partner_id, audience="partners")
        self.assertNotEqual(again, link, "a narrower audience is another link")

    def test_every_link_expires_by_its_purpose_whatever_its_audience(self):
        now = fields.Datetime.now()
        for audience in ("partners", "organizations", "signed_in"):
            with self.subTest(audience=audience):
                link, _token = self._issue(
                    partner=self.portal.partner_id,
                    audience=audience,
                    cause="notification",
                )
                self.assertAlmostEqual(
                    link.date_to,
                    now + timedelta(days=365),
                    delta=timedelta(minutes=5),
                )

    def test_every_cause_declares_its_lifetime(self):
        causes = {value for value, _label in self.Link._fields["cause"].selection}
        self.assertEqual(set(self.Link._get_cause_lifetimes()), causes)

    def test_no_path_issues_or_moves_a_link_past_its_lifetime(self):
        far = fields.Datetime.now() + timedelta(days=90)
        link, _token = self._issue()
        doc = self.doc.with_user(self.owner)
        manager = self.Link.with_user(self.owner).with_privilege(
            "base.privilege_manage_links", reason="the test tries every path"
        )
        paths = {
            "_issue": lambda: self._issue(date_to=far),
            "_issue_many": lambda: self.Link.with_user(self.owner)._issue_many(
                doc, self.customer, date_to=far
            ),
            "_update_record_links": lambda: self.Link.with_user(
                self.owner
            )._update_record_links(doc, {"date_to": far}),
            "manage privilege": lambda: (
                link.with_user(self.owner)
                .with_privilege("base.privilege_manage_links", reason="test")
                .write({"date_to": far})
            ),
            "manage privilege, no expiry": lambda: manager.browse(link.id).write(
                {"date_to": False}
            ),
            "superuser": lambda: link.sudo().write({"date_to": far}),
        }
        for label, path in paths.items():
            with (
                self.subTest(label),
                self.assertRaises(ValidationError),
                self.env.cr.savepoint(),
            ):
                path()
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=30),
            delta=timedelta(minutes=5),
        )

    def _issue_dated(self, due, **kwargs):
        self.doc.sudo().date_due = due
        link, _token = self._issue(
            partner=self.customer, cause="notification", **kwargs
        )
        return link

    def test_a_link_following_its_record_s_date_expires_with_it(self):
        due = fields.Datetime.now() + timedelta(days=730)
        link = self._issue_dated(due)
        self.assertTrue(link.dated_by_record)
        self.assertEqual(link.date_to, due + timedelta(days=7))
        self.doc.sudo().partner_id = self.customer
        each = self.Link.with_user(self.owner)._issue_each_new(
            self.doc.with_user(self.owner), partner_field="partner_id"
        )
        each_link = self.Link.sudo()._resolve(each[self.doc.id], action=None).link
        self.assertTrue(each_link.dated_by_record)
        self.assertEqual(each_link.date_to, due + timedelta(days=7))

    def test_every_issuer_of_a_notification_hands_out_the_dated_link(self):
        due = fields.Datetime.now() + timedelta(days=730)
        self.doc.sudo().write({"date_due": due, "partner_id": self.customer.id})
        Link = self.Link.with_user(self.owner)
        doc = self.doc.with_user(self.owner)
        link, token = Link._issue(doc, partner=self.customer, cause="notification")
        self.assertTrue(link.dated_by_record)
        self.assertEqual(link.date_to, due + timedelta(days=7))
        self.assertEqual(
            Link._issue_each(doc, partner_field="partner_id"), {doc.id: token}
        )
        self.assertEqual(
            Link._issue_many(doc, self.customer, cause="notification"),
            {self.customer.id: token},
        )
        self.assertEqual(
            self.Link.sudo().search_count(
                [("res_model", "=", doc._name), ("res_id", "=", doc.id)]
            ),
            1,
            "no issuer mints a second link beside the dated one",
        )
        shared, _token = Link._issue(doc, cause="share")
        self.assertFalse(shared.dated_by_record)
        with self.assertRaises(ValueError):
            Link._issue_many(doc, self.customer, cause="notification", date_to=due)

    def test_a_record_without_a_date_keeps_the_cause_s_lifetime(self):
        now = fields.Datetime.now()
        for cause, days, dated in (("notification", 365, True), ("share", 30, False)):
            with self.subTest(cause=cause):
                link, _token = self._issue(cause=cause)
                self.assertEqual(link.dated_by_record, dated)
                self.assertAlmostEqual(
                    link.date_to,
                    now + timedelta(days=days),
                    delta=timedelta(minutes=5),
                )
                link.sudo().date_to -= timedelta(minutes=1)
                again, _token = self._issue(cause=cause)
                self.assertEqual(again, link, "handed out again, issued earlier")

    def test_a_dated_link_moves_with_its_record_both_ways(self):
        now = fields.Datetime.now()
        link = self._issue_dated(now + timedelta(days=10))
        undated, _token = self._issue(partner=self.customer, cause="share")
        Link = self.Link.with_user(self.owner)
        for due in (now + timedelta(days=730), now + timedelta(days=3)):
            with self.subTest(due=due):
                self.doc.sudo().date_due = due
                Link._sync_record_expiries(self.doc.with_user(self.owner))
                self.assertEqual(link.date_to, due + timedelta(days=7))
        self.doc.sudo().date_due = False
        Link._sync_record_expiries(self.doc.with_user(self.owner))
        self.assertAlmostEqual(
            link.date_to, now + timedelta(days=365), delta=timedelta(minutes=5)
        )
        self.assertAlmostEqual(
            undated.date_to, now + timedelta(days=30), delta=timedelta(minutes=5)
        )

    def test_a_dated_link_is_handed_out_again_at_its_record_s_date(self):
        now = fields.Datetime.now()
        link = self._issue_dated(now + timedelta(days=10))
        self.assertEqual(self._issue_dated(now + timedelta(days=10)), link)
        due = now + timedelta(days=400)
        self.doc.sudo().date_due = due
        self.Link.with_user(self.owner)._sync_record_expiries(
            self.doc.with_user(self.owner)
        )
        self.assertEqual(self._issue_dated(due), link)
        self.assertEqual(link.date_to, due + timedelta(days=7))

    def test_no_path_moves_a_dated_link_past_its_record_s_date(self):
        due = fields.Datetime.now() + timedelta(days=730)
        link = self._issue_dated(due)
        beyond = due + timedelta(days=8)
        doc = self.doc.with_user(self.owner)
        paths = {
            "sharer": lambda: link.with_user(self.owner).write({"date_to": beyond}),
            "sharer extends": lambda: link.with_user(self.owner).action_extend(beyond),
            "_update_record_links": lambda: self.Link.with_user(
                self.owner
            )._update_record_links(doc, {"date_to": beyond}),
            "manage privilege": lambda: (
                link.with_user(self.owner)
                .with_privilege("base.privilege_manage_links", reason="test")
                .write({"date_to": beyond})
            ),
            "superuser": lambda: link.sudo().write({"date_to": beyond}),
            "administrator": lambda: link.with_user(
                self.env.ref("base.user_admin")
            ).action_extend(beyond),
        }
        for label, path in paths.items():
            with (
                self.subTest(label),
                self.assertRaises(ValidationError),
                self.env.cr.savepoint(),
            ):
                path()
        with self.assertRaises(ValueError):
            self._issue(date_to=beyond, cause="notification")
        undated, _token = self._issue(cause="share")
        for user in (self.owner, self.env.ref("base.user_admin")):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                undated.with_user(user).write({"dated_by_record": True})
        link.with_user(self.owner).write({"date_to": due})
        self.assertEqual(link.date_to, due)
        link.with_user(self.env.ref("base.user_admin")).write(
            {"date_to": beyond, "expiry_waived": True}
        )
        self.assertEqual(link.date_to, beyond)

    def test_uses_are_counted_by_hour_address_user_and_action(self):
        link, token = self._issue(partner=self.customer)
        public = self.Link.with_user(self.env.ref("base.public_user"))
        with patch.object(
            type(self.env["ir.http"]),
            "_get_request_remote_addr",
            lambda self: "10.0.0.7",
        ):
            for _ in range(3):
                public._resolve(token)
            public._resolve(token, action="download")
            self.Link.with_user(self.portal)._resolve(token)
        link.invalidate_recordset()
        self.assertEqual(link.use_count, 5)
        self.assertTrue(link.last_used_at)
        rows = {(use.action, use.user_id): use.count for use in link.sudo().use_ids}
        public_id = 0
        self.assertEqual(
            rows,
            {
                ("view", public_id): 3,
                ("download", public_id): 1,
                ("view", self.portal.id): 1,
            },
        )

    def test_revoking_and_extending_are_logged(self):
        link, _token = self._issue(partner=self.customer, cause="notification")
        link.with_user(self.owner).action_extend(
            fields.Datetime.now() + timedelta(days=90)
        )
        link.with_user(self.owner).action_revoke("done")
        events = (
            self.env["ir.access.log"]
            .sudo()
            .search([("link_id", "=", link.id)])
            .mapped("event")
        )
        self.assertEqual(
            sorted(events), ["link_created", "link_extended", "link_revoked"]
        )

    def test_a_changed_secret_leaves_old_links_working(self):
        link, token = self._issue(partner=self.customer)
        self.env["ir.config_parameter"].sudo().set_param(
            "database.secret", "rotated-for-the-test"
        )
        public = self.Link.with_user(self.env.ref("base.public_user"))
        self.assertEqual(public._resolve(token).link, link)
        self.assertIsNone(link._token())
        fresh, fresh_token = self._issue(partner=self.customer)
        self.assertNotEqual(fresh, link)
        self.assertNotEqual(fresh_token, token)

    def test_a_session_opens_a_record_at_the_role_it_holds_on_it(self):
        self.doc.sudo().reader_ids = self.stranger
        Link = self.Link.with_user(self.stranger)
        self.assertEqual(Link._open_record(self.doc._name, self.doc.id), self.doc)
        with self.assertRaises(AccessError):
            Link._open_record(self.doc._name, self.doc.id, role="edit")
        _link, token = self._issue(role="edit")
        opened = Link._open_record(
            self.doc._name, self.doc.id, access_token=token, role="edit"
        )
        self.assertEqual(opened, self.doc)


@tagged("post_install", "-at_install", "access_link")
class TestLinkDoor(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(cls.env, "door_owner", groups="base.group_user")
        cls.stranger = new_test_user(
            cls.env, "door_stranger", password="door_stranger", groups="base.group_user"
        )
        cls.doc = (
            cls.env["test_access_right.shared_doc"]
            .with_user(cls.owner)
            .create({"name": "Invoice 12"})
        )
        cls.other = (
            cls.env["test_access_right.shared_doc"]
            .with_user(cls.owner)
            .create({"name": "Invoice 13"})
        )

    def _issue(self, **kwargs):
        return (
            self.env["access.link"]
            .with_user(self.owner)
            ._issue(self.doc.with_user(self.owner), **kwargs)
        )

    def test_the_door_opens_with_the_token_and_names_the_link(self):
        link, token = self._issue()
        res = self.url_open(
            f"/test_access_rights/shared/{self.doc.id}?access_token={token}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"id": self.doc.id, "link": link.id})

    def test_the_door_refuses_every_bad_token_alike(self):
        _link, token = self._issue()
        for label, url in {
            "no token": f"/test_access_rights/shared/{self.doc.id}",
            "guessed": f"/test_access_rights/shared/{self.doc.id}?access_token={'A' * 32}",
            "other record": f"/test_access_rights/shared/{self.other.id}?access_token={token}",
            "role": f"/test_access_rights/shared_edit/{self.doc.id}?access_token={token}",
        }.items():
            with self.subTest(label):
                self.assertEqual(self.url_open(url).status_code, 404)

    def test_a_signed_in_reader_needs_no_token(self):
        self.authenticate("door_stranger", "door_stranger")
        self.assertEqual(
            self.url_open(f"/test_access_rights/shared/{self.doc.id}").status_code, 404
        )
        self.doc.sudo().reader_ids = self.stranger
        res = self.url_open(f"/test_access_rights/shared/{self.doc.id}")
        self.assertEqual(res.json(), {"id": self.doc.id, "link": False})

    def test_a_signed_in_reader_does_not_pass_an_edit_door(self):
        self.doc.sudo().reader_ids = self.stranger
        self.authenticate("door_stranger", "door_stranger")
        url = f"/test_access_rights/shared_edit/{self.doc.id}"
        self.assertEqual(self.url_open(url).status_code, 404)
        _link, token = self._issue(role="edit")
        res = self.url_open(f"{url}?access_token={token}")
        self.assertEqual(res.json(), {"id": self.doc.id})

    def test_a_route_may_send_a_refused_visitor_elsewhere(self):
        _link, token = self._issue()
        url = f"/test_access_rights/shared_or_home/{self.doc.id}"
        refused = self.url_open(f"{url}?access_token={'A' * 32}", allow_redirects=False)
        self.assertEqual(refused.status_code, 303)
        self.assertTrue(refused.headers["Location"].endswith("/my"))
        self.assertEqual(
            self.url_open(f"{url}?access_token={token}").json(),
            {"id": self.doc.id, "su": True},
        )

    def test_the_handler_gets_the_record_in_sudo_whoever_opened_it(self):
        self.doc.sudo().reader_ids = self.stranger
        self.authenticate("door_stranger", "door_stranger")
        res = self.url_open(f"/test_access_rights/shared_or_home/{self.doc.id}")
        self.assertEqual(res.json(), {"id": self.doc.id, "su": True})

    def test_a_link_opens_its_own_model_only_whatever_the_id(self):
        node = self.env["test_access_right.graph_node"].sudo().create({"name": "n"})
        _link, token = self._issue()
        res = self.url_open(
            f"/test_access_rights/node/{self.doc.id}?access_token={token}"
        )
        self.assertEqual(res.status_code, 404)
        foreign = self.url_open(
            f"/test_access_rights/node/{node.id}?access_token={token}"
        )
        self.assertEqual(foreign.status_code, 404)

    def test_a_link_for_signed_in_people_sends_a_visitor_to_login(self):
        _link, token = self._issue(audience="signed_in")
        res = self.url_open(
            f"/test_access_rights/shared/{self.doc.id}?access_token={token}",
            allow_redirects=False,
        )
        self.assertEqual(res.status_code, 303)
        self.assertIn("/web/login", res.headers["Location"])
