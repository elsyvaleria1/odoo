from collections.abc import Callable
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.tools import SQL, frozendict
from odoo.tools.json import json_default

_debug = DebugLog(__name__)

RETENTION_DAYS = 30
GC_BATCH_SIZE = 10000


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
    result = fields.Json(readonly=True)
    processed_at = fields.Datetime(
        index=True,
        readonly=True,
        required=True,
    )

    _operation_uuid_unique = models.Constraint(
        "unique (operation_uuid)", "An operation with this uuid was already processed"
    )

    @api.model
    def _call_once(
        self, operation_uuid: str, res_model: str, method: str, call: Callable[[], Any]
    ) -> Any:
        # A concurrent replay waits on the uncommitted row, then fails to
        # serialise; its retry reads the result this transaction commits.
        self.env.cr.execute(
            SQL(
                """
                INSERT INTO pos_processed_operation
                       (operation_uuid, user_id, res_model, method, processed_at)
                VALUES (%s, %s, %s, %s, now() AT TIME ZONE 'UTC')
           ON CONFLICT (operation_uuid) DO NOTHING
             RETURNING id
                """,
                operation_uuid,
                self.env.uid,
                res_model,
                method,
            )
        )
        if claimed := self.env.cr.fetchone():
            result = call()
            self.env.cr.execute(
                SQL(
                    "UPDATE pos_processed_operation SET result = %s::jsonb WHERE id = %s",
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
                SELECT user_id, res_model, method, result
                  FROM pos_processed_operation
                 WHERE operation_uuid = %s
                """,
                operation_uuid,
            )
        )
        user_id, done_model, done_method, result = self.env.cr.fetchone()
        if (user_id, done_model, done_method) != (self.env.uid, res_model, method):
            _debug.logic(
                "operation_replay_mismatch",
                operation=operation_uuid,
                model=res_model,
                method=method,
                done_model=done_model,
                done_method=done_method,
                same_user=user_id == self.env.uid,
            )
            raise AccessError(
                self.env._("This operation was already processed as another one.")
            )
        _debug.logic(
            "operation_replayed",
            operation=operation_uuid,
            model=res_model,
            method=method,
        )
        return result

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
