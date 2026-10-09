from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMailGroupUi(HttpCase):
    def test_archives_filter_in_place(self):
        group = self.env["mail.group"].create(
            {"name": "PN List", "alias_name": "pn.list", "access_mode": "public"}
        )
        messages = self.env["mail.group.message"].create(
            [
                {
                    "subject": subject,
                    "mail_group_id": group.id,
                    "moderation_status": "accepted",
                    "email_from": '"Ada" <ada@example.com>',
                }
                for subject in ("PN January", "PN March")
            ]
        )
        for message, date in zip(messages, ("2026-01-15", "2026-03-10"), strict=True):
            self.env.cr.execute(
                "UPDATE mail_group_message SET create_date = %s WHERE id = %s",
                (date, message.id),
            )
        messages.invalidate_recordset(["create_date"])
        self.start_tour(
            f"/groups/{self.env['ir.http']._slug(group)}?mode=date",
            "mail_group_archives_partial_navigation",
        )
