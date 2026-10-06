from odoo.modules.module import get_module_path, load_script
from odoo.tests import tagged

from .sign_request_common import SignRequestCommon


@tagged("post_install", "-at_install")
class TestHashedSmsCodesAndVersionedLogsMigration(SignRequestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = load_script(
            f"{get_module_path('sign')}/migrations/1.7/pre-migrate.py",
            "sign_1_7_pre_migrate",
        )

    def test_the_1_6_schema_is_carried_over(self):
        sign_request = self.create_sign_request_1_role_sms_auth(
            self.partner_1, self.env["res.partner"]
        )
        sign_request.request_item_ids.sudo().sign(self.single_signer_sign_values)
        item = sign_request.request_item_ids
        self.env.flush_all()
        cr = self.env.cr
        cr.execute("ALTER TABLE sign_log DROP COLUMN hash_version")
        cr.execute("ALTER TABLE sign_log ADD COLUMN token varchar")
        cr.execute("ALTER TABLE sign_request_item DROP COLUMN sms_verified_date")
        cr.execute("ALTER TABLE sign_request_item DROP COLUMN sms_verified_number")
        cr.execute("ALTER TABLE sign_request_item ADD COLUMN sms_token varchar")
        cr.execute(
            "UPDATE sign_request_item SET sms_token = '123456', sms_number = '+32499000003'"
            " WHERE id = %s",
            [item.id],
        )

        self.script.migrate(cr, "1.6")
        self.script.migrate(cr, "1.6")

        cr.execute("SELECT DISTINCT hash_version FROM sign_log")
        self.assertEqual(cr.fetchall(), [(1,)])
        for table, column in (
            ("sign_log", "token"),
            ("sign_request_item", "sms_token"),
        ):
            cr.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                [table, column],
            )
            self.assertFalse(cr.fetchall(), f"{table}.{column} is dropped")
        cr.execute(
            "SELECT sms_verified_date, sms_verified_number FROM sign_request_item"
            " WHERE id = %s",
            [item.id],
        )
        verified_date, verified_number = cr.fetchone()
        self.assertTrue(verified_date)
        self.assertEqual(verified_number, "+32499000003")
        self.env.invalidate_all()
