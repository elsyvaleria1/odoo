from datetime import timedelta

from odoo import fields
from odoo.db import db_connect
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

DOC = "test_access_right.shared_doc"


@tagged("post_install", "-at_install", "access_link")
class TestAccessLinkRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        self.customer = self.env.ref("base.partner_admin")
        self.far = fields.Datetime.now() + timedelta(days=700)
        self.near = fields.Datetime.now() + timedelta(days=5)
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            cr.execute(
                "DELETE FROM access_link WHERE res_model = %s AND res_id IN "
                "(SELECT id FROM test_access_right_shared_doc WHERE name = 'race')",
                [DOC],
            )
            cr.execute("DELETE FROM test_access_right_shared_doc WHERE name = 'race'")
            cr.commit()

    def committed_doc(self):
        with self.cursor() as cr:
            doc = self.env(cr=cr, su=True)[DOC].create(
                {"name": "race", "date_due": self.far}
            )
            cr.commit()
            return doc.id

    def run_as_a_request(self, cr, work):
        env = self.env(cr=cr, su=True)
        attempts = []

        def attempt():
            attempts.append(len(attempts) + 1)
            return work(env, attempts[-1])

        with mute_logger("odoo.db.cursor", "odoo.service.model"):
            result = retrying(attempt, env)
        return result, len(attempts)

    def issue(self, env, doc_id):
        link, _token = env["access.link"]._issue(
            env[DOC].browse(doc_id), partner=self.customer, cause="notification"
        )
        return link.id

    def move(self, env, doc_id):
        doc = env[DOC].browse(doc_id)
        doc.date_due = self.near
        env["access.link"]._sync_record_expiries(doc)

    def link_dates(self, doc_id):
        with self.cursor() as cr:
            cr.execute(
                "SELECT date_to FROM access_link WHERE res_model = %s AND res_id = %s",
                [DOC, doc_id],
            )
            return [row[0] for row in cr.fetchall()]

    def test_a_link_issued_across_a_date_move_takes_the_moved_date(self):
        doc_id = self.committed_doc()
        with self.cursor() as cr_issue, self.cursor() as cr_move:

            def issue(env, attempt):
                env[DOC].browse(doc_id).name
                if attempt == 1:
                    self.move(self.env(cr=cr_move, su=True), doc_id)
                    cr_move.commit()
                return self.issue(env, doc_id)

            _link_id, attempts = self.run_as_a_request(cr_issue, issue)
        self.assertEqual(self.link_dates(doc_id), [self.near + timedelta(days=7)])
        self.assertEqual(attempts, 2, "the issue must fail to serialize, and rerun")

    def test_a_date_moved_across_a_link_issue_moves_the_new_link(self):
        doc_id = self.committed_doc()
        with self.cursor() as cr_move, self.cursor() as cr_issue:

            def move(env, attempt):
                env[DOC].browse(doc_id).name
                if attempt == 1:
                    self.issue(self.env(cr=cr_issue, su=True), doc_id)
                    cr_issue.commit()
                self.move(env, doc_id)

            _result, attempts = self.run_as_a_request(cr_move, move)
        self.assertEqual(self.link_dates(doc_id), [self.near + timedelta(days=7)])
        self.assertEqual(attempts, 2, "the move must fail to serialize, and rerun")

    def test_a_link_handed_out_again_across_a_date_move_needs_no_rerun(self):
        doc_id = self.committed_doc()
        with self.cursor() as cr:
            self.issue(self.env(cr=cr, su=True), doc_id)
            cr.commit()
        with self.cursor() as cr_issue, self.cursor() as cr_move:

            def issue(env, attempt):
                env[DOC].browse(doc_id).name
                if attempt == 1:
                    self.move(self.env(cr=cr_move, su=True), doc_id)
                    cr_move.commit()
                return self.issue(env, doc_id)

            _link_id, attempts = self.run_as_a_request(cr_issue, issue)
        self.assertEqual(self.link_dates(doc_id), [self.near + timedelta(days=7)])
        self.assertEqual(attempts, 1)
