from odoo.tests.common import TransactionCase, tagged

GONE = "gone.module.model"


@tagged("post_install", "-at_install")
class TestDanglingResModel(TransactionCase):
    def _orphaned(self, name, with_content=True):
        vals = {"name": name, "type": "binary"}
        if with_content:
            vals["raw"] = b"before"
        document = self.env["document.document"].create(vals)
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE document_document SET res_model = %s, res_id = %s WHERE id = %s",
            (GONE, 42, document.id),
        )
        self.env.invalidate_all()
        self.assertNotIn(document.res_model, self.env)
        return document

    def test_reading_a_dangling_link_answers_rather_than_raises(self):
        document = self._orphaned("orphan-read.txt")

        self.assertFalse(document.res_name)
        self.assertFalse(document.res_model_name)

    def test_filling_an_empty_orphaned_document_clears_the_link(self):
        document = self._orphaned("orphan-empty.txt", with_content=False)

        document.write({"raw": b"uploaded at last"})

        self.assertFalse(document.res_model, "the dangling link is dropped")
        self.assertFalse(document.res_id)
        self.assertTrue(document.attachment_id)
        self.assertEqual(
            (document.attachment_id.res_model, document.attachment_id.res_id),
            ("document.document", document.id),
            "and the new file belongs to the document itself",
        )

    def test_a_new_attachment_never_inherits_a_dead_model(self):
        document = self._orphaned("orphan-swap.txt", with_content=False)
        document.write({"raw": b"first"})
        replacement = self.env["ir.attachment"].create(
            {"name": "replacement.txt", "raw": b"second"}
        )

        document.write({"attachment_id": replacement.id})

        self.assertNotEqual(
            replacement.res_model, GONE, "the dead model must not be propagated"
        )
        self.assertEqual(
            replacement.raw,
            b"second",
            "and the replacement stays readable -- `ir.attachment` denies "
            "access to a row whose res_model it cannot access-check, so "
            "stamping a dead name on it makes the new version unreadable",
        )
        self.assertEqual(document.attachment_id, replacement)

    def test_a_live_link_is_left_alone(self):
        partner = self.env["res.partner"].create({"name": "still here"})
        document = self.env["document.document"].create(
            {"name": "linked.txt", "type": "binary"}
        )
        document.write({"res_model": "res.partner", "res_id": partner.id})

        document.write({"raw": b"content"})

        self.assertEqual(document.res_model, "res.partner")
        self.assertEqual(document.res_id, partner.id)
