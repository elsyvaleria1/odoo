from datetime import date, datetime, timedelta

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import tagged

from .test_document_common import TransactionCaseDocuments


@tagged("post_install", "-at_install")
class TestDocumentsLockOwnership(TransactionCaseDocuments):
    def test_a_lock_is_taken_for_oneself_only(self):
        document = (
            self.env["document.document"]
            .with_user(self.doc_user)
            .create({"name": "held.txt", "user_folder_id": "MY", "raw": b"x"})
        )
        with self.assertRaises(AccessError):
            document.write({"lock_uid": self.doc_user_2.id})
        document.write({"lock_uid": self.doc_user.id})
        self.assertEqual(document.lock_uid, self.doc_user)
        document.toggle_lock()
        self.assertFalse(document.lock_uid)


@tagged("post_install", "-at_install")
class TestDocumentsRequestMessages(TransactionCaseDocuments):
    def _request_bodies(self, document):
        return [
            body
            for body in document.message_ids.mapped("body")
            if "Document Request" in str(body)
        ]

    def test_a_request_is_answered_by_content_not_by_emptying(self):
        document = self.env["document.document"].create({"name": "awaited.txt"})
        document.write({"raw": b""})
        self.assertFalse(self._request_bodies(document), "emptying is no answer")
        document.write({"raw": b"answer"})
        self.assertEqual(len(self._request_bodies(document)), 1)

    def test_a_request_closed_without_a_file_is_not_uploaded(self):
        document = self.env["document.document"].create({"name": "form.pdf"})
        activity = document.activity_schedule(
            "mail.mail_activity_data_todo", summary="send the form"
        )
        document.request_activity_id = activity
        activity.invalidate_recordset(["is_document_request"])
        activity.action_feedback()
        self.assertFalse(
            [
                body
                for body in document.message_ids.mapped("body")
                if "Uploaded by" in str(body)
            ]
        )


@tagged("post_install", "-at_install")
class TestDocumentsManagerPredicate(TransactionCaseDocuments):
    def test_a_settings_administrator_is_no_documents_manager(self):
        settings_admin = self.env["res.users"].create(
            {
                "name": "Settings only",
                "login": "settings_only",
                "group_ids": [Command.link(self.env.ref("base.group_system").id)],
            }
        )
        Documents = self.env["document.document"]
        self.assertFalse(settings_admin.has_group("document.group_documents_manager"))
        self.assertFalse(Documents.with_user(settings_admin)._is_documents_manager())
        self.assertTrue(
            Documents.with_user(settings_admin).sudo()._is_documents_manager()
        )
        self.assertTrue(
            Documents.with_user(self.document_manager)._is_documents_manager()
        )


