import base64
import io

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, users
from odoo.tools import mute_logger
from odoo.tools.pdf import BrandedFileWriter


class testAttachmentAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "foo",
                "login": "foo",
                "email": "foo@bar.com",
                "group_ids": [(6, 0, [cls.env.ref("sign.group_sign_user").id])],
            }
        )
        with io.BytesIO() as stream:
            BrandedFileWriter().write(stream)
            stream.seek(0)
            cls.pdf = base64.b64encode(stream.read())

    def test_user_template_attachment_without_res_fields(self):
        env_user = self.env(user=self.user)
        attachment = env_user["ir.attachment"].create(
            {"name": "foo", "datas": self.pdf}
        )
        template = env_user["sign.template"].create({})
        document = env_user["sign.document"].create(
            {
                "attachment_id": attachment.id,
                "template_id": template.id,
            }
        )
        self.assertEqual(document.datas, self.pdf)
        attachment_2 = env_user["ir.attachment"].create(
            {"name": "foo", "datas": self.pdf}
        )
        document.write({"attachment_id": attachment_2.id})
        self.assertEqual(document.datas, self.pdf)

    def test_user_template_attachment_without_res_fields_created_by_admin(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "foo", "datas": self.pdf}
        )
        template = self.env["sign.template"].create({})
        document = self.env["sign.document"].create(
            {
                "attachment_id": attachment.id,
                "template_id": template.id,
            }
        )

        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            attachment.with_user(self.user).datas
        self.assertEqual(document.with_user(self.user).datas, self.pdf)

        attachment = self.env["ir.attachment"].create(
            {"name": "bar", "datas": self.pdf}
        )
        document.write({"attachment_id": attachment.id})

        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            self.assertEqual(attachment.with_user(self.user).datas, self.pdf)
        self.assertEqual(document.with_user(self.user).datas, self.pdf)

    def test_user_read_unallowed_attachment(self):
        autovacuum_job = self.env.ref("base.autovacuum_job")
        attachment_forbidden = self.env["ir.attachment"].create(
            {
                "name": "foo",
                "datas": self.pdf,
                "res_model": autovacuum_job._name,
                "res_id": autovacuum_job.id,
            }
        )
        self.env.invalidate_all()
        with self.assertRaises(AccessError):
            attachment_forbidden.with_user(self.user).datas
        with self.assertRaises(AccessError):
            template = self.env["sign.template"].create({})
            document = (
                self.env["sign.document"]
                .with_user(self.user)
                .create(
                    {
                        "attachment_id": attachment_forbidden.id,
                        "template_id": template.id,
                    }
                )
            )
            document.datas

        attachment_tmp = (
            self.env["ir.attachment"]
            .with_user(self.user)
            .create(
                {
                    "name": "bar",
                    "datas": self.pdf,
                }
            )
        )
        template = (
            self.env["sign.template"]
            .with_user(self.user)
            .create(
                {
                    "name": "test template",
                }
            )
        )
        document = (
            self.env["sign.document"]
            .with_user(self.user)
            .create(
                {
                    "attachment_id": attachment_tmp.id,
                    "template_id": template.id,
                }
            )
        )
        with self.assertRaises(AccessError):
            document.write({"attachment_id": attachment_forbidden.id})
            document.datas

    @users("foo")
    @mute_logger(
        "odoo.addons.base.models.ir_model",
        "odoo.addons.base.models.ir_access",
        "odoo.models",
    )
    def test_access_sign_user_fields(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(
            admin.env.user == self.user and not admin.env.su,
            "This test makes sense only if it is tested with employee access rights",
        )
        my_user = self.env["res.users"].browse(self.env.user.id)
        self.assertTrue(
            my_user.env.user == self.user and not my_user.env.su,
            "This test makes sense only if it is tested with employee access rights",
        )

        sign_user_fields = ["sign_signature", "sign_initials"]

        for field in sign_user_fields:
            admin.sudo()[field] = base64.b64encode(b"admin")

        signature = base64.b64encode(b"foo")
        for field in sign_user_fields:
            my_user[field] = signature
            self.assertEqual(
                my_user[field],
                signature,
                f"An employee must be able to read his own {field!r}",
            )
            with self.assertRaises(
                AccessError,
                msg=f"An employee must not be able to write {field!r} of another user",
            ):
                admin[field] = signature
            with self.assertRaises(
                AccessError,
                msg=f"An employee must not be able to read {field!r} of another user",
            ):
                admin[field]

            attachment_id = (
                self.env["ir.attachment"]
                .sudo()
                .search(
                    [
                        ("res_model", "=", "res.users"),
                        ("res_id", "=", admin.id),
                        ("res_field", "=", field),
                    ]
                )
                .id
            )

            with self.assertRaises(
                AccessError,
                msg=f"An employee must not be able to read the attachment related to the {field!r} of another user",
            ):
                self.env["ir.attachment"].browse(attachment_id).datas

    def test_user_sign_item(self):
        env_user = self.env(user=self.user)
        attachment = env_user["ir.attachment"].create(
            {"name": "foo", "datas": self.pdf}
        )
        attachment_2 = env_user["ir.attachment"].create(
            {"name": "foo", "datas": self.pdf}
        )
        template = env_user["sign.template"].create({})
        template_2 = self.env["sign.template"].create({})
        document = env_user["sign.document"].create(
            {
                "attachment_id": attachment.id,
                "template_id": template.id,
            }
        )
        document_2 = self.env["sign.document"].create(
            {
                "attachment_id": attachment_2.id,
                "template_id": template_2.id,
            }
        )

        sign_item = env_user["sign.item"].create(
            {
                "document_id": document.id,
                "type_id": self.env.ref("sign.sign_item_type_name").id,
                "posX": 0.190,
                "posY": 0.185,
                "width": 0.680,
                "height": 0.015,
            }
        )

        with self.assertRaises(AccessError):
            template_2.with_env(env_user).read(["name"])

        with self.assertRaises(AccessError):
            document_2.with_env(env_user).read(["name"])

        with self.assertRaises(AccessError):
            sign_item.template_id = template_2

        with self.assertRaises(AccessError):
            sign_item.document_id = document_2

        with self.assertRaises(AccessError):
            env_user["sign.item"].create(
                {
                    "document_id": document_2.id,
                    "type_id": self.env.ref("sign.sign_item_type_name").id,
                    "posX": 0.190,
                    "posY": 0.185,
                    "width": 0.680,
                    "height": 0.015,
                }
            )

        sign_item = env_user["sign.item"].create(
            {
                "document_id": document.id,
                "template_id": template_2.id,
                "type_id": self.env.ref("sign.sign_item_type_name").id,
                "posX": 0.190,
                "posY": 0.185,
                "width": 0.680,
                "height": 0.015,
            }
        )
        self.assertEqual(sign_item.template_id, template)
