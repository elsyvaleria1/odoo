from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import SQL, mute_logger


@tagged("post_install", "-at_install")
class TestModelMetadataAuthority(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env,
            login="metadata_access_manager",
            groups="base.group_user,base.group_erp_manager",
        )
        cls.system_group = cls.env.ref("base.group_system")
        cls.partner_model_id = cls.env["ir.model"]._get_id("res.partner")

    def test_an_access_manager_cannot_write_compute_code(self):
        code = (
            "for record in self:\n"
            "    record['x_audit_code'] = 'x'\n"
            "self.env['res.users'].browse(%d).write("
            "{'group_ids': [(4, self.env.ref('base.group_system').id)]})"
        ) % self.manager.id
        with self.assertRaises(AccessError):
            self.env["ir.model.fields"].with_user(self.manager).create(
                {
                    "model_id": self.partner_model_id,
                    "name": "x_audit_code",
                    "field_description": "Audit code",
                    "ttype": "char",
                    "store": True,
                    "depends": "name",
                    "compute": code,
                }
            )
        self.env.invalidate_all()
        self.assertNotIn(self.system_group, self.manager.all_group_ids)

    def test_an_access_manager_cannot_rewrite_an_existing_compute(self):
        field = self.env["ir.model.fields"].create(
            {
                "model_id": self.partner_model_id,
                "name": "x_audit_plain",
                "field_description": "Audit plain",
                "ttype": "char",
                "store": False,
                "compute": "for record in self:\n    record['x_audit_plain'] = 'x'",
            }
        )
        with self.assertRaises(AccessError):
            field.with_user(self.manager).write(
                {"compute": "for record in self:\n    record['x_audit_plain'] = 'y'"}
            )

    def test_an_access_manager_still_creates_a_plain_field(self):
        field = (
            self.env["ir.model.fields"]
            .with_user(self.manager)
            .create(
                {
                    "model_id": self.partner_model_id,
                    "name": "x_audit_label",
                    "field_description": "Audit label",
                    "ttype": "char",
                }
            )
        )
        self.assertEqual(field.sudo().state, "manual")

    def test_an_administrator_writes_compute_code(self):
        field = self.env["ir.model.fields"].create(
            {
                "model_id": self.partner_model_id,
                "name": "x_audit_admin",
                "field_description": "Audit admin",
                "ttype": "char",
                "store": False,
                "compute": "for record in self:\n    record['x_audit_admin'] = 'ok'",
            }
        )
        self.assertEqual(self.env.ref("base.partner_admin")[field.name], "ok")

    def test_an_access_manager_cannot_repoint_an_external_id(self):
        public_user = self.env.ref("base.public_user")
        data = (
            self.env["ir.model.data"]
            .with_user(self.manager)
            .search([("module", "=", "base"), ("name", "=", "public_user")])
        )
        self.assertTrue(data)
        with self.assertRaises(AccessError):
            data.write({"res_id": self.env.ref("base.user_admin").id})
        self.env.invalidate_all()
        self.assertEqual(self.env.ref("base.public_user"), public_user)

    def test_an_access_manager_cannot_drop_a_database_constraint(self):
        constraint = self.env["ir.model.constraint"].search(
            [("name", "=", "res_users_login_key")]
        )
        self.assertTrue(constraint)
        with mute_logger("odoo.addons.base.models.ir_model_reflection"):
            with self.assertRaises(AccessError):
                constraint.with_user(self.manager).unlink()
        self.assertTrue(
            self.env.execute_query(
                SQL(
                    "SELECT 1 FROM pg_constraint WHERE conname = %s",
                    "res_users_login_key",
                )
            )
        )
