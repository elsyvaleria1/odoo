from datetime import timedelta
from urllib.parse import parse_qs

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.base.models.access_link import hash_token


@tagged("post_install", "-at_install", "access_link")
class TestInvitationLinks(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["slide.channel"].create(
            {
                "name": "Invitation course",
                "visibility": "members",
                "enroll": "invite",
                "is_published": True,
            }
        )
        cls.invited, cls.other = cls.env["slide.channel.partner"].create(
            [
                {
                    "channel_id": cls.channel.id,
                    "partner_id": cls.env["res.partner"]
                    .create({"name": name, "email": f"{name}@example.com"})
                    .id,
                    "member_status": "invited",
                    "last_invitation_date": fields.Datetime.now(),
                }
                for name in ("invited_one", "invited_two")
            ]
        )

    def _visit(self, member, token):
        self.authenticate(None, None)
        response = self.url_open(
            f"/slides/{self.channel.id}/invite?invite_partner_id="
            f"{member.partner_id.id}&invite_hash={token}",
            allow_redirects=False,
        )
        return parse_qs(self.parse_http_location(response.headers["Location"]).query)

    def _link(self, member):
        return (
            self.env["access.link"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "slide.channel.partner"),
                    ("res_id", "=", member.id),
                ]
            )
        )

    def test_an_invitation_is_a_link_in_the_members_name_while_it_is_pending(self):
        self.invited._issue_invitation_links()
        link = self._link(self.invited)
        self.assertEqual(
            (len(link), link.partner_id, link.role, link.cause),
            (1, self.invited.partner_id, "view", "invitation"),
        )
        self.assertAlmostEqual(
            link.date_to,
            self.invited.last_invitation_date + relativedelta(months=3),
            delta=timedelta(seconds=5),
        )
        token = parse_qs(self.invited.invitation_link.split("?", 1)[1])["invite_hash"][
            0
        ]
        self.assertEqual(link.token_hash, hash_token(token))
        self.assertNotIn("invite_error", self._visit(self.invited, token))

    def test_a_token_opens_its_own_invitation_only(self):
        (self.invited | self.other)._issue_invitation_links()
        token = parse_qs(self.invited.invitation_link.split("?", 1)[1])["invite_hash"][
            0
        ]
        self.assertEqual(
            self._visit(self.other, token).get("invite_error"), ["hash_fail"]
        )
        self._link(self.invited).date_to = fields.Datetime.now() - timedelta(seconds=1)
        self.assertEqual(
            self._visit(self.invited, token).get("invite_error"), ["hash_fail"]
        )

    def test_a_member_with_an_account_is_sent_to_log_in_under_their_exact_login(self):
        user = new_test_user(
            self.env, login="learner+courses@example.com", groups="base.group_portal"
        )
        member = self.channel.sudo()._action_add_members(user.partner_id)
        member._issue_invitation_links()
        token = parse_qs(member.invitation_link.split("?", 1)[1])["invite_hash"][0]

        query = self._visit(member, token)

        self.assertEqual(query["auth_login"], ["learner+courses@example.com"])
        self.assertEqual(query["redirect"], [f"/slides/{self.channel.id}"])
