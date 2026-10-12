import uuid
from types import SimpleNamespace
from unittest.mock import patch

from odoo.db import db_connect
from odoo.exceptions import ConcurrencyError
from odoo.http.core import _request_stack
from odoo.tests import TransactionCase, tagged

from odoo.addons.rpc.controllers.doc import DocController
from odoo.addons.rpc.tools.cache import doc_cache_generation, index_attachment_name


@tagged("-at_install", "post_install")
class TestDocIndexConcurrentBuild(TransactionCase):
    def setUp(self):
        super().setUp()
        self.generation = doc_cache_generation(self.env)
        self.filename = index_attachment_name(self.generation, uuid.uuid4().hex)
        self.addCleanup(self._drop_committed_rows)

    def _drop_committed_rows(self):
        with db_connect(self.env.cr.dbname).cursor() as cr:
            cr.execute("DELETE FROM ir_attachment WHERE name = %s", [self.filename])
            cr.commit()

    def _build(self, cr):
        request_env = self.env(cr=cr)
        _request_stack.push(
            SimpleNamespace(env=request_env, bound_env=request_env, session={})
        )
        try:
            with patch.object(DocController, "_doc_index", return_value=[]):
                return (
                    DocController()
                    ._doc_index_cache(self.filename, self.generation, refresh=False)
                    .id
                )
        finally:
            _request_stack.pop()

    def test_a_request_queued_on_the_lock_does_not_build_the_index_again(self):
        with (
            self.leave_registry_test_mode(),
            db_connect(self.env.cr.dbname).cursor() as cr_a,
            db_connect(self.env.cr.dbname).cursor() as cr_b,
        ):
            cr_b.execute("SELECT 1")
            built_by_a = self._build(cr_a)
            cr_a.commit()
            retries = 0
            while True:
                try:
                    served_to_b = self._build(cr_b)
                    cr_b.commit()
                    break
                except ConcurrencyError:
                    retries += 1
                    cr_b.rollback()
                    if retries > 1:
                        raise
            cr_b.execute(
                "SELECT id FROM ir_attachment WHERE name = %s ORDER BY id",
                [self.filename],
            )
            committed = [row[0] for row in cr_b.fetchall()]
        self.assertEqual(
            committed,
            [built_by_a],
            "the request whose snapshot predates the first build stored a second one",
        )
        self.assertEqual(served_to_b, built_by_a)
        self.assertEqual(retries, 1)
