from odoo.exceptions import AccessError
from odoo.tests import HttpCase, JsonRpcException, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestRpcRights(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.officer = new_test_user(
            cls.env,
            login="rights_officer",
            groups="base.group_user,website_slides.group_website_slides_officer",
        )
        cls.learner = new_test_user(
            cls.env, login="rights_learner", groups="base.group_portal"
        )
        cls.stranger = cls.env["res.partner"].create({"name": "Not asked"})
        cls.channel = (
            cls.env["slide.channel"]
            .with_user(cls.officer)
            .create(
                {
                    "name": "Rights course",
                    "enroll": "public",
                    "is_published": True,
                    "karma_slide_vote": 50,
                }
            )
        )
        cls.slide = (
            cls.env["slide.slide"]
            .with_user(cls.officer)
            .create(
                {
                    "name": "Rights lesson",
                    "channel_id": cls.channel.id,
                    "slide_category": "article",
                    "html_content": "<p>x</p>",
                    "is_published": True,
                }
            )
        )
        cls.channel.sudo()._action_add_members(cls.learner.partner_id)

    def _call(self, model, method, args):
        return self.call_jsonrpc(
            "/web/dataset/call_kw",
            {"model": model, "method": method, "args": args, "kwargs": {}},
        )

    @mute_logger("odoo.http")
    def test_a_learner_cannot_enroll_someone_else_by_granting_access(self):
        self.authenticate("rights_learner", "rights_learner")

        with self.assertRaises(JsonRpcException):
            self._call(
                "slide.channel",
                "action_grant_access",
                [[self.channel.id], self.stranger.id],
            )

        self.assertNotIn(self.stranger, self.channel.sudo().partner_ids)

    @mute_logger("odoo.http")
    def test_a_vote_needs_the_karma_through_any_door(self):
        self.authenticate("rights_learner", "rights_learner")

        with self.assertRaises(JsonRpcException):
            self._call("slide.slide", "action_like", [[self.slide.id]])

        self.assertEqual(self.slide.likes, 0)

    def test_an_upload_into_another_courses_section_is_refused(self):
        other = self.env["slide.channel"].create({"name": "Elsewhere"})
        foreign = self.env["slide.slide"].create(
            {"name": "Foreign section", "channel_id": other.id, "is_category": True}
        )
        self.authenticate("rights_officer", "rights_officer")

        result = self.call_jsonrpc(
            "/slides/add_slide",
            {
                "channel_id": self.channel.id,
                "name": "Misplaced",
                "slide_category": "article",
                "category_id": [foreign.id],
            },
        )

        self.assertIn("error", result)
        self.assertFalse(
            self.env["slide.slide"].search_count([("name", "=", "Misplaced")])
        )

    def test_an_employee_without_rights_on_the_course_cannot_enroll_others(self):
        employee = new_test_user(
            self.env, login="rights_employee", groups="base.group_user"
        )
        wizard = (
            self.env["wizard.slide.channel.add.attendee"]
            .with_user(employee)
            .create(
                {
                    "channel_id": self.channel.id,
                    "enroll_mode": True,
                    "partner_ids": [(6, 0, self.stranger.ids)],
                }
            )
        )

        with self.assertRaises(AccessError):
            wizard.action_invite()

        self.assertNotIn(self.stranger, self.channel.sudo().partner_ids)

    def test_anyone_still_joins_an_open_course_themselves(self):
        employee = new_test_user(
            self.env, login="rights_joiner", groups="base.group_user"
        )

        self.channel.with_user(employee)._action_add_members(employee.partner_id)

        self.assertIn(employee.partner_id, self.channel.sudo().partner_ids)
