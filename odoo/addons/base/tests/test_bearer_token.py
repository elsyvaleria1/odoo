from odoo.db.schema import column_exists
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.base.models.mixin_bearer_token import hash_bearer_token


@tagged("post_install", "-at_install")
class TestBearerToken(TransactionCase):
    """An attachment's access token, kept as its hash and its sealed value."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.attachment = cls.env["ir.attachment"].create(
            {"name": "shared.txt", "raw": b"shared", "access_token": "right-token"}
        )

    def stored(self, attachment):
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT access_token_hash, access_token_sealed FROM ir_attachment "
            "WHERE id = %s",
            [attachment.id],
        )
        return self.env.cr.fetchone()

    def test_the_token_is_kept_sealed_never_in_clear(self):
        self.assertFalse(column_exists(self.env.cr, "ir_attachment", "access_token"))
        token_hash, sealed = self.stored(self.attachment)
        self.assertEqual(token_hash, hash_bearer_token("right-token"))
        self.assertNotIn("right-token", sealed)
        self.attachment.invalidate_recordset()
        self.assertEqual(self.attachment.access_token, "right-token")

    def test_the_token_opens_its_file_and_finds_it(self):
        self.assertTrue(self.attachment._can_return_content(None, "right-token"))
        with self.assertRaises(AccessError):
            self.attachment._can_return_content(None, "wrong-token")
        Attachment = self.env["ir.attachment"]
        self.assertEqual(
            Attachment.search([("access_token", "=", "right-token")]), self.attachment
        )
        self.assertNotIn(
            self.attachment, Attachment.search([("access_token", "!=", "right-token")])
        )
        self.assertFalse(Attachment.search([("access_token", "=", "wrong-token")]))

    def test_a_generated_token_is_kept_and_shown_again(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "new.txt", "raw": b"new"}
        )
        self.assertFalse(attachment.access_token)
        [token] = attachment.generate_access_token()
        attachment.invalidate_recordset()
        self.assertEqual(attachment.access_token, token)
        self.assertEqual(attachment.generate_access_token(), [token])
        self.assertEqual(self.stored(attachment)[0], hash_bearer_token(token))

    def test_tokens_are_kept_and_removed_together(self):
        attachments = self.env["ir.attachment"].create(
            [{"name": f"batch-{i}.txt", "raw": b"batch"} for i in range(3)]
        )
        tokens = attachments.generate_access_token()
        self.assertEqual(len(set(tokens)), 3)
        for attachment, token in zip(attachments, tokens, strict=True):
            self.assertEqual(self.stored(attachment)[0], hash_bearer_token(token))
        attachments.write({"access_token": False})
        for attachment in attachments:
            self.assertEqual(self.stored(attachment), (None, None))
            self.assertFalse(attachment.access_token)

    def test_a_copy_opens_with_the_same_token(self):
        copy = self.attachment.copy()
        self.assertEqual(copy.access_token, "right-token")
        self.assertTrue(copy._access_token_opens("right-token"))

    def test_a_token_sealed_under_another_secret_opens_but_is_not_shown(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "database.secret", "another secret"
        )
        self.env.registry.clear_cache()
        self.attachment.invalidate_recordset()
        self.assertFalse(self.attachment.access_token)
        self.assertTrue(self.attachment._access_token_opens("right-token"))
