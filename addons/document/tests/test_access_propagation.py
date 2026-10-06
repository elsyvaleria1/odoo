from odoo import Command
from odoo.tests.common import tagged

from .test_document_common import TransactionCaseDocuments


@tagged("post_install", "-at_install")
class TestAccessPropagation(TransactionCaseDocuments):
    def _chain(self, name):
        Document = self.env["document.document"]
        folders = []
        parent = False
        for level in ("root", "mid", "leaf"):
            vals = {"name": f"{name}-{level}", "type": "folder"}
            vals.update(
                {"folder_id": parent.id} if parent else {"user_folder_id": "COMPANY"}
            )
            parent = Document.create(vals)
            folders.append(parent)
        return folders

    def _values(self, folders):
        self.env.invalidate_all()
        return [folder.sudo().access_internal for folder in folders]

    def test_a_root_s_audience_reaches_every_level_below(self):
        folders = self._chain("A")

        folders[0].action_update_access_rights(access_internal="edit")
        self.assertEqual(self._values(folders), ["edit", "edit", "edit"])
        self.assertFalse(
            (folders[1] | folders[2]).access_ids, "nothing is written below the root"
        )

        folders[0].action_update_access_rights(access_internal="none")
        self.assertEqual(self._values(folders), ["none", "none", "none"])

    def test_a_folder_that_narrows_its_audience_is_a_boundary(self):
        folders = self._chain("B")
        folders[0].action_update_access_rights(access_internal="edit")

        folders[1].action_update_access_rights(access_internal="view")
        self.assertTrue(folders[1].is_access_restricted)
        self.assertEqual(self._values(folders), ["edit", "view", "view"])

        folders[0].action_update_access_rights(access_internal="none")
        self.assertEqual(
            self._values(folders),
            ["none", "view", "view"],
            "what the root grants stops at the boundary, both ways",
        )

    def test_a_root_s_manager_does_not_reach_under_a_boundary(self):
        Document = self.env["document.document"]
        user = self.env["res.users"].create(
            {
                "name": "Propagation User",
                "login": "propagation_user",
                "group_ids": [
                    Command.set([self.env.ref("document.group_documents_user").id])
                ],
            }
        )
        as_user = Document.with_user(user)
        root = as_user.create(
            {"name": "G-root", "type": "folder", "user_folder_id": "MY"}
        )
        mid = as_user.create({"name": "G-mid", "type": "folder", "folder_id": root.id})
        leaf = as_user.create({"name": "G-leaf", "type": "folder", "folder_id": mid.id})
        mid.sudo().write(
            {
                "owner_id": self.env.ref("base.user_admin").id,
                "is_access_restricted": True,
            }
        )
        leaf.sudo().owner_id = self.env.ref("base.user_admin")
        # the edit grant a previous owner keeps goes too
        (mid | leaf).sudo().access_ids.unlink()

        readable = as_user.search([("id", "in", (root | mid | leaf).ids)])
        self.assertEqual(readable, root, "the boundary keeps the root's owner out")

        root.with_user(user).action_update_access_rights(access_internal="view")

        self.assertEqual(self._values([root, mid, leaf]), ["view", "none", "none"])

    def test_an_update_that_changes_nothing_queues_no_tracking(self):
        Tracking = self.env["document.access.tracking"]
        folders = self._chain("D")
        folders[0].action_update_access_rights(access_internal="view")
        before = Tracking.sudo().search_count([])

        folders[0].action_update_access_rights(access_internal="view")

        self.assertEqual(Tracking.sudo().search_count([]), before)

    def test_a_bad_tracking_batch_size_still_tracks_the_change(self):
        Tracking = self.env["document.access.tracking"]
        Param = self.env["ir.config_parameter"].sudo()
        for index, value in enumerate(("0", "-3", "junk")):
            Param.set_param("document.tracking_batch_size", value)
            folders = self._chain(f"B{index}")
            before = Tracking.sudo().search_count([])
            folders[0].action_update_access_rights(access_internal="edit")
            self.assertGreater(Tracking.sudo().search_count([]), before, value)
