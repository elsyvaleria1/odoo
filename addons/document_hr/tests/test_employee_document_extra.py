from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import new_test_user

from .test_document_hr_common import TransactionCaseDocumentsHr


class TestEmployeeDocumentsExtra(TransactionCaseDocumentsHr):
    """Cover employee document counters, action branches, and share links."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Docs Employee",
                "user_id": cls.doc_user.id,
                "partner_id": cls.doc_user.partner_id.id,
                "wage": 1,
            }
        )

    def test_signature_tag_unlink_guard(self):
        """Check that the contract-signature tag cannot be deleted."""
        tag = self.env.ref("document_hr.document_tag_signature_request")
        with self.assertRaises(UserError):
            tag.unlink()

    def test_document_count_without_employee_folder(self):
        """Check the transitional partner-based counter when no employee
        folder is configured."""
        self.employee.hr_employee_folder_id = False
        self.env["document.document"].create(
            {
                "name": "Partner doc",
                "partner_id": self.employee.partner_id.id,
                "folder_id": self.env.ref("document.document_internal_folder").id,
            }
        )
        self.employee.invalidate_recordset(["document_count"])
        self.assertEqual(self.employee.document_count, 1)

        # An employee whose partner simply has no documents. This used to
        # clear `partner_id` instead, which `hr.employee` forbids: the field is
        # `required=True` and the column is NOT NULL, so the write raised
        # `NotNullViolation` and the assertion below was never reached. The
        # branch under test is `document_count_by_partner.get(partner, 0)`, and
        # a partner with nothing filed against it reaches it exactly as a
        # contactless employee would have -- while being a state this fork can
        # actually hold.
        orphan = self.env["hr.employee"].create({"name": "No Documents"})
        orphan.hr_employee_folder_id = False
        orphan.invalidate_recordset(["document_count"])
        self.assertEqual(orphan.document_count, 0)
        self.assertTrue(
            orphan.partner_id,
            "an employee is partner-backed by design here; a test that needs "
            "one without a contact is testing a record that cannot exist",
        )

    def test_action_view_documents_branches(self):
        """Check the legacy-filter, access, and act_url branches of
        action_view_documents."""
        hr_user = new_test_user(
            self.env,
            login="docs_hr_officer",
            groups="base.group_user,hr.group_hr_user,document.group_documents_user",
        )
        action = self.employee.with_user(hr_user).action_view_documents()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(
            action["url"],
            self.employee.hr_employee_folder_id.sudo().access_url,
        )

        with self.assertRaises(AccessError):
            self.employee.with_user(self.doc_user).action_view_documents()

        self.employee.company_id.documents_hr_settings = False
        action = self.employee.with_user(hr_user).action_view_documents()
        self.assertEqual(
            action["context"]["default_partner_id"],
            self.employee.partner_id.id,
        )

        # settings=False must still be gated the same as settings=True: a
        # non-hr user gets no "search everywhere" action either.
        with self.assertRaises(AccessError):
            self.employee.with_user(self.doc_user).action_view_documents()

    def test_public_employee_bridge(self):
        """Check the public employee counter relation and the see-documents
        action for user and non-user employees."""
        # is_user is true only for the employee of the CURRENT user
        self.env["document.document"].create(
            [
                {
                    "name": f"Bridge doc {index}",
                    "partner_id": self.doc_user.partner_id.id,
                    "owner_id": self.doc_user.id,
                    "folder_id": self.env.ref("document.document_internal_folder").id,
                }
                for index in range(2)
            ]
        )
        public = (
            self.env["hr.employee"].with_user(self.doc_user).browse(self.employee.id)
        )
        self.assertEqual(public.partner_document_count, 2)
        self.assertTrue(public.is_user)
        action = public.action_see_documents()
        self.assertEqual(
            action["context"]["default_partner_id"], self.doc_user.partner_id.id
        )

        plain = self.env["hr.employee"].create({"name": "No User Employee"})
        public_plain = self.env["hr.employee"].browse(plain.id)
        self.assertIsNone(public_plain.action_see_documents())

    def test_clearing_employee_subfolders_setting_removes_them(self):
        """Check that emptying the subfolders setting deletes the folders it
        created, and not only that replacing it with another name does."""
        company = self.employee.company_id
        folder = self.employee.sudo().hr_employee_folder_id
        Documents = self.env["document.document"].sudo()

        company.write({"employee_subfolders": "Gamma"})
        gamma = Documents.search(
            [("folder_id", "=", folder.id), ("name", "=", "Gamma")]
        )
        self.assertTrue(gamma, "setting the name creates the subfolder")

        company.write({"employee_subfolders": False})
        self.assertFalse(
            gamma.exists(),
            "clearing the setting must remove the subfolders it created; "
            "reading the written value instead of the key made the branch falsy",
        )

    def test_archived_employee_folder_moves_with_the_others(self):
        """Check that re-pointing the Employees Folder also moves the folder of
        an archived employee, instead of orphaning it under the old root."""
        company = self.employee.company_id
        self.employee.action_archive()
        new_root = self.env["document.document"].create(
            {"name": "New employees root", "type": "folder"}
        )

        company.write({"documents_employee_folder_id": new_root.id})

        self.employee.sudo().invalidate_recordset()
        self.assertEqual(
            self.employee.sudo().hr_employee_folder_id.folder_id,
            new_root,
            "an archived employee's folder must not be left under the old root",
        )

    def test_repointing_folder_resets_manually_customized_access(self):
        """Pin today's behaviour (round-2 audit R3, CONFIRMED, fix left as a
        DECISION NEEDED — see the round-2 ledger): re-pointing the Employees
        Folder unconditionally resets every employee folder's access back to
        the module defaults, even one an HR admin had manually locked down
        further. This is deliberate — it counters document.document.write's
        own access-from-new-parent sync — but it is currently silent and
        untested, so pin it here on purpose: a future change to this method
        must touch this test knowingly, not by accident."""
        folder = self.employee.sudo().hr_employee_folder_id
        self.assertEqual(folder.access_via_link, "none")
        folder.sudo().access_via_link = "view"

        new_root = self.env["document.document"].create(
            {"name": "New employees root", "type": "folder"}
        )
        self.employee.company_id.write({"documents_employee_folder_id": new_root.id})

        folder.invalidate_recordset(["access_via_link"])
        self.assertEqual(
            folder.access_via_link,
            "none",
            "today's behaviour resets access to the module default on every "
            "re-point, discarding any manual customization; if this starts "
            "failing, the change is deliberate and this test (plus the "
            "DECISION NEEDED it references) must be updated, not just deleted",
        )

    def test_main_folder_generation_is_idempotent(self):
        """Check that regenerating the company root folder keeps the existing
        one instead of orphaning it and everything filed under it."""
        company = self.employee.company_id
        before = company.documents_employee_folder_id
        self.assertTrue(before, "the fixture configures a root folder")

        folders = company._generate_employee_documents_main_folders()

        self.assertEqual(
            company.documents_employee_folder_id,
            before,
            "an already configured company must keep its root folder",
        )
        self.assertEqual(
            folders,
            before,
            "the return value stays aligned with self for overriding modules",
        )

    def test_second_company_gets_the_contracts_tag(self):
        """Check that a company created after install also gets the default
        contracts tag through _generate_employee_documents_main_folders."""
        tag = self.env.ref("document_hr.documents_hr_tag_contracts")
        company = self.env["res.company"].create({"name": "Second company"})
        self.assertIn(
            tag,
            company.documents_hr_contracts_tags,
            "every company must tag its contract documents, not only company 1",
        )

    def test_main_company_gets_the_contracts_tag_through_the_generic_path(self):
        """Check that base.main_company gets the default contracts tag from
        _generate_employee_documents_main_folders alone, with no dedicated
        data record for it (round-2 audit R2: the old noupdate XML record
        hardcoding base.main_company was redundant with this method and has
        been removed)."""
        tag = self.env.ref("document_hr.documents_hr_tag_contracts")
        main_company = self.env.ref("base.main_company")
        main_company.documents_hr_contracts_tags = [(5, 0, 0)]
        main_company._generate_employee_documents_main_folders()
        self.assertIn(
            tag,
            main_company.documents_hr_contracts_tags,
            "the generic per-company loop must tag base.main_company too, "
            "not only companies created after install",
        )

    def test_existing_contracts_tag_is_not_overwritten(self):
        """Check that a company which already chose its own contracts tags
        keeps them."""
        other_tag = self.env["document.tag"].create({"name": "Custom contracts"})
        company = self.env["res.company"].create(
            {
                "name": "Opinionated company",
                "documents_hr_contracts_tags": [(6, 0, other_tag.ids)],
            }
        )
        self.assertEqual(company.documents_hr_contracts_tags, other_tag)

    def test_subfolder_generation_is_idempotent_with_spaces(self):
        """Check that a comma-separated list written the way humans write it,
        with spaces, does not duplicate a subfolder on every save."""
        company = self.employee.company_id
        folder = self.employee.sudo().hr_employee_folder_id
        Documents = self.env["document.document"].sudo()

        company.write({"employee_subfolders": "Alpha, Beta"})
        first_pass = sorted(
            Documents.search([("folder_id", "=", folder.id)]).mapped("name")
        )
        self.assertEqual(first_pass, ["Alpha", "Beta", "Contracts"])

        # a non-empty folder survives the delete branch, so a duplicate would stay
        beta = Documents.search([("folder_id", "=", folder.id), ("name", "=", "Beta")])
        Documents.create({"name": "keepalive", "folder_id": beta.id})

        self.employee.sudo()._create_employee_documents_subfolders()

        second_pass = sorted(
            Documents.search([("folder_id", "=", folder.id)]).mapped("name")
        )
        self.assertEqual(
            second_pass,
            first_pass,
            "regenerating with the setting unchanged must be a no-op",
        )

    def test_document_count_in_a_mixed_batch(self):
        """Check that an employee without a folder keeps its partner-based
        count when computed alongside an employee that has one."""
        partner = self.env["res.partner"].create({"name": "Mixed batch contact"})
        folderless = self.env["hr.employee"].create(
            {"name": "No folder", "partner_id": partner.id}
        )
        folderless.sudo().hr_employee_folder_id = False
        self.env["document.document"].sudo().create(
            {
                "name": "Doc on the contact",
                "partner_id": partner.id,
                "folder_id": self.env.ref("document.document_internal_folder").id,
            }
        )

        folderless.invalidate_recordset(["document_count"])
        alone = folderless.document_count

        batch = self.employee | folderless
        batch.invalidate_recordset(["document_count"])
        in_batch = dict(zip(batch, batch.mapped("document_count"), strict=True))

        self.assertEqual(alone, 1)
        self.assertEqual(
            in_batch[folderless],
            alone,
            "the branch must be chosen per record, not from the batch-wide union",
        )

    def test_employee_folder_generation_is_idempotent(self):
        """Check that regenerating an employee's folder keeps the existing one
        instead of orphaning it and everything filed under it."""
        before = self.employee.sudo().hr_employee_folder_id
        self.assertTrue(before, "the fixture gives the employee a folder")

        self.employee.sudo()._create_employee_documents_folders()

        self.assertEqual(
            self.employee.sudo().hr_employee_folder_id,
            before,
            "an employee that already has a folder must keep it",
        )

    def test_contract_document_is_filed_in_the_employees_contracts(self):
        """A contract attachment's document lands in the employee's "Contracts"
        folder, where a signed contract is filed too -- not at the company-wide
        root among every employee's folders (upstream's own fix, 2026-04-03)."""
        attachment = self.env["ir.attachment"].create(
            {
                "datas": self.TEXT,
                "name": "contract_folder_probe.txt",
                "mimetype": "text/plain",
                "res_model": "hr.version",
                "res_id": self.employee.version_id.id,
            }
        )
        document = (
            self.env["document.document"]
            .sudo()
            .search([("attachment_id", "=", attachment.id)])
        )
        self.assertTrue(document, "the attachment creates a document")
        self.assertEqual(
            document.folder_id, self.employee.hr_employee_contract_folder_id
        )

    def test_the_root_is_a_closed_boundary_nothing_opens(self):
        root = self.env.company.documents_employee_folder_id
        self.assertTrue(root.is_access_restricted)
        self.assertEqual((root.access_internal, root.access_via_link), ("none", "none"))
        for opening in (
            {"access_internal": "view"},
            {"access_via_link": "view"},
            {"is_access_restricted": False},
        ):
            with self.subTest(opening=opening), self.assertRaises(ValidationError):
                root.sudo().write(opening)
        with self.assertRaises(ValidationError):
            root.sudo().action_update_access_rights(access_internal="view")

    def test_a_root_re_pointed_under_an_open_folder_keeps_employees_closed(self):
        Document = self.env["document.document"]
        opened = Document.create(
            {"name": "Open parent", "type": "folder", "user_folder_id": "COMPANY"}
        )
        opened.action_update_access_rights(access_internal="view")
        new_root = Document.create(
            {"name": "HR root", "type": "folder", "folder_id": opened.id}
        )
        self.env.company.documents_employee_folder_id = new_root
        bystander = self.env["res.users"].create(
            {
                "name": "Bystander",
                "login": "hr_root_bystander",
                "group_ids": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        employee = self.env["hr.employee"].create({"name": "Someone private"})
        folder = employee.hr_employee_folder_id
        self.assertEqual(folder.folder_id, new_root)
        self.assertTrue(new_root.is_access_restricted)
        for record in (new_root, folder):
            record.invalidate_recordset()
            self.assertEqual(record.with_user(bystander).user_permission, "none")


class TestEmployeeFilesStayInPlace(TransactionCaseDocumentsHr):
    def test_saving_the_settings_again_keeps_one_subfolder_and_its_trash(self):
        company = self.env.company
        employee = self.env["hr.employee"].create({"name": "Filed"})
        admin = self.env["res.users"].create(
            {
                "name": "Settings only",
                "login": "hr_settings_only",
                "group_ids": [Command.set([self.env.ref("base.group_system").id])],
            }
        )
        folder = employee.hr_employee_folder_id

        def subfolders(name):
            return (
                self.env["document.document"]
                .with_context(active_test=False)
                .search([("folder_id", "=", folder.id), ("name", "=", name)])
            )

        for _save in range(2):
            company.with_user(admin).employee_subfolders = "Payslips,Medical"
        self.assertEqual(len(subfolders("Payslips")), 1)
        self.assertEqual(len(subfolders("Medical")), 1)

        trashed = self.env["document.document"].create(
            {"name": "old.txt", "folder_id": subfolders("Medical").id}
        )
        trashed.action_archive()
        company.with_user(admin).employee_subfolders = "Payslips"
        self.assertEqual(
            len(subfolders("Medical")), 1, "a subfolder holding trash is kept"
        )
        company.with_user(admin).employee_subfolders = "Medical"
        self.assertFalse(subfolders("Payslips"), "an empty one is removed")

    def test_an_archived_employees_folder_is_theirs_still(self):
        employee = self.env["hr.employee"].create({"name": "Former"})
        folder = employee.hr_employee_folder_id
        employee.active = False
        self.assertFalse(employee.active)
        with self.assertRaisesRegex(ValidationError, "employee folder"):
            folder.unlink()
