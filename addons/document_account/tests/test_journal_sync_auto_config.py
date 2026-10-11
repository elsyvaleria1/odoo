from odoo.tests.common import RecordCapturer, tagged

from odoo.addons.document_account.tests.common import DocumentsAccountTestCommon


@tagged("post_install", "-at_install", "test_document_bridge")
class TestJournalSyncAutoConfig(DocumentsAccountTestCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        FolderSettings = cls.env["document.account.folder.setting"]
        cls.setup_other_company()

        existing_settings = FolderSettings.search(
            [("journal_id", "any", [("type", "in", ["bank", "general"])])]
        )
        auto_configured_folders = existing_settings.folder_id
        existing_settings.unlink()
        auto_configured_folders.action_archive()

        cls.env["res.lang"]._activate_lang("fr_FR")
        journal_type_sel_by_value = (
            cls.env["ir.model.fields"]
            ._get("account.journal", "type")
            .selection_ids.grouped("value")
        )
        for journal_type, default_tr, fr_FR_tr in (
            ("general", "Miscellaneous", "Divers"),
            ("bank", "Bank", "Banque"),
            ("cash", "Cash", "Espèces"),
        ):
            journal_type_sel_by_value[journal_type].name = default_tr
            journal_type_sel_by_value[journal_type].with_context(
                lang="fr_FR"
            ).name = fr_FR_tr

        cls.company_2 = cls.env["res.company"].search([("name", "=", "company_2")])[0]
        with cls._freeze_time("2022-08-22 09:16"):
            cls.journals = cls.env["account.journal"].create(
                [
                    {
                        "name": "Misc company 1",
                        "type": "general",
                        "company_id": cls.env.company.id,
                    },
                    {
                        "name": "Misc company 2",
                        "type": "general",
                        "company_id": cls.company_2.id,
                    },
                    {
                        "name": "Bank company 2",
                        "type": "bank",
                        "company_id": cls.company_2.id,
                    },
                    {
                        "name": "Cash company 1",
                        "type": "cash",
                        "company_id": cls.env.company.id,
                    },
                ]
            )
        settings = FolderSettings.search([("journal_id", "in", cls.journals.ids)])
        cls.settings_by_name = settings.grouped(lambda j: j.journal_id.name)
        cls.unused_folder_with_misc_name = cls.env["document.document"].create(
            {
                "name": "Miscellaneous",
                "type": "folder",
                "folder_id": cls.env.company.account_folder_id.id,
                "company_id": cls.env.company.id,
            }
        )
        cls.misc_journal = cls.journals[0]
        cls.misc_setting = FolderSettings.search(
            [("journal_id", "=", cls.misc_journal.id)]
        )
        cls.misc_folder = cls.misc_setting.folder_id

    def test_initial_data(self):
        self.assertEqual(len(self.settings_by_name), 4)
        self.assertNotEqual(self.env.lang, "fr_FR")

    def test_auto_creation_of_settings(self):
        for name, expected_folder_name, expected_folder_name_fr, expected_company in (
            ("Misc company 1", "Miscellaneous", "Divers", self.env.company),
            ("Misc company 2", "Miscellaneous", "Divers", self.company_2),
            ("Bank company 2", "Bank", "Banque", self.company_2),
            ("Cash company 1", "Cash", "Cash", self.env.company),
        ):
            setting = self.settings_by_name[name]
            folder = setting.folder_id
            self.assertEqual(folder.name, expected_folder_name)
            self.assertEqual(
                folder.with_context(lang="fr_FR").name, expected_folder_name_fr
            )
            self.assertEqual(folder.company_id, expected_company)
            self.assertFalse(folder.owner_id)
            self.assertEqual(folder.access_internal, "edit")
            self.assertEqual(folder.access_via_link, "none")
            self.assertFalse(folder.access_ids.filtered(lambda a: a.role))
            self.assertEqual(setting.company_id, expected_company)
            self.assertFalse(
                setting.tag_ids,
                "No tag is invented for the journal: the name of a journal is "
                "not a classification, it is already on the linked move.",
            )

    def test_no_tag_is_created_for_a_journal(self):
        FolderSettings = self.env["document.account.folder.setting"]
        with RecordCapturer(self.env["document.tag"], []) as capture:
            journal = self.env["account.journal"].create(
                {"name": "Untagged journal", "type": "general"}
            )
        self.assertFalse(capture.records)
        setting = FolderSettings.search([("journal_id", "=", journal.id)])
        self.assertTrue(setting, "The synchronization setting is still created.")
        self.assertFalse(setting.tag_ids)

    def test_create_journal_without_base_folder(self):
        self.env.company.account_folder_id = False
        journal = self.env["account.journal"].create(
            {
                "name": "Test without base folder",
                "type": "general",
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(
            self.env["document.account.folder.setting"].search(
                [("journal_id", "=", journal.id)]
            )
        )

    def test_folder_creation(self):
        FolderSettings = self.env["document.account.folder.setting"]
        self.misc_setting.unlink()
        (self.misc_folder | self.unused_folder_with_misc_name).unlink()

        with RecordCapturer(self.env["document.document"], []) as capture:
            misc = self.env["account.journal"].create(
                {"name": "Misc", "type": "general"}
            )
        created_folder = capture.records.filtered(lambda d: d.name == "Miscellaneous")
        self.assertEqual(len(created_folder), 1)
        self.assertEqual(
            FolderSettings.search([("journal_id", "=", misc.id)]).folder_id,
            created_folder,
        )

    def test_folder_creation_existing_folder_with_wrong_company(self):
        FolderSettings = self.env["document.account.folder.setting"]
        self.misc_setting.unlink()
        self.misc_folder.unlink()
        self.unused_folder_with_misc_name.company_id = False

        with RecordCapturer(self.env["document.document"], []) as capture:
            misc = self.env["account.journal"].create(
                {"name": "Misc", "type": "general"}
            )
        created_folder = capture.records.filtered(lambda d: d.name == "Miscellaneous")
        self.assertEqual(len(created_folder), 1)
        self.assertEqual(
            FolderSettings.search([("journal_id", "=", misc.id)]).folder_id,
            created_folder,
        )

    def test_folder_reuse_from_settings(self):
        FolderSettings = self.env["document.account.folder.setting"]
        self.misc_setting.folder_id.name = "renamed"

        with self._freeze_time("2024-08-22 09:16"):
            new_misc_journal = self.env["account.journal"].create(
                {"name": "Misc 2", "type": "general"}
            )
        new_misc_setting = FolderSettings.search(
            [("journal_id", "=", new_misc_journal.id)]
        )
        self.assertEqual(
            new_misc_setting.folder_id,
            self.misc_setting.folder_id,
            "The folder of the configuration with the same journal type is used (same comapny).",
        )
        replaced_folder = self.env["document.document"].create(
            {
                "name": "replaced",
                "type": "folder",
                "folder_id": self.env.company.account_folder_id.id,
                "company_id": self.env.company.id,
            }
        )
        new_misc_setting.folder_id = replaced_folder
        with self._freeze_time("2025-08-22 10:16"):
            another_misc_journal = self.env["account.journal"].create(
                {"name": "Misc 3", "type": "general"}
            )
        another_misc_setting = FolderSettings.search(
            [("journal_id", "=", another_misc_journal.id)]
        )
        self.assertEqual(another_misc_setting.folder_id.name, "replaced")
        self.assertEqual(new_misc_setting.folder_id.name, "replaced")
        self.assertEqual(self.misc_setting.folder_id.name, "renamed")
        self.assertFalse(
            FolderSettings.search(
                [("folder_id", "=", self.unused_folder_with_misc_name.id)]
            ),
            "The folder with the journal type name is not used as existing configured folder are preferred.",
        )

    def test_folder_reuse_setting_of_another_company(self):
        FolderSettings = self.env["document.account.folder.setting"]
        self.misc_setting.sudo().company_id = self.company_2

        new_misc_journal = self.env["account.journal"].create(
            {"name": "Misc 2", "type": "general"}
        )
        self.assertEqual(
            FolderSettings.search([("journal_id", "=", new_misc_journal.id)]).folder_id,
            self.misc_folder,
            "The folder configured for the journals of the same type in the "
            "journal's own company is reused, not a new one.",
        )

    def test_folder_reuse_no_setting(self):
        FolderSettings = self.env["document.account.folder.setting"]
        self.misc_setting.unlink()
        self.misc_folder.unlink()

        misc_journal_no_pre_config = self.env["account.journal"].create(
            {"name": "Misc", "type": "general"}
        )
        misc_journal_no_pre_config_setting = FolderSettings.search(
            [("journal_id", "=", misc_journal_no_pre_config.id)]
        )
        self.assertEqual(
            misc_journal_no_pre_config_setting.folder_id.name, "Miscellaneous"
        )
        self.assertEqual(
            misc_journal_no_pre_config_setting.folder_id,
            self.unused_folder_with_misc_name,
        )

    def test_post_init(self):
        FolderSettings = self.env["document.account.folder.setting"]
        settings = FolderSettings.search([])
        folders = settings.folder_id
        self.unused_folder_with_misc_name.unlink()
        settings.unlink()
        folders.unlink()

        for lang in (self.env.lang, "fr_FR"):
            with self.subTest(lang=lang):
                self.env["account.journal"].with_context(lang=lang).search(
                    [("id", "not in", FolderSettings._search([]).select("journal_id"))]
                )._documents_configure_sync()
                settings_by_name = FolderSettings.search(
                    [("journal_id", "in", self.journals.ids)]
                ).grouped(lambda j: j.journal_id.name)
                for (
                    name,
                    expected_folder_name,
                    expected_folder_name_fr,
                    expected_company,
                ) in (
                    (
                        "Misc company 1",
                        "Miscellaneous",
                        "Divers",
                        self.env.company,
                    ),
                    (
                        "Misc company 2",
                        "Miscellaneous",
                        "Divers",
                        self.company_2,
                    ),
                    (
                        "Bank company 2",
                        "Bank",
                        "Banque",
                        self.company_2,
                    ),
                    (
                        "Cash company 1",
                        "Cash",
                        "Espèces",
                        self.env.company,
                    ),
                ):
                    setting = settings_by_name[name]
                    folder = setting.folder_id
                    self.assertEqual(folder.name, expected_folder_name)
                    self.assertEqual(
                        folder.with_context(lang="fr_FR").name, expected_folder_name_fr
                    )
                    self.assertEqual(folder.company_id, expected_company)
                    self.assertFalse(folder.owner_id)
                    self.assertEqual(folder.access_internal, "edit")
                    self.assertEqual(folder.access_via_link, "none")
                    self.assertFalse(folder.access_ids.filtered(lambda a: a.role))
                    self.assertEqual(setting.company_id, expected_company)
                    self.assertFalse(setting.tag_ids)
