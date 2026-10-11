from odoo.tests import tagged

from odoo.addons.mail.tests.common_controllers import MailControllerBinaryCommon


@tagged("-at_install", "post_install", "mail_controller")
class TestPublicBinaryController(MailControllerBinaryCommon):
    def test_avatar_no_public(self):
        for source in (self.guest_2, self.user_employee_nopartner.partner_id):
            self._execute_subtests(
                source,
                (
                    (self.user_public, False),
                    (self.guest, False),
                    (self.user_portal, False),
                    (self.user_employee, True),
                ),
            )

    def test_avatar_private(self):
        document = self.env["mail.test.simple.unfollow"].create({"name": "Test"})
        self._post_message(document, self.user_employee_nopartner)
        self._execute_subtests(
            self.user_employee_nopartner.partner_id,
            (
                (self.user_public, False),
                (self.guest, False),
                (self.user_portal, False),
                (self.user_employee, True),
            ),
        )

    def test_avatar_public(self):
        document = self.env["mail.test.access.public"].create({"name": "Test"})
        for author, source in (
            (self.guest_2, self.guest_2),
            (self.user_employee_nopartner, self.user_employee_nopartner.partner_id),
        ):
            self._post_message(document, author)
            self._execute_subtests(
                source,
                (
                    (self.user_public, False),
                    (self.guest, False),
                    (self.user_portal, False),
                    (self.user_employee, True),
                ),
            )
