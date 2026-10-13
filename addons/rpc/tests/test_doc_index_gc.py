import base64

from odoo.tests import TransactionCase, tagged

from odoo.addons.rpc.tools.cache import doc_cache_generation


@tagged("post_install", "-at_install")
class TestDocIndexGc(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Attachment = cls.env["ir.attachment"]
        cls.generation = doc_cache_generation(cls.env)

    def _doc_index(self, generation, suffix):
        return self.Attachment.create(
            {
                "name": f"odoo-doc-index-{generation}-{suffix}.json",
                "datas": base64.b64encode(b"{}"),
            }
        )

    def test_gc_removes_stale_index_keeps_current(self):
        stale = self._doc_index("0000000000", "en_US")
        fresh = self._doc_index(self.generation, "en_US")
        self.Attachment._gc_doc_index()
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_gc_keeps_every_audience_of_the_current_generation(self):
        kept = self._doc_index(self.generation, "en_US") | self._doc_index(
            self.generation, "fr_FR"
        )
        self.Attachment._gc_doc_index()
        self.assertEqual(len(kept.exists()), 2)

    def test_gc_noop_without_indexes(self):
        self.Attachment.search([("name", "like", R"odoo-doc-index-%")]).unlink()
        self.Attachment._gc_doc_index()

    def test_gc_ignores_unrelated_attachments(self):
        bystander = self.Attachment.create(
            {"name": "odoo-doc-index.json", "datas": base64.b64encode(b"{}")}
        )
        self.Attachment._gc_doc_index()
        self.assertTrue(bystander.exists())
