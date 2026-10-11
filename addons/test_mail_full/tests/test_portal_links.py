from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit

from odoo import fields
from odoo.tests import counting_statements, tagged
from odoo.tools import SQL, mute_logger

from odoo.addons.base.models.access_link import hash_token
from odoo.addons.test_mail_full.tests.test_portal import TestPortal

LEGACY_TOKEN = "3f2b9c1e-7a4d-4e8b-9f60-2c5d8a1b7e93"


@tagged("-at_install", "post_install", "portal", "access_link")
class TestPortalLinks(TestPortal):
    def _page(self, token, **params):
        query = "&".join(f"{key}={value}" for key, value in params.items())
        return self.url_open(
            f"/my/test_portal_records/{self.record_portal.id}?token={token}&{query}"
        )

    def _links(self, record=None):
        record = record or self.record_portal
        return (
            self.env["access.link"]
            .sudo()
            .search([("res_model", "=", record._name), ("res_id", "=", record.id)])
        )

    def _carry_over(self, token):
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO access_link (res_model, res_id, role, audience,
                       token_hash, token_hint, date_to, cause, legacy_source,
                       partner_id, use_count, expiry_waived)
                VALUES (%s, %s, 'comment', 'anyone', %s, %s,
                        now() + interval '365 days', 'migration',
                        'mail.test.portal.access_token', %s, 0, false)
                """,
                self.record_portal._name,
                self.record_portal.id,
                hash_token(token),
                token[:4],
                self.record_portal.partner_id.id,
            )
        )

    def test_the_customer_token_is_a_link_stored_as_its_hash(self):
        token = self.record_portal.access_token
        link = self._links()
        self.assertEqual(len(link), 1)
        self.assertEqual(
            (link.partner_id, link.role, link.cause),
            (self.partner_1, "comment", "notification"),
        )
        self.assertAlmostEqual(
            link.date_to,
            fields.Datetime.now() + timedelta(days=365),
            delta=timedelta(minutes=5),
        )
        self.env.cr.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'mail_test_portal' AND column_name = 'access_token'"
        )
        self.assertEqual(self.env.cr.fetchone()[0], 0, "no token is kept in clear")
        self.assertEqual(self.record_portal._portal_get_or_create_token(), token)
        other = self.record_portal._portal_get_or_create_token(self.partner_2)
        self.assertNotEqual(other, token, "another recipient gets another link")
        self.assertEqual(len(self._links()), 2)

    def test_a_token_opens_its_record_and_nothing_else(self):
        token = self.record_portal.access_token
        self.assertTrue(self.record_portal._portal_token_opens(token))
        other = self.env["mail.test.portal"].create({"name": "Other"})
        self.assertFalse(other._portal_token_opens(token))
        self.assertFalse(self.record_portal._portal_token_opens(token[:-1] + "x"))
        self.assertFalse(self.record_portal._portal_token_opens("é" * 36))

    def test_a_revoked_or_expired_link_opens_nothing(self):
        token = self.record_portal.access_token
        self._links().sudo().date_to = fields.Datetime.now() - timedelta(seconds=1)
        self.assertFalse(self.record_portal._portal_token_opens(token))
        self._links().sudo().date_to = fields.Datetime.now() + timedelta(days=1)
        self.assertTrue(self.record_portal._portal_token_opens(token))
        self.env["access.link"]._revoke_record_links(self.record_portal, "test")
        self.assertFalse(self.record_portal._portal_token_opens(token))
        self.record_portal.invalidate_recordset(["access_token"])
        self.assertFalse(self.record_portal.access_token)

    @mute_logger("odoo.http")
    def test_a_token_from_before_the_upgrade_still_opens_and_posts(self):
        self._carry_over(LEGACY_TOKEN)
        pid = self.partner_2.id
        legacy_hash = self.record_portal._sign_token(pid, token=LEGACY_TOKEN)
        self.authenticate(None, None)
        opened = f'data-res_id="{self.record_portal.id}"'
        self.assertIn(opened, self._page(LEGACY_TOKEN).text)
        self.assertNotIn(opened, self._page(LEGACY_TOKEN[:-1] + "0").text)

        res = self.url_open(
            url=f"{self.record_portal.get_base_url()}/mail/message/post",
            json={
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    "post_data": {"body": "Still here"},
                    "token": LEGACY_TOKEN,
                    "hash": legacy_hash,
                    "pid": pid,
                },
            },
        )
        res.raise_for_status()
        self.assertNotIn("error", res.json())
        self.assertEqual(self.record_portal.message_ids[0].author_id, self.partner_2)

        forged = self.record_portal._sign_token(pid, token="not-the-token")
        res = self.url_open(
            url=f"{self.record_portal.get_base_url()}/mail/message/post",
            json={
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    "post_data": {"body": "Forged"},
                    "token": LEGACY_TOKEN,
                    "hash": forged,
                    "pid": pid,
                },
            },
        )
        forged_post = self.record_portal.message_ids[0]
        self.assertNotEqual(forged_post.author_id, self.partner_2)
        self.assertEqual(forged_post.author_id, self.record_portal.partner_id)

    def test_a_mail_link_from_before_the_upgrade_lands_on_the_page_with_its_token(
        self,
    ):
        self._carry_over(LEGACY_TOKEN)
        self.authenticate(None, None)
        links = len(self._links())
        response = self.url_open(
            f"/mail/view?model={self.record_portal._name}"
            f"&res_id={self.record_portal.id}&access_token={LEGACY_TOKEN}"
        )
        self.assertIn(f"access_token={LEGACY_TOKEN}", response.url)
        self.assertEqual(len(self._links()), links, "a visit issues no link")

    @mute_logger("odoo.http")
    def test_a_recipient_posts_as_the_partner_its_link_was_issued_to(self):
        token = self.record_portal._portal_get_or_create_token(self.partner_2)
        self.authenticate(None, None)
        res = self.url_open(
            url=f"{self.record_portal.get_base_url()}/mail/message/post",
            json={
                "params": {
                    "thread_model": self.record_portal._name,
                    "thread_id": self.record_portal.id,
                    "post_data": {"body": "From the second recipient"},
                    "token": token,
                },
            },
        )
        res.raise_for_status()
        self.assertNotIn("error", res.json())
        self.assertEqual(self.record_portal.message_ids[0].author_id, self.partner_2)

    def test_the_link_the_customer_is_mailed_posts_as_the_customer(self):
        groups = self.record_portal._notify_get_recipients_groups(
            self.env["mail.message"], False
        )
        url = next(
            data["button_access"]["url"]
            for name, matches, data in groups
            if name == "portal_customer" and matches({"id": self.partner_1.id})
        )
        query = dict(parse_qsl(urlsplit(url).query))
        self.authenticate(None, None)
        for name, credentials in (
            ("token", {"token": query["access_token"]}),
            (
                "token and hash",
                {
                    "token": query["access_token"],
                    "hash": query["hash"],
                    "pid": query["pid"],
                },
            ),
        ):
            with self.subTest(name):
                body = f"From the customer's mail, with its {name}"
                res = self.url_open(
                    url=f"{self.record_portal.get_base_url()}/mail/message/post",
                    json={
                        "params": {
                            "thread_model": self.record_portal._name,
                            "thread_id": self.record_portal.id,
                            "post_data": {"body": body},
                            **credentials,
                        },
                    },
                )
                self.assertNotIn("error", res.json())
                self.env.invalidate_all()
                self.assertIn(body, self.record_portal.message_ids[0].body)
                self.assertEqual(
                    self.record_portal.message_ids[0].author_id, self.partner_1
                )

    def test_a_list_reads_its_tokens_in_as_many_queries_as_one_record(self):
        records = self.env["mail.test.portal"].create(
            [{"name": f"Listed {i}", "partner_id": self.partner_1.id} for i in range(6)]
        )
        tokens = [record._portal_get_or_create_token() for record in records]

        def cost(listed):
            self.env.invalidate_all()
            listed = listed.browse(listed.ids)
            with counting_statements(self.env.cr) as statements:
                self.assertEqual(listed.mapped("access_token"), tokens[: len(listed)])
                return statements.count

        cost(records)
        self.assertEqual(cost(records[:1]), cost(records))

    def test_nobody_writes_a_token(self):
        self.record_portal.write({"access_token": "A" * 36})
        self.record_portal.invalidate_recordset(["access_token"])
        self.assertNotEqual(self.record_portal.access_token, "A" * 36)
        self.assertFalse(self.record_portal._portal_token_opens("A" * 36))
