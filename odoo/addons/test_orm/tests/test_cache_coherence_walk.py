import logging
import os
from collections import Counter
from contextlib import contextmanager

from odoo.api import Environment
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import SQL

from .cache_coherence_walk import (
    KINDS_COMPARED,
    Walk,
    explore,
    no_savepoints_left,
    viewers,
)

_logger = logging.getLogger(__name__)


class PostgresHarness:
    def __init__(self, env, user, company):
        self.env = env
        self.viewers = viewers(env, user.id, company.id)

    def alive_ids(self, model_name):
        table = self.env[model_name]._table
        self.env.cr.execute(SQL("SELECT id FROM %s", SQL.identifier(table)))
        return [row[0] for row in self.env.cr.fetchall()]

    @contextmanager
    def fresh(self):
        cr = self.env.registry.cursor()
        try:
            yield lambda viewer: Environment(
                cr, viewer.uid, viewer.context, su=viewer.su
            )
        finally:
            cr.close()


@tagged("post_install", "-at_install")
class TestCacheCoherenceWalk(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_FR")
        cls.company = cls.env["res.company"].create({"name": "coherence walk"})
        cls.user = new_test_user(
            cls.env,
            login="coherence_walk",
            groups="base.group_user",
            company_id=cls.env.company.id,
            company_ids=[Command.set([cls.env.company.id, cls.company.id])],
        )

    def _run(self, ops):
        self.env.registry.clear_cache()
        savepoint = self.env.cr.savepoint()
        try:
            walk = Walk(PostgresHarness(self.env, self.user, self.company))
            with no_savepoints_left(walk):
                failure = walk.run(ops)
            self.compared.update(walk.compared)
            return failure, walk.log
        finally:
            savepoint.close(rollback=True)

    def test_a_random_walk_leaves_the_cache_and_stored_computes_agreeing_with_a_fresh_read(
        self,
    ):
        first, _, count = os.environ.get(
            "ODOO_CACHE_COHERENCE_SEEDS", "0:120"
        ).partition(":")
        steps = int(os.environ.get("ODOO_CACHE_COHERENCE_STEPS", "80"))
        self.compared = Counter()
        for seed in range(int(first), int(first) + int(count)):
            with self.subTest(seed=seed):
                report = explore(self._run, seed, steps)
                self.assertIsNone(report, report)
        _logger.info("cache coherence walk compared %s", dict(self.compared))
        self.assertTrue(all(self.compared[kind] for kind in KINDS_COMPARED))
