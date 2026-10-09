import logging
from typing import Any

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

PENDING_KEY = "integration.exchange.values"


def queue_exchange_values(env: api.Environment, vals: dict[str, Any]) -> None:
    cr = env.cr
    if PENDING_KEY not in cr.precommit.durable_data:
        _register_flush_hooks(env)
    cr.precommit.durable_data[PENDING_KEY].append(vals)


def _register_flush_hooks(env: api.Environment) -> None:
    cr = env.cr
    pending = cr.precommit.durable_data[PENDING_KEY] = []
    registry = env.registry

    @cr.precommit.add_durable
    def batch_create_logs():
        logs = cr.precommit.durable_data.pop(PENDING_KEY, pending)
        if logs:
            env["integration.exchange"].sudo().create(
                _without_vanished_references(env, logs)
            )
            _logger.debug("Batch created %d exchange rows", len(logs))

    # A caller that lets an error propagate rolls its transaction back, and the
    # exchange that failed is the one most worth a row. `_rollback` empties
    # `precommit.durable_data` before running this, so it keeps its own list.
    @cr.postrollback.add
    def keep_logs_of_rolled_back_transaction():
        if pending:
            keep_rows(registry, pending)


def keep_rows(registry, logs: list[dict[str, Any]]) -> None:
    """Create `logs` in a transaction of their own, the one they were queued
    in having rolled back."""
    try:
        with registry.cursor() as log_cr:
            log_env = api.Environment(log_cr, SUPERUSER_ID, {})
            log_env["integration.exchange"].sudo().create(
                _without_vanished_references(log_env, logs)
            )
    except Exception:
        _logger.exception(
            "Could not keep %d exchange row(s) of a rolled-back transaction",
            len(logs),
        )


def _without_vanished_references(
    env: api.Environment, logs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Unlink rows from the records a rollback took away.

    A row is queued in the transaction of its call, and what the call stood
    on may have been created there too: a record's connection is made lazily
    by its first call, and its company, user or credential can be as new as
    the call. When a savepoint or the transaction around it rolls back, those
    records go with it while the row survives, and naming them would fail the
    row's insert on its foreign key. The row is kept without them. Its
    channel is a reference, which no foreign key holds, and stays named.
    """
    exchanges = env["integration.exchange"]
    vanished = {}
    for name, field in exchanges._fields.items():
        if field.type != "many2one" or not field.store:
            continue
        named = {vals[name] for vals in logs if vals.get(name)}
        if named:
            present = env[field.comodel_name].sudo().browse(named).exists()
            vanished[name] = named - set(present.ids)
    if not any(vanished.values()):
        return list(logs)
    return [
        {
            **vals,
            **{
                name: False for name, gone in vanished.items() if vals.get(name) in gone
            },
        }
        for vals in logs
    ]


def keep_row_on_rollback(env: api.Environment, vals: dict[str, Any], admission) -> None:
    cr = env.cr
    registry = env.registry

    @cr.postrollback.add
    def keep_row_of_rolled_back_transaction():
        keep_rows(
            registry,
            [
                {
                    **vals,
                    "event_type": admission.event_type or vals.get("event_type"),
                    "state": "failed",
                    "error_type": "other",
                    "error_message": admission.error or "the request rolled back",
                }
            ],
        )
