import base64

from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tests.common import TransactionCase, tagged

GIF = b"R0lGODdhAQABAIAAAP///////ywAAAAAAQABAAACAkQBADs="
TEXT = base64.b64encode(bytes("workflow bridge product", "utf-8"))


@tagged("post_install", "-at_install")
class TestCaseDocumentsBridgeProduct(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder_test = cls.env["document.document"].create(
            {"name": "folder_test", "type": "folder"}
        )
        cls.company_test = cls.env["res.company"].create(
            {
                "name": "test bridge products",
                "product_folder_id": cls.folder_test.id,
                "documents_product_settings": False,
            }
        )
        cls.template_test = cls.env["product.template"].create(
            {
                "name": "template_test",
                "company_id": cls.company_test.id,
            }
        )
        cls.product_test = cls.template_test.product_variant_id
        cls.template_test_1 = cls.env["product.template"].create(
            {
                "name": "template_test_1",
                "company_id": cls.company_test.id,
            }
        )
        cls.product_test_1 = cls.template_test_1.product_variant_id
        cls.template_test_2 = cls.env["product.template"].create(
            {
                "name": "Box",
                "company_id": cls.company_test.id,
            }
        )
        cls.product_test_2 = cls.template_test_2.product_variant_id
        cls.attachment_txt_two = cls.env["ir.attachment"].create(
            {
                "datas": TEXT,
                "name": "fileTextTwo.txt",
                "mimetype": "text/plain",
            }
        )
        cls.attachment_gif_two = cls.env["ir.attachment"].create(
            {
                "datas": GIF,
                "name": "fileTwoGif.gif",
                "mimetype": "image/gif",
            }
        )
        cls.attachment_gif = cls.env["ir.attachment"].create(
            {
                "datas": GIF,
                "name": "fileGif.gif",
                "mimetype": "image/gif",
            }
        )

    def test_bridge_folder_product_settings_on_write(self):
        self.company_test.write({"documents_product_settings": True})

        self.attachment_gif_two.write(
            {"res_model": "product.product", "res_id": self.product_test.id}
        )
        self.attachment_txt_two.write(
            {"res_model": "product.template", "res_id": self.template_test.id}
        )

        txt_doc = self.env["document.document"].search(
            [("attachment_id", "=", self.attachment_txt_two.id)]
        )
        gif_doc = self.env["document.document"].search(
            [("attachment_id", "=", self.attachment_gif_two.id)]
        )

        self.assertEqual(
            txt_doc.folder_id,
            self.folder_test,
            "the text two document should have a folder",
        )
        self.assertEqual(
            gif_doc.folder_id,
            self.folder_test,
            "the gif two document should have a folder",
        )

    def _products_search(self, record, field_name):
        self.company_test.write({"documents_product_settings": True})
        self.attachment_gif_two.write(
            {
                "res_model": record._name,
                "res_id": record[0].id,
            }
        )
        self.attachment_txt_two.write(
            {
                "res_model": record._name,
                "res_id": record[1].id,
            }
        )
        self.attachment_gif.write(
            {
                "res_model": record._name,
                "res_id": record[2].id,
            }
        )

        docs = self.env["document.document"].search(
            [("res_id", "in", record.ids), ("res_model", "=", record._name)], order="id"
        )
        docs.flush_recordset()
        unlinked_doc = self.env["document.document"].create(
            {
                "name": "unlinked.txt",
                "attachment_id": self.env["ir.attachment"]
                .create(
                    {
                        "datas": TEXT,
                        "name": "unlinked.txt",
                    }
                )
                .id,
            }
        )
        owned = Domain("id", "in", (docs | unlinked_doc).ids)
        cases = [
            ([(field_name, "ilike", "template")], docs[0:2]),
            (
                [(field_name, "not ilike", "template"), (field_name, "!=", False)],
                docs[2],
            ),
            ([(field_name, "=", "template_test")], docs[0]),
            (
                [(field_name, "!=", "template_test"), (field_name, "!=", False)],
                docs[1:],
            ),
            ([(field_name, "=", record[0].id)], docs[0]),
            ([(field_name, "=", True)], docs),
            ([(field_name, "=", False)], unlinked_doc),
            ([(field_name, "in", record.ids)], docs),
            (
                [(field_name, "not in", record.ids + [False])],
                self.env["document.document"],
            ),
            (
                [
                    "|",
                    (field_name, "in", [record[2].id]),
                    (field_name, "ilike", "template"),
                ],
                docs,
            ),
        ]
        for domain, result in cases:
            with self.subTest(domain=domain):
                self.assertEqual(
                    self.env["document.document"].search(owned & Domain(domain)), result
                )

    def test_product_template_document_search(self):
        product_templates = (
            self.template_test + self.template_test_1 + self.template_test_2
        )
        return self._products_search(product_templates, "product_template_id")

    def test_product_product_document_search(self):
        products = self.product_test + self.product_test_1 + self.product_test_2
        return self._products_search(products, "product_id")

    def test_bridge_folder_product_settings_default_company(self):
        company_test = self.env["res.company"].create(
            {
                "name": "test bridge products two",
                "product_folder_id": self.folder_test.id,
                "documents_product_settings": True,
            }
        )
        test_user = self.env["res.users"].create(
            {
                "name": "documents test documents user",
                "login": "dtdu",
                "email": "dtdu@yourcompany.com",
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.ref("document.group_documents_user"),
                            self.ref("base.group_system"),
                        ],
                    )
                ],
                "company_ids": [(6, 0, [company_test.id])],
                "company_id": company_test.id,
            }
        )
        template_test = self.env["product.template"].create(
            {
                "name": "template_test",
            }
        )
        self.attachment_txt_two.with_user(test_user).write(
            {
                "res_model": "product.template",
                "res_id": template_test.id,
            }
        )
        txt_doc = self.env["document.document"].search(
            [("attachment_id", "=", self.attachment_txt_two.id)]
        )
        self.assertEqual(
            txt_doc.folder_id,
            self.folder_test,
            "the text two document should have a folder",
        )

        product_test = self.env["product.product"].create(
            {
                "name": "product_test",
            }
        )
        self.attachment_gif_two.with_user(test_user).write(
            {
                "res_model": "product.product",
                "res_id": product_test.id,
            }
        )
        gif_doc = self.env["document.document"].search(
            [("attachment_id", "=", self.attachment_gif_two.id)]
        )
        self.assertEqual(
            gif_doc.folder_id,
            self.folder_test,
            "the gif two document should have a folder",
        )

    def test_default_res_id_model(self):
        self.company_test.write({"documents_product_settings": True})

        attachment = (
            self.env["ir.attachment"]
            .with_context(
                default_res_id=self.product_test.id,
                default_res_model=self.product_test._name,
            )
            .create(
                {
                    "datas": GIF,
                    "name": "fileTwoGif.gif",
                    "mimetype": "image/gif",
                }
            )
        )
        document = self.env["document.document"].search(
            [("attachment_id", "=", attachment.id)]
        )
        self.assertTrue(
            document, "It should have created a document from default values"
        )

    def test_create_product_from_workflow(self):
        document_gif = self.env["document.document"].create(
            {
                "datas": GIF,
                "name": "file.gif",
                "mimetype": "image/gif",
                "folder_id": self.folder_test.id,
            }
        )

        action = document_gif.create_product_template()
        new_product = self.env["product.template"].browse([action["res_id"]])

        self.assertEqual(document_gif.res_model, "product.template")
        self.assertEqual(document_gif.res_id, new_product.id)
        self.assertEqual(new_product.image_1920, document_gif.datas)

    def test_product_search_does_not_confuse_id_one_with_the_any_sentinel(self):
        Document = self.env["document.document"]
        first, last = self.env["product.template"].create(
            [
                {"name": "sentinel_first"},
                {"name": "sentinel_last"},
            ]
        )
        documents = Document.create(
            [
                {
                    "name": "sentinel_%s.txt" % template.id,
                    "attachment_id": self.env["ir.attachment"]
                    .create(
                        {
                            "datas": TEXT,
                            "name": "sentinel_%s.txt" % template.id,
                        }
                    )
                    .id,
                    "res_model": "product.template",
                    "res_id": template.id,
                }
                for template in (first, last)
            ]
        )
        documents.flush_recordset()
        doc_first, doc_last = documents
        owned = Domain("id", "in", documents.ids)

        self.assertEqual(
            Document.search(owned & Domain("product_template_id", "in", [first.id])),
            doc_first,
        )
        self.assertNotIn(
            doc_last,
            Document.search(owned & Domain("product_template_id", "in", [1, first.id])),
            "an id of 1 in the value set widened the search to every product document",
        )
        self.assertNotIn(
            doc_last,
            Document.search(owned & Domain("product_template_id", "=", 1)),
            "'= 1' matched a document whose product template is not id 1",
        )

    def test_create_product_template_requires_a_document(self):
        Template = self.env["product.template"]
        before = Template.search_count([])
        with self.assertRaises(UserError):
            self.env["document.document"].browse([]).create_product_template()
        self.env.flush_all()
        self.assertEqual(
            Template.search_count([]),
            before,
            "an empty recordset created a stray product.template",
        )

    def test_create_product_template_ignores_the_caller_defaults(self):
        document = self.env["document.document"].create(
            {
                "name": "spec.txt",
                "attachment_id": self.env["ir.attachment"]
                .create(
                    {
                        "datas": TEXT,
                        "name": "spec.txt",
                    }
                )
                .id,
            }
        )
        poisoned = document.with_context(default_type="folder", default_active=False)

        action = poisoned.create_product_template()

        product = self.env["product.template"].browse(action["res_id"])
        self.assertEqual(product.type, "consu")
        self.assertTrue(product.active, "the product was created archived")
        self.assertNotIn("default_type", action["context"])
        self.assertNotIn("default_active", action["context"])