@tagged("post_install", "-at_install")
class TestDocumentsWizards(TransactionCaseDocuments):
    def test_the_place_folder_wizard_names_its_destination(self):
        Wizard = self.env["wizard.document.document.place.folder"].with_user(
            self.doc_user
        )
        for destination, name in (
            ("MY", "My Drive"),
            ("COMPANY", "Company"),
            (str(self.folder_a.id), "folder A"),
        ):
            with self.subTest(destination=destination):
                saved = Wizard.web_save(
                    {"operation": "copy", "destination": destination},
                    {"display_name": {}},
                )
                self.assertEqual(saved[0]["display_name"], name)

    def test_a_link_expiry_is_saved_on_every_selected_document(self):
        Documents = self.env["document.document"].with_user(self.doc_user)
        documents = Documents.create(
            [
                {"name": f"linked-{i}.txt", "user_folder_id": "MY", "raw": b"x"}
                for i in range(2)
            ]
        )
        documents.action_update_access_rights(access_via_link="view")
        Sharing = self.env["wizard.document.document.share"].with_user(self.doc_user)
        wizard = Sharing.browse(Sharing.action_open(documents.ids)["res_id"])
        expiry = fields.Datetime.now().replace(microsecond=0) + timedelta(days=20)
        wizard.link_date_to = expiry
        self.assertTrue(wizard.is_access_modified, "a Save button is offered")
        wizard.action_update_rights()
        documents.invalidate_recordset(["link_date_to"])
        self.assertEqual(set(documents.mapped("link_date_to")), {expiry})

    def test_a_removed_member_raises_no_missing_access_warning(self):
        partner = self.env["res.partner"].create({"name": "No user"})
        document = (
            self.env["document.document"]
            .with_user(self.doc_user)
            .create({"name": "m.txt", "user_folder_id": "MY", "raw": b"x"})
        )
        document.action_update_access_rights(partners={partner: ("view", False)})
        Sharing = self.env["wizard.document.document.share"].with_user(self.doc_user)
        wizard = Sharing.browse(Sharing.action_open(document.ids)["res_id"])
        line = wizard.share_access_ids.filtered(lambda l: l.partner_id == partner)
        self.assertTrue(line.has_warning_no_access)
        line.is_deleted = True
        self.assertFalse(line.has_warning_no_access)
        self.assertFalse(wizard.has_warning_partners_without_access)

    def test_a_system_administrator_is_warned_off_another_person_s_drive(self):
        sysadmin = self.env["res.users"].create(
            {
                "name": "Documents system",
                "login": "documents_system",
                "group_ids": [
                    Command.link(self.env.ref("document.group_documents_system").id)
                ],
            }
        )
        drive_document = (
            self.env["document.document"]
            .with_user(self.doc_user)
            .create({"name": "private.txt", "user_folder_id": "MY", "raw": b"x"})
        )
        company_document = self.env["document.document"].create(
            {"name": "shared.txt", "user_folder_id": "COMPANY", "raw": b"x"}
        )
        for document, warned in ((drive_document, True), (company_document, False)):
            with self.subTest(document=document.name):
                document.sudo().action_update_access_rights(
                    partners={sysadmin.partner_id: ("manage", False)}
                )
                Sharing = self.env["wizard.document.document.share"].with_user(sysadmin)
                wizard = Sharing.browse(Sharing.action_open(document.ids)["res_id"])
                wizard.share_access_ids.filtered(
                    lambda line: line.partner_id == sysadmin.partner_id
                ).is_deleted = True
                self.assertEqual(wizard.has_warning_self_access_loss, warned)

    def test_link_to_record_refuses_what_its_opener_refuses(self):
        document = self.env["document.document"].create(
            {"name": "l.txt", "raw": b"x", "user_folder_id": "COMPANY"}
        )
        with self.assertRaises(UserError):
            document.action_link_to_record("no.such.model")
        first, second = self.env["res.partner"].create(
            [{"name": "First"}, {"name": "Second"}]
        )
        document.write({"res_model": "res.partner", "res_id": first.id})
        wizard = self.env["wizard.document.document.link.record"].create(
            {
                "document_ids": [Command.set(document.ids)],
                "resource_ref": f"res.partner,{second.id}",
            }
        )
        with self.assertRaises(UserError):
            wizard.link_to()
        self.assertEqual(document.res_id, first.id)

    def test_link_to_record_offers_only_models_the_user_may_write(self):
        Wizard = self.env["wizard.document.document.link.record"].with_user(
            self.doc_user
        )
        domain = Wizard._domain_model_id()
        offered = set(next(term[2] for term in domain if term[0] == "model"))
        thread = self.env.registry["mixin.mail.thread"]
        readable_only = {
            name
            for name, model_class in self.env.registry.items()
            if not model_class._abstract
            and issubclass(model_class, thread)
            and self.env[name].with_user(self.doc_user).has_access("read")
            and not self.env[name].with_user(self.doc_user).has_access("write")
        }
        self.assertTrue(readable_only, "the fixture needs a model it may only read")
        self.assertFalse(offered & readable_only, "link_to would refuse those")
        self.assertTrue(
            all(
                self.env[model].with_user(self.doc_user).has_access("write")
                for model in offered
            )
        )

    def test_a_request_grant_ends_with_the_deadline_day_where_it_is_read(self):
        Documents = self.env["document.document"].with_context(tz="America/Mexico_City")
        self.assertEqual(
            Documents._request_grant_end(date(2026, 10, 1)),
            datetime(2026, 10, 2, 5, 59, 59, 999999),
        )


@tagged("post_install", "-at_install")
class TestDocumentsNotificationAccess(TransactionCaseDocuments):
    def test_an_expired_grant_offers_no_access_button(self):
        partner = self.env["res.partner"].create({"name": "Former guest"})
        document = self.env["document.document"].create(
            {"name": "n.txt", "raw": b"x", "access_via_link": "view"}
        )
        document.action_update_access_rights(partners={partner: ("view", False)})
        grant = document.access_ids.filtered(lambda a: a.partner_id == partner)
        grant.sudo().write({"date_to": fields.Datetime.now() - timedelta(days=1)})
        groups = document._notify_get_recipients_groups(
            self.env["mail.message"], "Document"
        )
        test = next(
            group[1]
            for group in groups
            if group[0] == "group_documents_document_people_with_access"
        )
        self.assertFalse(test({"uid": False, "id": partner.id}))


