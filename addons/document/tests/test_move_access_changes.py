from odoo.tests.common import tagged

from .test_document_common import TransactionCaseDocuments
from odoo.addons.document.tools import MOVE_ACCESS_CHECK, MoveChangesAccess


@tagged("post_install", "-at_install")
class TestMoveAccessChanges(TransactionCaseDocuments):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Document = cls.env["document.document"]
        cls.folder_view = Document.create(
            {"name": "View", "type": "folder", "user_folder_id": "COMPANY"}
        )
        cls.folder_view.action_update_access_rights(access_internal="view")
        cls.folder_edit = Document.create(
            {"name": "Edit", "type": "folder", "user_folder_id": "COMPANY"}
        )
        cls.folder_edit.action_update_access_rights(
            access_internal="edit", access_via_link="view"
        )
        cls.folder_none = Document.create(
            {"name": "None", "type": "folder", "user_folder_id": "COMPANY"}
        )
        cls.folder_none.action_update_access_rights(access_internal="none")

    def _file(self, name, folder):
        return self.env["document.document"].create(
            {"name": name, "type": "binary", "raw": b"x", "folder_id": folder.id}
        )

    def _levels(self, documents):
        self.env.invalidate_all()
        return {
            document: (document.folder_id, document.sudo().access_internal)
            for document in documents
        }

    def assertRefused(self, documents, folder, expected, watched=None):
        watched = watched or documents
        before = self._levels(watched)
        # not assertRaises, which rolls back by itself: the refusal must
        try:
            documents.with_context(**{MOVE_ACCESS_CHECK: True}).write(
                {"folder_id": folder.id}
            )
        except MoveChangesAccess as refusal:
            self.assertEqual(refusal.changes, expected)
        else:
            self.fail("the move was not refused")
        self.assertEqual(
            self._levels(watched), before, "a refused move leaves nothing moved"
        )

    def assertMoved(self, documents, folder):
        documents.with_context(**{MOVE_ACCESS_CHECK: True}).write(
            {"folder_id": folder.id}
        )
        self.assertEqual(documents.folder_id, folder)

    def test_a_document_taking_the_folder_s_access_is_refused(self):
        document = self._file("plain", self.folder_view)
        self.assertRefused(
            document,
            self.folder_edit,
            {
                "access_internal": ["edit"],
                "access_via_link": "view",
                "documents": 1,
                "contents": 0,
            },
        )

    def test_the_move_goes_through_when_it_changes_no_access(self):
        document = self._file("raised", self.folder_view)
        document.action_update_access_rights(access_internal="edit")
        self.assertFalse(document.is_access_restricted)
        # its own grant outranks the destination's: nothing changes
        self.assertMoved(document, self.folder_none)
        self.assertEqual(document.access_internal, "edit")

    def test_a_restricted_document_is_refused_for_its_link_only(self):
        document = self._file("boundary", self.folder_edit)
        document.action_update_access_rights(access_internal="view")
        self.assertTrue(document.is_access_restricted)
        self.assertRefused(
            document,
            self.folder_none,
            {
                "access_internal": [],
                "access_via_link": "none",
                "documents": 1,
                "contents": 0,
            },
        )

    def test_documents_landing_on_different_levels_report_each(self):
        plain = self._file("plain", self.folder_edit)
        raised = self._file("raised", self.folder_none)
        raised.action_update_access_rights(access_internal="view")
        raised.folder_id = self.folder_edit
        self.assertEqual(raised.access_internal, "edit")
        self.assertRefused(
            plain | raised,
            self.folder_none,
            {
                "access_internal": ["none", "view"],
                "access_via_link": "none",
                "documents": 2,
                "contents": 0,
            },
        )

    def test_a_moved_folder_reports_what_it_contains(self):
        folder = self.env["document.document"].create(
            {"name": "Moved", "type": "folder", "folder_id": self.folder_view.id}
        )
        inner = self._file("inner", folder)
        boundary = self._file("boundary", folder)
        boundary.action_update_access_rights(access_internal="none")
        self.assertTrue(boundary.is_access_restricted)
        self.assertRefused(
            folder,
            self.folder_edit,
            {
                "access_internal": ["edit"],
                "access_via_link": "view",
                "documents": 1,
                "contents": 2,
            },
            watched=folder | inner | boundary,
        )

    def test_a_shortcut_moves_without_asking(self):
        target = self._file("target", self.folder_view)
        shortcut = target.action_create_shortcut(str(self.folder_view.id))
        self.assertMoved(shortcut, self.folder_edit)

    def test_a_folder_shortcut_destination_is_judged_on_its_folder(self):
        document = self._file("plain", self.folder_view)
        shortcut = self.folder_edit.action_create_shortcut(str(self.folder_none.id))
        self.assertRefused(
            document,
            shortcut,
            {
                "access_internal": ["edit"],
                "access_via_link": "view",
                "documents": 1,
                "contents": 0,
            },
        )

    def test_an_internal_user_is_told_without_elevation(self):
        editable = self.env["document.document"].create(
            {"name": "Editable", "type": "folder", "user_folder_id": "COMPANY"}
        )
        editable.action_update_access_rights(access_internal="edit")
        document = self._file("shared", self.folder_edit)
        self.assertRefused(
            document.with_user(self.doc_user),
            editable,
            {
                "access_internal": [],
                "access_via_link": "none",
                "documents": 1,
                "contents": 0,
            },
            watched=document,
        )

    def test_without_the_flag_a_move_is_never_refused(self):
        document = self._file("plain", self.folder_view)
        document.write({"folder_id": self.folder_edit.id})
        self.assertEqual(document.folder_id, self.folder_edit)
        self.assertEqual(document.access_internal, "edit")
