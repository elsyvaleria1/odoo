from collections import Counter

from odoo.db import db_connect
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL, mute_logger

from odoo.addons.base.models.mixin_access_graph_reach import REACH_COLUMNS


@tagged("post_install", "-at_install")
class TestDocumentReachRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            env["document.document"].search([("name", "=like", "race %")]).unlink()
            env["res.partner"].search([("name", "=", "race partner")]).unlink()
            cr.commit()

    def committed_folder(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            folder = env["document.document"].create(
                {"name": "race folder", "type": "folder", "access_internal": "none"}
            )
            document = env["document.document"].create(
                {"name": "race document", "type": "binary", "folder_id": folder.id}
            )
            partner = env["res.partner"].create({"name": "race partner"})
            cr.commit()
            return folder.id, document.id, partner.id

    def race(self, early, late):
        attempts = []
        with self.cursor() as cr_late, self.cursor() as cr_early:
            env = self.env(cr=cr_late, su=True)

            def write():
                attempts.append(len(attempts) + 1)
                env.cr.execute("SELECT 1")
                if len(attempts) == 1:
                    early(self.env(cr=cr_early, su=True))
                    cr_early.commit()
                late(env)
                env.flush_all()

            with mute_logger("odoo.db.cursor", "odoo.service.model"):
                retrying(write, env)
        return len(attempts)

    def grant_rows(self, document_id, partner_id):
        with self.cursor() as cr:
            table = self.env(cr=cr)["document.document"]._access_reach_table()
            cr.execute(
                SQL(
                    """SELECT count(*) FROM %s AS reach
                         JOIN document_access AS grant_row ON grant_row.id = reach.grant_id
                        WHERE reach.resource_id = %s AND grant_row.partner_id = %s""",
                    SQL.identifier(table),
                    document_id,
                    partner_id,
                )
            )
            return cr.fetchone()[0]

    def assert_table_is_derived(self):
        with self.cursor() as cr:
            documents = self.env(cr=cr, su=True)["document.document"]
            table = SQL.identifier(documents._access_reach_table())
            columns = SQL(", ").join(SQL.identifier(c) for c in REACH_COLUMNS)
            cr.execute(SQL("SELECT %s FROM %s", columns, table))
            kept = Counter(cr.fetchall())
            cr.execute(SQL("DELETE FROM %s", table))
            cr.execute(documents._access_reach_rows(SQL("TRUE")))
            cr.execute(SQL("SELECT %s FROM %s", columns, table))
            rebuilt = Counter(cr.fetchall())
            cr.rollback()
        self.assertEqual(
            kept - rebuilt, Counter(), "rows kept that derive from nothing"
        )
        self.assertEqual(rebuilt - kept, Counter(), "rows derived that were not kept")

    def assert_reads_a_new_grant(self, place):
        def grant(env, ids):
            env["document.access"].create(
                {"document_id": ids[0], "partner_id": ids[2], "role": "view"}
            )

        for early_is_grant in (True, False):
            with self.subTest(early="grant" if early_is_grant else "place"):
                try:
                    ids = self.committed_folder()
                    placed = []

                    def placing(env, ids=ids, placed=placed):
                        placed.append(place(env, *ids[:2]))

                    def granting(env, ids=ids):
                        grant(env, ids)

                    early, late = (
                        (granting, placing) if early_is_grant else (placing, granting)
                    )
                    attempts = self.race(early, late)
                    self.assertTrue(self.grant_rows(placed[-1], ids[2]))
                    self.assert_table_is_derived()
                    self.assertEqual(
                        attempts, 2, "the later write must fail to serialize, and rerun"
                    )
                finally:
                    self.drop_committed()

    def test_a_shortcut_made_to_a_document_a_new_grant_reaches_is_reached(self):
        def shortcut(env, folder_id, document_id):
            return (
                env["document.document"]
                .create(
                    {
                        "name": "race shortcut",
                        "type": "binary",
                        "shortcut_document_id": document_id,
                    }
                )
                .id
            )

        self.assert_reads_a_new_grant(shortcut)

    def test_a_link_shared_in_a_folder_a_new_grant_reaches_is_found(self):
        def link(env, folder_id, document_id):
            env["document.document"].browse(document_id).access_via_link = "view"
            return document_id

        self.assert_reads_a_new_grant(link)
