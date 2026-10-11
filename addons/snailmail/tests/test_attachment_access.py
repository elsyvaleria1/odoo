import base64

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class testAttachmentAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "foo",
                "login": "foo",
                "email": "foo@bar.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_partner_manager").id,
                        ],
                    )
                ],
            }
        )
        cls.letter_defaults = {
            "model": cls.user.partner_id._name,
            "res_id": cls.user.partner_id.id,
            "partner_id": cls.user.partner_id.id,
        }

    def test_user_letter_attachment_without_res_fields(self):
        env_user = self.env(user=self.user)
        attachment = env_user["ir.attachment"].create(
            {"name": "foo", "datas": base64.b64encode(b"foo")}
        )
        letter = env_user["snailmail.letter"].create(
            {"attachment_id": attachment.id, **self.letter_defaults}
        )
        self.assertEqual(base64.b64decode(letter.attachment_datas), b"foo")
        attachment_2 = env_user["ir.attachment"].create(
            {"name": "foo", "datas": base64.b64encode(b"bar")}
        )
        letter.write({"attachment_id": attachment_2.id})
        self.assertEqual(base64.b64decode(letter.attachment_datas), b"bar")

    def test_user_letter_attachment_without_res_fields_created_by_admin(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "foo", "datas": base64.b64encode(b"foo")}
        )
        letter = self.env["snailmail.letter"].create(
            {"attachment_id": attachment.id, **self.letter_defaults}
        )

        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            attachment.with_user(self.user).datas
        self.assertEqual(
            base64.b64decode(letter.with_user(self.user).attachment_datas), b"foo"
        )

        attachment = self.env["ir.attachment"].create(
            {"name": "bar", "datas": base64.b64encode(b"bar")}
        )
        letter.write({"attachment_id": attachment.id})

        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            self.assertEqual(
                base64.b64decode(attachment.with_user(self.user).datas), b"bar"
            )
        self.assertEqual(
            base64.b64decode(letter.with_user(self.user).attachment_datas), b"bar"
        )

    def test_user_read_unallowed_attachment(self):
        autovacuum_job = self.env.ref("base.autovacuum_job")
        attachment_forbidden = self.env["ir.attachment"].create(
            {
                "name": "foo",
                "datas": base64.b64encode(b"foo"),
                "res_model": autovacuum_job._name,
                "res_id": autovacuum_job.id,
            }
        )
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            attachment_forbidden.with_user(self.user).datas
        with self.assertRaises(AccessError):
            letter = (
                self.env["snailmail.letter"]
                .with_user(self.user)
                .create(
                    {
                        "attachment_id": attachment_forbidden.id,
                        **self.letter_defaults,
                    }
                )
            )
            letter.attachment_datas

        attachment_tmp = (
            self.env["ir.attachment"]
            .with_user(self.user)
            .create(
                {
                    "name": "bar",
                    "datas": base64.b64encode(b"bar"),
                }
            )
        )
        letter = (
            self.env["snailmail.letter"]
            .with_user(self.user)
            .create(
                {
                    "attachment_id": attachment_tmp.id,
                    **self.letter_defaults,
                }
            )
        )
        with self.assertRaises(AccessError):
            letter.write({"attachment_id": attachment_forbidden.id})
            letter.attachment_datas
