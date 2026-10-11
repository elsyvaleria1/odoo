import contextlib

from odoo.tests import TransactionCase
from odoo.tools import SQL

OPERATIONAL_MODELS = (
    "mail.message",
    "res.partner",
    "product.product",
)


class TrainingNeutralityCase(TransactionCase):

    operational_models = OPERATIONAL_MODELS

    def _table_fingerprint(self, models):
        self.env.flush_all()
        fingerprint = {}
        for model in models:
            if model not in self.env:
                continue
            self.env.cr.execute(
                SQL(
                    "SELECT count(*), coalesce(max(write_date), max(create_date)) FROM %s",
                    SQL.identifier(self.env[model]._table),
                )
            )
            fingerprint[model] = self.env.cr.fetchone()
        return fingerprint

    @contextlib.contextmanager
    def assertNoOperationalWrites(self, models=None):
        models = models or self.operational_models
        before = self._table_fingerprint(models)
        yield
        after = self._table_fingerprint(models)
        changed = {m: (before[m], after[m]) for m in before if before[m] != after[m]}
        self.assertFalse(changed, f"The simulator wrote operational data: {changed}")
