import zipfile
from datetime import datetime, time, timedelta
from io import BytesIO

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.document.tests.test_document_common import (
    TEXT,
    TransactionCaseDocuments,
)

PRIVATE_CONTENT = b"top secret payroll data"
SHARED_CONTENT = b"legitimately link-shared content"


@tagged("post_install", "-at_install")
class TestDocumentsZipShortcutLeak(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Doc = cls.env["document.document"]

        cls.internal_user = cls.env["res.users"].create(
            {
                "login": "audit3_internal",
                "name": "Audit3 Internal",
                "group_ids": [
                    Command.link(cls.env.ref("document.group_documents_user").id)
                ],
            }
        )

        cls.shared_folder = Doc.create(
            {
                "type": "folder",
                "name": "shared folder",
                "access_internal": "edit",
                "access_via_link": "edit",
            }
        )
        cls.private_folder = Doc.create(
            {
                "type": "folder",
                "name": "private folder",
                "access_internal": "none",
                "access_via_link": "none",
            }
        )
        cls.private_target = Doc.create(
            {
                "type": "binary",
                "name": "private-target.txt",
                "folder_id": cls.private_folder.id,
                "access_internal": "none",
                "access_via_link": "none",
                "is_access_via_link_hidden": True,
                "raw": PRIVATE_CONTENT,
            }
        )
        cls.shared_target = Doc.create(
            {
                "type": "binary",
                "name": "shared-target.txt",
                "folder_id": cls.private_folder.id,
                "access_internal": "view",
                "access_via_link": "view",
                "is_access_via_link_hidden": False,
                "raw": SHARED_CONTENT,
            }
        )
        cls.shared_file = Doc.create(
            {
                "type": "binary",
                "name": "shared-file.txt",
                "folder_id": cls.shared_folder.id,
                "access_internal": "edit",
                "access_via_link": "view",
                "raw": TEXT,
            }
        )

        cls.leak_shortcut = cls.private_target.sudo().action_create_shortcut(
            str(cls.shared_folder.id)
        )
        cls.legit_shortcut = cls.shared_target.sudo().action_create_shortcut(
            str(cls.shared_folder.id)
        )
        cls.leak_shortcut.sudo().write(
            {
                "access_internal": "edit",
                "access_via_link": "view",
                "is_access_via_link_hidden": False,
            }
        )

    def _zip_namelist(self, folder):
        res = self.url_open(f"/documents/content/{folder.access_token}")
        res.raise_for_status()
        self.assertEqual(res.headers["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(res.content)) as res_zip:
            return sorted(res_zip.namelist()), b"".join(
                res_zip.read(name) for name in res_zip.namelist()
            )

    def test_zip_public_does_not_leak_shortcut_target(self):
        self.authenticate(None, None)
        names, blob = self._zip_namelist(self.shared_folder)

        self.assertNotIn(
            "private-target.txt",
            names,
            "the private target's filename leaked into the public zip",
        )
        self.assertNotIn(
            PRIVATE_CONTENT, blob, "the private target's content leaked into the zip"
        )
        self.assertEqual(names, ["shared-file.txt", "shared-target.txt"])
        self.assertIn(SHARED_CONTENT, blob)

    def test_zip_internal_does_not_leak_shortcut_target(self):
        self.assertEqual(
            self.private_target.with_user(self.internal_user).user_permission,
            "none",
            "test setup: the target must be inaccessible to this user",
        )
        self.authenticate("audit3_internal", "audit3_internal")
        names, blob = self._zip_namelist(self.shared_folder)

        self.assertNotIn("private-target.txt", names)
        self.assertNotIn(PRIVATE_CONTENT, blob)
        self.assertIn("shared-target.txt", names)

    def test_zip_shortcut_target_own_token_is_refused(self):
        self.authenticate(None, None)
        for document in (self.private_target, self.leak_shortcut):
            with self.subTest(document=document.name):
                res = self.url_open(f"/documents/content/{document.access_token}")
                self.assertEqual(res.status_code, 404)


@tagged("post_install", "-at_install")
class TestDocumentsActivityExpirationSync(TransactionCaseDocuments):
    def _prepare_request(self):
        wizard = self.env["wizard.document.document.request"].create(
            {
                "name": "Audit3 Request",
                "requestee_id": self.internal_user.partner_id.id,
                "folder_id": self.folder_a.id,
                "activity_date_deadline_range": 5,
            }
        )
        document = wizard.request_document()
        activity = document.request_activity_id
        access = self.env["document.access"].search(
            [
                ("document_id", "=", document.id),
                ("partner_id", "=", self.internal_user.partner_id.id),
            ]
        )
        self.assertTrue(access.date_to, "test setup: the grant expires")
        return document, activity, access

    def test_permanent_grant_is_never_expired(self):
        __, activity, access = self._prepare_request()
        access.date_to = False

        activity.action_reschedule_today()

        self.assertFalse(
            access.date_to,
            "a permanent grant was silently turned into an expiring one",
        )

    def test_noop_deadline_write_does_not_resync_expiration(self):
        __, activity, access = self._prepare_request()
        activity.date_deadline = fields.Date.context_today(activity)
        extended = datetime.combine(
            activity.date_deadline + timedelta(days=10), datetime.max.time()
        )
        access.date_to = extended

        activity.action_reschedule_today()

        self.assertEqual(
            access.date_to,
            extended,
            "a no-op deadline write reset the requestee's expiration date",
        )

    def test_real_deadline_change_still_syncs_expiration(self):
        __, activity, access = self._prepare_request()
        new_deadline = activity.date_deadline + timedelta(days=3)

        activity.with_context(tz="America/Mexico_City").date_deadline = new_deadline

        self.assertEqual(
            access.date_to,
            datetime.combine(new_deadline + timedelta(days=1), time(5, 59, 59, 999999)),
            "the requestee's expiring grant must follow the new deadline, "
            "through the end of its day where the requester reads it (UTC-6)",
        )


@tagged("post_install", "-at_install")
class TestDocumentsRequestWizardSelfRequest(TransactionCaseDocuments):
    def test_self_request_keeps_permanent_grant(self):
        document = (
            self.env["wizard.document.document.request"]
            .with_user(self.doc_user)
            .create(
                {
                    "name": "Self Request",
                    "requestee_id": self.doc_user.partner_id.id,
                    "folder_id": self.folder_a.id,
                    "activity_date_deadline_range": 5,
                }
            )
            .request_document()
        )
        access = self.env["document.access"].search(
            [
                ("document_id", "=", document.id),
                ("partner_id", "=", self.doc_user.partner_id.id),
            ]
        )
        self.assertEqual(len(access), 1)
        self.assertEqual(access.role, "manage")
        self.assertFalse(
            access.date_to,
            "the requester's permanent grant was overwritten by the expiring one",
        )


@tagged("post_install", "-at_install")
class TestDocumentsOperationBatch(TransactionCaseDocuments):
    def test_destination_children_are_not_shifted_in_batch(self):
        Doc = self.env["document.document"]
        child_a, child_b = Doc.create(
            [
                {
                    "type": "binary",
                    "name": f"child in {folder.name}",
                    "folder_id": folder.id,
                    "raw": TEXT,
                }
                for folder in (self.folder_a, self.folder_b)
            ]
        )
        wizards = self.env["wizard.document.document.place.folder"].create(
            [
                {"operation": "move", "destination": str(folder.id)}
                for folder in (self.folder_b, self.folder_a)
            ]
        )
        wizard_b, wizard_a = wizards
        wizards.invalidate_recordset(["destination_children_ids"])

        self.assertIn(child_b, wizard_b.destination_children_ids)
        self.assertNotIn(child_a, wizard_b.destination_children_ids)
        self.assertIn(child_a, wizard_a.destination_children_ids)
        self.assertNotIn(child_b, wizard_a.destination_children_ids)


@tagged("post_install", "-at_install")
class TestDocumentsLinkToRecordWizard(TransactionCaseDocuments):
    def test_link_to_without_record_raises_user_error(self):
        wizard = self.env["wizard.document.document.link.record"].create({})
        with self.assertRaises(UserError):
            wizard.link_to()

    def test_target_model_selection_uses_a_real_boolean(self):
        models = dict(
            self.env["wizard.document.document.link.record"]._selection_target_model()
        )
        self.assertIn("res.partner", models)
        self.assertNotIn("document.document", models)
        self.assertNotIn(
            "ir.model.fields",
            models,
            "a non mail-thread model must not be offered as a link target",
        )

    def test_dead_field_is_gone(self):
        self.assertNotIn(
            "accessible_model_ids",
            self.env["wizard.document.document.link.record"]._fields,
        )


@tagged("post_install", "-at_install")
class TestDocumentsInboxAlias(TransactionCase):
    def test_inbox_alias_has_a_parent_model(self):
        alias = self.env.ref(
            "document.document_inbox_folder_mail_alias", raise_if_not_found=False
        )
        if not alias:
            self.skipTest("Inbox alias not seeded in this database")
        self.assertEqual(alias.alias_parent_model_id.model, "document.document")
        self.assertEqual(
            alias.alias_parent_thread_id,
            self.env.ref("document.document_inbox_folder").id,
        )


@tagged("post_install", "-at_install")
class TestDocumentsOperationWizard(TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.operator = new_test_user(
            cls.env,
            login="operation_user",
            groups="base.group_user,document.group_documents_user",
        )
        cls.Operation = cls.env["wizard.document.document.place.folder"].with_user(
            cls.operator
        )
        cls.target_folder = (
            cls.env["document.document"]
            .with_user(cls.operator)
            .create({"name": "Target", "type": "folder"})
        )

    def _document(self, name="movable.txt"):
        return (
            self.env["document.document"]
            .with_user(self.operator)
            .create({"name": name, "type": "binary", "raw": b"payload"})
        )

    def _run(self, **values):
        wizard = self.Operation.create(
            {"destination": str(self.target_folder.id), **values}
        )
        wizard.action_confirm()
        return wizard

    def test_move_puts_the_documents_in_the_destination(self):
        document = self._document()

        self._run(operation="move", document_ids=[Command.set(document.ids)])

        self.assertEqual(document.folder_id, self.target_folder)

    def test_copy_leaves_the_original_where_it_was(self):
        document = self._document()

        self._run(operation="copy", document_ids=[Command.set(document.ids)])

        self.assertFalse(document.folder_id, "the original does not move")
        copies = self.env["document.document"].search(
            [("folder_id", "=", self.target_folder.id)]
        )
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies.attachment_id.raw, b"payload")

    def test_shortcut_points_at_the_original(self):
        document = self._document()

        self._run(operation="shortcut", document_ids=[Command.set(document.ids)])

        shortcut = self.env["document.document"].search(
            [("folder_id", "=", self.target_folder.id)]
        )
        self.assertEqual(shortcut.shortcut_document_id, document)

    def test_add_a_file_attachment_copies_it_in(self):
        attachment = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create({"name": "report.txt", "type": "binary", "raw": b"content"})
        )

        self._run(operation="add", attachment_id=attachment.id)

        document = self.env["document.document"].search(
            [("folder_id", "=", self.target_folder.id)]
        )
        self.assertEqual(document.type, "binary")
        self.assertEqual(document.attachment_id.raw, b"content")
        self.assertNotEqual(
            document.attachment_id,
            attachment,
            "the source attachment is copied, not moved",
        )

    def test_add_a_url_attachment_keeps_its_address(self):
        attachment = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create(
                {
                    "name": "Odoo",
                    "type": "url",
                    "url": "https://www.odoo.com/page/x",
                }
            )
        )

        self._run(operation="add", attachment_id=attachment.id)

        document = self.env["document.document"].search(
            [("folder_id", "=", self.target_folder.id)]
        )
        self.assertEqual(document.type, "url")
        self.assertEqual(document.url, "https://www.odoo.com/page/x")

    def test_add_a_url_attachment_odoo_cannot_serve_is_refused(self):
        attachment = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create({"name": "Internal", "type": "url", "url": "/web/content/42"})
        )

        with self.assertRaises(ValidationError):
            self._run(operation="add", attachment_id=attachment.id)

    def test_add_without_an_attachment_is_refused(self):
        with self.assertRaises(UserError):
            self._run(operation="add")
