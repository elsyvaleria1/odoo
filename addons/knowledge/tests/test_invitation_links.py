from urllib.parse import urlparse

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install", "access_link")
class TestArticleInvitationLinks(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.article = cls.env["knowledge.article"].create(
            {"name": "Shared notes", "internal_permission": "write"}
        )
        guests = cls.env["res.partner"].create(
            [
                {"name": "Guest one", "email": "guest.one@example.com"},
                {"name": "Guest two", "email": "guest.two@example.com"},
            ]
        )
        cls.article._add_members(guests, "read")
        cls.guest, cls.other = (
            cls.article.article_member_ids.filtered(
                lambda member, partner=partner: member.partner_id == partner
            )
            for partner in guests
        )

    def _visit(self, member_id, token):
        self.authenticate(None, None)
        return self.url_open(
            f"/knowledge/article/invite/{member_id}/{token}", allow_redirects=False
        )

    def test_an_invitation_is_a_link_in_the_members_name(self):
        token = self.guest._get_invitation_token()
        link = (
            self.env["access.link"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "knowledge.article.member"),
                    ("res_id", "=", self.guest.id),
                ]
            )
        )
        self.assertEqual(
            (len(link), link.partner_id, link.cause),
            (1, self.guest.partner_id, "share"),
        )
        self.assertEqual(self.guest._get_invitation_token(), token, "reused")
        response = self._visit(self.guest.id, token)
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/", urlparse(response.headers["Location"]).path)
        self.assertEqual(self._visit(self.other.id, token).status_code, 404)
