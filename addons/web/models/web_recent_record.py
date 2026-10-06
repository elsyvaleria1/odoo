from typing import Any

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

_debug = DebugLog(__name__)


class WebRecentRecord(models.Model):
    _name = "web.recent.record"
    _description = "Recently Opened Record"
    _order = "recency desc, id desc"
    _access_anchors = frozendict({"owner": "user_id"})

    _KEPT_PER_USER = 100
    _NOTED_PER_CALL = 50

    user_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        ondelete="cascade",
    )
    res_model = fields.Char(
        string="Related Document Model",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Related Document ID",
        required=True,
    )
    opened_at = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )
    count = fields.Integer(
        default=1,
        required=True,
    )
    recency = fields.Integer(
        default=0,
        required=True,
    )

    _user_record_unique = models.UniqueIndex("(user_id, res_model, res_id)")

    @api.model
    def note_opened(self, entries: list[dict[str, Any]]) -> None:
        if not isinstance(entries, list) or len(entries) > self._NOTED_PER_CALL:
            raise ValidationError(self.env._("Invalid list of opened records."))
        opened: dict[tuple[str, int], None] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError(self.env._("Invalid opened record."))
            res_model, res_id = entry.get("res_model"), entry.get("res_id")
            if (
                not isinstance(res_model, str)
                or res_model not in self.env
                or self.env[res_model]._abstract
                or not isinstance(res_id, int)
                or isinstance(res_id, bool)
                or res_id <= 0
            ):
                raise ValidationError(self.env._("Invalid opened record."))
            opened[(res_model, res_id)] = None
        readable = self._readable_pairs(opened)
        _debug.logic("note_opened", entries=len(opened), readable=len(readable))
        if not readable:
            return
        mine = self.search(
            [
                ("user_id", "=", self.env.uid),
                ("res_model", "in", list({res_model for res_model, _id in readable})),
                ("res_id", "in", list({res_id for _model, res_id in readable})),
            ]
        )
        rows = {(row.res_model, row.res_id): row for row in mine}
        latest = self.search([("user_id", "=", self.env.uid)], limit=1)
        recency = latest.recency
        now = fields.Datetime.now()
        created = []
        for res_model, res_id in opened:
            if (res_model, res_id) not in readable:
                continue
            recency += 1
            row = rows.get((res_model, res_id))
            if row:
                row.write(
                    {"opened_at": now, "count": row.count + 1, "recency": recency}
                )
            else:
                created.append(
                    {
                        "res_model": res_model,
                        "res_id": res_id,
                        "opened_at": now,
                        "recency": recency,
                    }
                )
        if created:
            self.create(created)

    @api.model
    def _readable_pairs(
        self, pairs: dict[tuple[str, int], Any] | list[tuple[str, int]]
    ) -> dict[tuple[str, int], models.BaseModel]:
        ids_by_model: dict[str, list[int]] = {}
        for res_model, res_id in pairs:
            ids_by_model.setdefault(res_model, []).append(res_id)
        readable = {}
        for res_model, res_ids in ids_by_model.items():
            records = (
                self.env[res_model].browse(res_ids).exists()._filtered_access("read")
            )
            for record in records:
                readable[(res_model, record.id)] = record
        return readable

    @api.model
    def _get_recent(self, limit: int) -> list[dict[str, Any]]:
        with _debug.perf("get_recent", cr=self.env.cr, limit=limit) as span:
            rows = self.search([("user_id", "=", self.env.uid)], limit=limit * 3)
            readable = self._readable_pairs(
                [(row.res_model, row.res_id) for row in rows]
            )
            span.set(rows=len(rows), readable=len(readable))
        model_names = {
            res_model: self.env["ir.model"]._get(res_model).name
            for res_model in {res_model for res_model, _res_id in readable}
        }
        result = []
        for row in rows:
            record = readable.get((row.res_model, row.res_id))
            if record is None:
                continue
            result.append(
                {
                    "res_model": row.res_model,
                    "res_id": row.res_id,
                    "display_name": record.display_name,
                    "model_name": model_names[row.res_model],
                    "opened_at": row.opened_at,
                }
            )
            if len(result) == limit:
                break
        return result

    @api.autovacuum
    def _gc_keep_the_most_recent_per_user(self) -> tuple[int, bool]:
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM web_recent_record
                 WHERE id IN (
                       SELECT id FROM (
                              SELECT id, row_number() OVER (
                                         PARTITION BY user_id
                                         ORDER BY recency DESC, id DESC
                                     ) AS rank
                                FROM web_recent_record
                       ) ranked
                        WHERE rank > %(kept)s
                 )
                """,
                kept=self._KEPT_PER_USER,
            )
        )
        _debug.logic("gc_recent_records", deleted=self.env.cr.rowcount)
        return self.env.cr.rowcount, False
