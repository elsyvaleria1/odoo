from unittest.mock import patch

from odoo.db import db_connect
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestAiSortRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            env["automation.rule"].search([("name", "=", "race sort")]).unlink()
            env["document.document"].with_context(active_test=False).search(
                [("name", "like", "race sort%")]
            ).unlink()
            cr.commit()

    def committed_document_to_sort(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            folder = env["document.document"].create(
                {"name": "race sort folder", "type": "folder"}
            )
            env["automation.rule"].create(
                {
                    "name": "race sort",
                    "model_id": env["ir.model"]._get_id("document.document"),
                    "trigger": "on_hand",
                    "ai_autosort_folder_id": folder.id,
                }
            )
            document = env["document.document"].create(
                {
                    "name": "race sort document",
                    "folder_id": folder.id,
                    "type": "binary",
                    "datas": "VGVzdCBmaWxl",
                    "ai_to_sort": True,
                }
            )
            cr.commit()
            return document.id

    def test_a_sort_that_loses_a_race_is_sorted_again(self):
        document_id = self.committed_document_to_sort()
        sorts = []
        with self.cursor() as cr_sort, self.cursor() as cr_edit:

            def sort(rule, records, domain_post=None):
                sorts.append(records.id)
                records.name
                rule.env.cr.execute("SELECT 1")
                if len(sorts) == 1:
                    edit = self.env(cr=cr_edit, su=True)["document.document"]
                    edit.browse(document_id).name = "race sort renamed"
                    edit.env.flush_all()
                    cr_edit.commit()
                records.name = "race sort sorted"
                records.env.flush_all()

            env = self.env(cr=cr_sort, su=True)
            with (
                patch.object(type(env["automation.rule"]), "_process", sort),
                mute_logger(
                    "odoo.db.cursor",
                    "odoo.addons.ai_document.models.document_document",
                ),
            ):
                env["document.document"]._cron_ai_sort()
                cr_sort.commit()
                env["document.document"]._cron_ai_sort()
                cr_sort.commit()
        with self.cursor() as cr:
            cr.execute(
                "SELECT name->>'en_US', ai_to_sort FROM document_document WHERE id = %s",
                [document_id],
            )
            self.assertEqual(cr.fetchone(), ("race sort sorted", False))
        self.assertEqual(sorts, [document_id, document_id], "sorted again")
