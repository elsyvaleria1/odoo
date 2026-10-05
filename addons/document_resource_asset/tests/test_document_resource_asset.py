from unittest.mock import patch

from psycopg.errors import UniqueViolation

from odoo.tests.common import TransactionCase, new_test_user


class TestAssetDocuments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.kind = cls.env.ref("resource_asset.kind_vehicle")
        cls.asset = cls.env["resource.asset"].create(
            {"name": "Van", "kind_id": cls.kind.id}
        )
        cls.setting = cls.env["resource.kind.document"].create(
            {"kind_id": cls.kind.id, "company_id": cls.env.company.id}
        )

    def test_a_kind_files_its_documents_in_its_own_folder(self):
        self.assertTrue(self.setting.folder_id, "a kind's folder is made on demand")
        self.assertEqual(self.asset._get_document_folder(), self.setting.folder_id)
        self.assertTrue(self.asset._check_create_documents())
        self.assertTrue(self.asset.document_centralized)

    def test_a_kind_that_centralizes_nothing_files_nothing(self):
        self.setting.centralize = False
        self.asset.invalidate_recordset()
        self.assertFalse(self.asset._check_create_documents())
        self.assertFalse(self.asset.document_centralized)
        self.assertTrue(self.asset.action_view_documents() is True)

    def test_a_kind_without_a_row_files_nothing(self):
        other = self.env["resource.asset"].create(
            {"name": "Drill", "kind_id": self.env.ref("resource_asset.kind_tool").id}
        )
        self.assertFalse(other._get_document_folder())
        self.assertFalse(other._check_create_documents())

    def test_one_row_per_kind_and_company(self):
        with self.assertRaises(UniqueViolation):
            with self.env.cr.savepoint():
                self.env["resource.kind.document"].create(
                    {"kind_id": self.kind.id, "company_id": self.env.company.id}
                )

    def test_the_tags_of_the_kind_reach_the_document(self):
        tag = self.env["document.tag"].create({"name": "Fleet doc"})
        self.setting.tag_ids = tag
        self.asset.invalidate_recordset()
        self.assertEqual(self.asset._get_document_tags(), tag)

    def test_a_kind_folder_is_never_someone_s_own_folder(self):
        kind = self.env["resource.kind"].create({"name": "Trailer", "code": "trailer"})
        someone = new_test_user(
            self.env,
            "trailer_owner",
            groups="base.group_user,document.group_documents_user",
        )
        personal = (
            self.env["document.document"]
            .with_user(someone)
            .create({"name": "Trailer", "type": "folder", "user_folder_id": "MY"})
        )
        self.assertTrue(personal.owner_id)
        setting = self.env["resource.kind.document"].create(
            {"kind_id": kind.id, "company_id": self.env.company.id}
        )
        self.assertNotEqual(setting.folder_id, personal)
        self.assertFalse(setting.folder_id.owner_id)
        self.assertFalse(setting.folder_id.folder_id)

    def test_a_page_of_assets_reads_its_settings_once(self):
        assets = self.env["resource.asset"].create(
            [{"name": f"Van {i}", "kind_id": self.kind.id} for i in range(6)]
        )
        Setting = type(self.env["resource.kind.document"])
        searches = []
        search = Setting.search

        def counting(records, *args, **kwargs):
            searches.append(args)
            return search(records, *args, **kwargs)

        assets.invalidate_recordset()
        with patch.object(Setting, "search", counting):
            self.assertTrue(all(assets.mapped("document_centralized")))
        self.assertEqual(len(searches), 1)
