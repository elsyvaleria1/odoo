from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests.common import TransactionCase


class TestDocumentsShare(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Document = cls.env["document.document"]
        Company = cls.env["res.company"]
        Website = cls.env["website"]
        cls.company_1 = Company.create({"name": "Company 1 with website"})
        cls.company_2 = Company.create({"name": "Company 2 with website"})
        cls.company_3 = Company.create({"name": "Company 3 with website"})
        cls.company_without_website = Company.create(
            {"name": "Company without website"}
        )

        cls.website_company_1 = Website.create(
            {
                "name": "Test company 1",
                "domain": "https://company_1.com",
                "company_id": cls.company_1.id,
            }
        )
        cls.website_company_2 = Website.create(
            {
                "name": "Test company 2",
                "domain": "https://website_2.com",
                "company_id": cls.company_2.id,
            }
        )
        cls.website_company_3 = Website.create(
            {
                "name": "Test company 3",
                "domain": "https://company_3.com",
                "company_id": cls.company_3.id,
            }
        )
        cls.website_main_company = cls.env.ref("base.main_company").website_id
        cls.website_main_company.domain = "https://main.company.com"

        cls.folder = Document.create({"name": "Folder no company", "type": "folder"})

        cls.default_domain = cls.company_without_website.get_base_url()

        cls.user = cls.env["res.users"].create(
            {
                "name": "User 1",
                "login": "user_1",
                "company_id": cls.company_1.id,
                "company_ids": [Command.set((cls.company_1 + cls.company_2).ids)],
            }
        )

    def test_share_url_domain(self):
        self.assertEqual(self.folder.website_id, self.website_main_company)
        self.assertSequenceEqual(
            self.folder.access_url[:24], "https://main.company.com"
        )

        self.folder.company_id = self.company_1
        self.assertSequenceEqual(self.folder.access_url[:21], "https://company_1.com")

        self.folder.company_id = self.company_without_website
        self.assertEqual(self.folder.website_id, self.website_main_company)
        self.assertTrue(self.folder.access_url.startswith("https://main.company.com"))

        self.website_main_company.domain = ""
        self.folder.company_id = self.company_without_website
        self.assertEqual(self.folder.website_id, self.website_main_company)
        self.assertTrue(self.folder.access_url.startswith(self.default_domain))

        self.folder.website_id = self.website_company_2
        self.assertTrue(self.folder.access_url.startswith("https://website_2.com"))

    def test_documents_website_id(self):
        self.assertEqual(self.website_company_1.company_id, self.company_1)
        self.assertEqual(self.website_company_2.company_id, self.company_2)
        self.assertEqual(self.website_company_3.company_id, self.company_3)

        with self.assertRaises(AccessError):
            self.env["document.document"].with_user(self.user).create(
                {
                    "name": "test1.txt",
                    "company_id": self.company_1.id,
                    "website_id": self.website_company_3.id,
                }
            )
        with self.assertRaises(AccessError):
            self.env["document.document"].with_user(self.user).create(
                {
                    "name": "test2.txt",
                    "website_id": self.website_company_3.id,
                }
            )
        self.env["document.document"].with_user(self.user).sudo().create(
            {
                "name": "test2.txt",
                "website_id": self.website_company_3.id,
            }
        )
        self.document_1 = (
            self.env["document.document"]
            .with_user(self.user)
            .create(
                {
                    "name": "doc1.txt",
                    "company_id": self.company_1.id,
                    "website_id": self.website_company_2.id,
                }
            )
        )
        self.document_2 = self.env["document.document"].create(
            {
                "name": "doc2.txt",
                "company_id": self.company_3.id,
            }
        )
        self.document_without_company = (
            self.env["document.document"]
            .with_user(self.user)
            .create(
                {
                    "website_id": self.website_company_1.id,
                }
            )
        )
        self.document_without_website = (
            self.env["document.document"]
            .with_user(self.user)
            .create(
                {
                    "company_id": self.company_1.id,
                    "website_id": False,
                }
            )
        )
        self.assertFalse(self.document_without_website.website_id)

        with self.assertRaises(AccessError):
            (self.document_1 + self.document_2).website_id = self.website_company_3.id
        self.document_2.website_id = self.website_company_3.id
        (
            self.document_2 + self.document_without_company
        ).website_id = self.website_company_2.id
