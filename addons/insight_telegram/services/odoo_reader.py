from contextlib import contextmanager

from odoo import api


class OdooReader:
    """Open read-only environments as the reader user, over every company.

    Each environment lives on its own PostgreSQL READ ONLY transaction on the
    primary, so nothing a report runs can write. The reader acts as superuser
    on purpose: the owner sees everything, and the read-only transaction is
    what keeps that safe.
    """

    # a report that would scan for longer is cut rather than left to load the
    # production database
    STATEMENT_TIMEOUT_MS = 20000

    def __init__(self, registry, reader_uid, context=None) -> None:
        self._registry = registry
        self._uid = reader_uid
        self._context = {**(context or {}), "active_test": True}

    @property
    def uid(self) -> int:
        return self._uid

    @contextmanager
    def env(self):
        with self._registry.cursor(readonly=True, primary=True) as cr:
            cr.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                [str(self.STATEMENT_TIMEOUT_MS)],
            )
            env = api.Environment(cr, self._uid, self._context, su=True)
            companies = env["res.company"].search([]).ids
            yield env(context={**env.context, "allowed_company_ids": companies})
