from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import OPT_SORT_KEYS, dumps_bytes
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools import SQL, frozendict
from odoo.tools.json import json_default

_debug = DebugLog(__name__)

RETENTION_DAYS = 30
GC_BATCH_SIZE = 10000
QUEUED_ORM_METHODS = frozenset({"create", "write", "unlink"})


def pos_queueable[F: Callable[..., Any]](method: F) -> F:
    method._pos_queueable = True  # type: ignore[attr-defined]
    return method


def _arguments_digest(args: Sequence[Any], kwargs: Mapping[str, Any]) -> str:
    # the context is the session's ambient state, merged into every call by the
    # client and rebuilt on reload, which a queued replay may cross
    arguments = [args, {key: kwargs[key] for key in kwargs if key != "context"}]
    return sha256(dumps_bytes(arguments, option=OPT_SORT_KEYS)).hexdigest()


class PosProcessedOperation(models.Model):
    _name = "pos.processed.operation"
    _description = "Processed POS Operation"
    _log_access = False
    _access_anchors = frozendict({"company": ""})

    operation_uuid = fields.Char(
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    res_model = fields.Char(
        readonly=True,
        required=True,
    )
    method = fields.Char(
        readonly=True,
        required=True,
    )
    arguments_digest = fields.Char(readonly=True)
    result = fields.Text(readonly=True)
    processed_at = fields.Datetime(
        index=True,
        readonly=True,
        required=True,
    )

    _operation_uuid_unique = models.Constraint(
        "unique (operation_uuid)", "An operation with this uuid was already processed"
    )

    @api.model
    def _is_queueable(self, res_model: str, method: str) -> bool:
        model_class = self.pool.get(res_model)
        if model_class is None or not issubclass(
            model_class, self.pool["mixin.pos.load"]
        ):
            return False
        return method in QUEUED_ORM_METHODS or any(
            getattr(vars(cls).get(method), "_pos_queueable", False)
            for cls in model_class.__mro__
        )

    @api.model
    def _call_once(
        self,
        operation_uuid: str,
        res_model: str,
        method: str,
        args: Sequence[Any],
        kwargs: Mapping[str, Any],
        call: Callable[[], Any],
    ) -> Any:
        digest = _arguments_digest(args, kwargs)
        # A concurrent replay waits on the uncommitted row, then fails to
        # serialise; its retry reads the result this transaction commits.
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO pos_processed_operation
                       (operation_uuid, user_id, res_model, method, arguments_digest,
                        processed_at)
                VALUES (%s, %s, %s, %s, %s, now() AT TIME ZONE 'UTC')
           ON CONFLICT (operation_uuid) DO NOTHING
             RETURNING id
                """,
                operation_uuid,
                self.env.uid,
                res_model,
                method,
                digest,
            )
        )
        if claimed := self.env.cr.fetchone():
            result = call()
            self.env.cr.execute(
                SQL(
                    "UPDATE pos_processed_operation SET result = %s WHERE id = %s",
                    json_dumps(result, default=json_default),
                    claimed[0],
                )
            )
            _debug.pipeline(
                "operation_processed",
                operation=operation_uuid,
                model=res_model,
                method=method,
            )
            return result

        self.env.cr.execute(
            SQL(
                """
                SELECT user_id, res_model, method, arguments_digest, result
                  FROM pos_processed_operation
                 WHERE operation_uuid = %s
                """,
                operation_uuid,
            )
        )
        user_id, done_model, done_method, done_digest, result = self.env.cr.fetchone()
        same_call = (user_id, done_model, done_method) == (
            self.env.uid,
            res_model,
            method,
        )
        # a row recorded before digests were has none; it expires with its retention
        same_arguments = done_digest is None or done_digest == digest
        if not (same_call and same_arguments):
            _debug.logic(
                "operation_replay_mismatch",
                operation=operation_uuid,
                model=res_model,
                method=method,
                done_model=done_model,
                done_method=done_method,
                same_user=user_id == self.env.uid,
                same_arguments=same_arguments,
            )
            raise AccessError(
                self.env._("This operation was already processed as another one.")
            )
        # a replay changes nothing and only hands back the answer: a declared
        # method's answer needs the model readable, an ORM write its own right
        self.env[res_model].check_access(
            method if method in QUEUED_ORM_METHODS else "read"
        )
        if result is None:
            _debug.logic(
                "operation_replay_unfinished",
                operation=operation_uuid,
                model=res_model,
                method=method,
            )
            raise UserError(
                self.env._(
                    "This operation saved part of its work and then stopped, so "
                    "its answer was never recorded. It will not run again: check "
                    "what it did before redoing it."
                )
            )
        _debug.logic(
            "operation_replayed",
            operation=operation_uuid,
            model=res_model,
            method=method,
        )
        return json_loads(result, lone_surrogates=True)

    @api.autovacuum
    def _gc_processed_operations(self) -> tuple:
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM pos_processed_operation
                 WHERE id IN (SELECT id FROM pos_processed_operation
                               WHERE processed_at < %s
                               LIMIT %s)
                """,
                fields.Datetime.subtract(fields.Datetime.now(), days=RETENTION_DAYS),
                GC_BATCH_SIZE,
            )
        )
        removed = self.env.cr.rowcount
        self.invalidate_model()
        _debug.lifecycle("processed_operations_gc", removed=removed)
        return removed, removed == GC_BATCH_SIZE