@tagged("post_install", "-at_install")
class TestDocumentsLinkCosts(TransactionCaseDocuments):
    def test_access_tokens_cost_one_query_for_many_documents(self):
        documents = self.env["document.document"].create(
            [
                {"name": f"t{i}.txt", "raw": b"x", "access_via_link": "view"}
                for i in range(10)
            ]
        )
        documents.invalidate_recordset(["access_token"])
        Cursor = type(self.env.cr)
        execute, token_queries = Cursor.execute, []

        def counting(cr, query, params=None, *args, **kwargs):
            if "token_nonce" in str(getattr(query, "code", query)):
                token_queries.append(query)
            return execute(cr, query, params, *args, **kwargs)

        Cursor.execute = counting
        try:
            tokens = documents.mapped("access_token")
        finally:
            Cursor.execute = execute
        self.assertEqual(len(token_queries), 1)
        self.assertTrue(all(token.rpartition("o")[0] for token in tokens))

    def test_the_review_of_a_purged_document_s_link_does_not_crash(self):
        document = self.env["document.document"].create(
            {"name": "gone.txt", "raw": b"x", "access_via_link": "view"}
        )
        links = document._document_links()
        document_id = document.id
        document.sudo().unlink()
        links = links.exists()
        if not links:
            self.skipTest("links go with their document")
        self.assertFalse(self.env["document.document"].browse(document_id).exists())
        links._review_issuer()


@tagged("post_install", "-at_install")
class TestDocumentsReachConsistency(TransactionCaseDocuments):
    def test_a_system_administrator_moves_what_the_reach_gives_them(self):
        sysadmin = self.env["res.users"].create(
            {
                "name": "Documents system mover",
                "login": "documents_system_mover",
                "group_ids": [
                    Command.link(self.env.ref("document.group_documents_system").id)
                ],
            }
        )
        in_a_drive = (
            self.env["document.document"]
            .with_user(self.doc_user)
            .create({"name": "theirs.txt", "user_folder_id": "MY", "raw": b"x"})
        )
        in_a_drive.action_update_access_rights(
            partners={sysadmin.partner_id: ("view", False)}
        )
        company = self.env["document.document"].create(
            {"name": "ours.txt", "user_folder_id": "COMPANY", "raw": b"x"}
        )
        as_sysadmin = (in_a_drive | company).with_user(sysadmin)
        self.assertEqual(
            {document.name: document.user_can_move for document in as_sysadmin},
            {"theirs.txt": False, "ours.txt": True},
        )


@tagged("post_install", "-at_install")
class TestDocumentsRequestLinkTracking(TransactionCaseDocuments):
    def _queued_changes(self, document):
        return (
            self.env["document.access.tracking"]
            .search([])
            .filtered(lambda tracking: document.id in tracking.documents)
        )

    def test_closing_a_request_tracks_its_upload_link_closing(self):
        document = self.env["document.document"].create(
            {"name": "form.pdf", "user_folder_id": "COMPANY"}
        )
        document.action_update_access_rights(access_via_link="edit")
        activity = document.activity_schedule(
            "mail.mail_activity_data_todo", summary="send it"
        )
        document.request_activity_id = activity
        activity.invalidate_recordset(["is_document_request"])
        self.env["document.access.tracking"].search([]).unlink()
        activity.action_feedback()
        self.assertEqual(document.access_via_link, "view")
        self.assertTrue(self._queued_changes(document))

    def test_a_folder_link_expiry_reaches_its_children(self):
        Documents = self.env["document.document"].with_user(self.doc_user)
        folder = Documents.create(
            {"name": "Shared tree", "user_folder_id": "MY", "type": "folder"}
        )
        children = Documents.create(
            [
                {"name": f"leaf-{i}.txt", "folder_id": folder.id, "raw": b"x"}
                for i in range(2)
            ]
        )
        folder.action_update_access_rights(access_via_link="view")
        children.invalidate_recordset(["access_via_link", "link_date_to"])
        self.assertEqual(set(children.mapped("access_via_link")), {"view"})
        Sharing = self.env["wizard.document.document.share"].with_user(self.doc_user)
        wizard = Sharing.browse(Sharing.action_open(folder.ids)["res_id"])
        expiry = fields.Datetime.now().replace(microsecond=0) + timedelta(days=20)
        wizard.link_date_to = expiry
        wizard.action_update_rights()
        (folder | children).invalidate_recordset(["link_date_to"])
        self.assertEqual(set((folder | children).mapped("link_date_to")), {expiry})


