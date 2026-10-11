import logging
from typing import Any

from odoo import SUPERUSER_ID, api
from odoo.libs import redact

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

    @cr.postrollback.add
    def keep_logs_of_rolled_back_transaction():
        if pending:
            keep_rows(registry, pending)


def keep_rows(registry, logs: list[dict[str, Any]]) -> None:
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
                    **admission.annotations,
                    "event_type": admission.event_type or vals.get("event_type"),
                    "state": "failed",
                    "error_type": "other",
                    "error_message": redact.mask_text(admission.error)
                    or "the request rolled back",
                    "duration_ms": admission.elapsed_ms,
                }
            ],
        )
