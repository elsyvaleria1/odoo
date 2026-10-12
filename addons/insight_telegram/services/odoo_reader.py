from contextlib import contextmanager

from odoo import api


class OdooReader:
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