@tagged("post_install", "-at_install")
class TestDocumentsReadCost(TransactionCaseDocuments):
    def _count(self, marker, call):
        Cursor = type(self.env.cr)
        execute, hits = Cursor.execute, []

        def counting(cr, query, params=None, *args, **kwargs):
            if str(getattr(query, "code", query)).startswith(marker):
                hits.append(query)
            return execute(cr, query, params, *args, **kwargs)

        Cursor.execute = counting
        try:
            call()
        finally:
            Cursor.execute = execute
        return len(hits)

    def test_a_folder_page_computes_permissions_in_one_batch(self):
        folder = self.env["document.document"].create(
            {"name": "Page", "type": "folder", "user_folder_id": "COMPANY"}
        )
        folder.access_internal = "view"
        self.env["document.document"].create(
            [
                {"name": f"p{i}.txt", "folder_id": folder.id, "raw": b"x"}
                for i in range(5)
            ]
        )
        Documents = self.env["document.document"].with_user(self.doc_user)
        self.env.invalidate_all()
        batches = self._count(
            "SELECT reachable.id",
            lambda: Documents.web_search_read(
                [("folder_id", "=", folder.id)],
                {
                    "name": {},
                    "user_permission": {},
                    "user_folder_id": {},
                    "available_embedded_actions_ids": {},
                },
            ),
        )
        self.assertEqual(batches, 1, "the documents and their folders together")


class TestDocumentsOwnerDefault(TransactionCaseDocuments):
    def test_a_copy_made_without_a_person_is_owned_by_nobody_and_says_nothing(self):
        source = self.env["document.document"].create(
            {"name": "Source", "folder_id": self.folder_a.id}
        )
        with self.assertNoLogs(
            "odoo.addons.document.models.document_document", "WARNING"
        ):
            copy = source.copy()
        self.assertFalse(self.env.user.active)
        self.assertFalse(copy.owner_id)
        self.assertEqual(source.with_user(self.doc_user).copy().owner_id, self.doc_user)


class TestDocumentsSearchPanelScope(TransactionCaseDocuments):
    def test_a_panel_scoped_to_one_folder_says_what_the_whole_tree_says(self):
        Document = self.env["document.document"]
        tag = self.env["document.tag"].create({"name": "Alias tag"})
        root = Document.create(
            {"name": "Scope", "type": "folder", "user_folder_id": "COMPANY"}
        )
        inner = Document.create(
            {
                "name": "Inner",
                "type": "folder",
                "folder_id": root.id,
                "alias_tag_ids": [Command.set(tag.ids)],
            }
        )
        Document.create({"name": "inner.txt", "folder_id": inner.id})
        target = Document.create(
            {"name": "Target", "type": "folder", "user_folder_id": "COMPANY"}
        )
        shortcut = target.action_create_shortcut(str(root.id))

        def panel(context):
            values = Document.with_context(context).search_panel_select_range(
                "user_folder_id", enable_counters=True
            )["values"]
            return {
                v["id"]: v for v in values if v["id"] in (root | inner | shortcut).ids
            }

        whole = panel({})
        scoped = panel({"documents_unique_folder_id": root.id})
        self.assertEqual(scoped.keys(), whole.keys())
        self.assertFalse(scoped[root.id]["user_folder_id"])
        for key in ("__count", "alias_tag_ids", "target_user_permission"):
            for folder in (inner, shortcut):
                self.assertEqual(
                    scoped[folder.id].get(key), whole[folder.id].get(key), key
                )
        self.assertEqual(scoped[inner.id]["alias_tag_ids"][0]["id"], tag.id)
        self.assertEqual(scoped[shortcut.id]["target_user_permission"], "edit")
        self.assertEqual(scoped[root.id]["__count"], whole[root.id]["__count"])
        self.assertTrue(scoped[root.id]["__count"])
