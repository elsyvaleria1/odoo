import contextvars
import hashlib
import hmac
import itertools
import json
import logging
from typing import Any, Self

from odoo import api, fields, models
from odoo.api import SUPERUSER_ID, ValuesType
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import SQL, config

_logger = logging.getLogger(__name__)

ACCESS_LOG_EVENTS = [
    ("grant_created", "Grant created"),
    ("grant_changed", "Grant changed"),
    ("grant_revoked", "Grant revoked"),
    ("grant_expired", "Grant expired"),
    ("grant_migrated", "Memberships migrated"),
    ("privilege_used", "Privilege used"),
    ("link_created", "Link issued"),
    ("link_extended", "Link extended"),
    ("link_revoked", "Link revoked"),
    ("log_purged", "Log rows purged"),
    ("log_erased", "Log rows erased"),
    ("log_chain_broken", "Log seal chain broken"),
]

CHAIN_COLUMNS = ("seal", "seal_seq", "content_hash", "erasure_id")
ERASURE_KEPT = ("id", "event", "create_date")
ERASURE_BATCH = 100
SEAL_KEY_MIN_LENGTH = 32
SEAL_LEGACY = "base.access_log_seal_legacy"
NO_SEAL_KEY = (
    "The authorization log is not sealed: set access_log_seal_key in the server "
    "configuration (or ODOO_ACCESS_LOG_SEAL_KEY), a secret of at least %s "
    "characters kept out of the database"
)

APPEND_ONLY = """
    CREATE OR REPLACE FUNCTION ir_access_log_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        changed text;
        operation text := current_setting('odoo.access_log_operation', true);
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF operation = 'purge' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'the authorization log is append-only: row % cannot be deleted', OLD.id
                USING ERRCODE = 'insufficient_privilege';
        END IF;
        FOR changed IN
            SELECT new_row.key
              FROM jsonb_each(to_jsonb(NEW)) new_row
              JOIN jsonb_each(to_jsonb(OLD)) old_row USING (key)
             WHERE new_row.value IS DISTINCT FROM old_row.value
        LOOP
            IF changed IN ('seal', 'seal_seq', 'content_hash') AND OLD.seal IS NULL THEN
                CONTINUE;
            END IF;
            IF operation = 'reseal' AND changed IN ('seal', 'content_hash') THEN
                CONTINUE;
            END IF;
            IF operation = 'erase' AND OLD.seal IS NOT NULL AND OLD.erasure_id IS NULL
               AND changed NOT IN ('id', 'event', 'create_date', 'seal', 'seal_seq', 'content_hash')
               AND (changed = 'erasure_id' OR to_jsonb(NEW) -> changed = 'null'::jsonb) THEN
                CONTINUE;
            END IF;
            IF to_jsonb(NEW) -> changed = 'null'::jsonb
               AND jsonb_typeof(to_jsonb(OLD) -> changed) = 'number' THEN
                CONTINUE;
            END IF;
            RAISE EXCEPTION 'the authorization log is append-only: row % cannot be changed (%)', OLD.id, changed
                USING ERRCODE = 'insufficient_privilege';
        END LOOP;
        RETURN NEW;
    END
    $$;
    CREATE OR REPLACE FUNCTION ir_access_log_no_truncate() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'the authorization log is append-only: it cannot be truncated'
            USING ERRCODE = 'insufficient_privilege';
    END
    $$;
    DROP TRIGGER IF EXISTS ir_access_log_append_only ON ir_access_log;
    CREATE TRIGGER ir_access_log_append_only
        BEFORE UPDATE OR DELETE ON ir_access_log
        FOR EACH ROW EXECUTE FUNCTION ir_access_log_append_only();
    DROP TRIGGER IF EXISTS ir_access_log_no_truncate ON ir_access_log;
    CREATE TRIGGER ir_access_log_no_truncate
        BEFORE TRUNCATE ON ir_access_log
        FOR EACH STATEMENT EXECUTE FUNCTION ir_access_log_no_truncate();
"""

SEAL_HEAD = "base.access_log_seal_head"
SEAL_BASE = "base.access_log_seal_base"

_PURGING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "access_log_purging", default=False
)


def _keep_rows(records: Any) -> None:
    return


def kept_on_uninstall(events: list[tuple[str, str]]) -> dict[str, Any]:
    return dict.fromkeys((event for event, _label in events), _keep_rows)


def _content_hash(key: bytes, content: dict[str, Any]) -> str:
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(key, b"content\0" + text.encode(), hashlib.sha256).hexdigest()


def _chained(key: bytes, previous: str, content_hash: str) -> str:
    link = f"link\0{previous}\0{content_hash}".encode()
    return hmac.new(key, link, hashlib.sha256).hexdigest()


LEGACY_CONTENT = SQL(
    """
    jsonb_strip_nulls(
        to_jsonb(log) - ARRAY['seal', 'seal_seq', 'actor_id', 'subject_user_id',
                              'group_id', 'grant_id', 'link_id', 'create_uid',
                              'write_uid']
    )
    """
)


def _legacy_chained(previous: str, content: dict[str, Any]) -> str:
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((previous + text).encode()).hexdigest()


class IrAccessLog(models.Model):
    _name = "ir.access.log"
    _description = "Authorization Log"
    _order = "id desc"
    _rec_name = "event"
    _allow_sudo_commands = False

    event = fields.Selection(
        selection=ACCESS_LOG_EVENTS,
        index=True,
        readonly=True,
        required=True,
    )
    actor_id = fields.Many2one(
        comodel_name="res.users",
        index=True,
        readonly=True,
        ondelete="set null",
        help="The user whose request made the change, also when the code that "
        "made it ran as the superuser.",
    )
    actor_login = fields.Char(
        readonly=True,
        help="The actor's login when the row was written; it stays when the "
        "user is deleted and Actor empties.",
    )
    subject_user_id = fields.Many2one(
        comodel_name="res.users",
        string="Subject",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    group_id = fields.Many2one(
        comodel_name="res.groups",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    grant_id = fields.Many2one(
        comodel_name="res.users.grant",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    model_name = fields.Char(
        string="Model",
        readonly=True,
    )
    operation = fields.Char(readonly=True)
    res_ids = fields.Char(
        string="Records",
        readonly=True,
        help="The ids the operation touched, the first hundred.",
    )
    cause = fields.Char(readonly=True)
    cause_model = fields.Char(readonly=True)
    cause_res_id = fields.Many2oneReference(
        model_field="cause_model",
        string="Cause Record",
        readonly=True,
    )
    reason = fields.Char(readonly=True)
    link_id = fields.Many2one(
        comodel_name="access.link",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )
    count = fields.Integer(
        readonly=True,
        help="How many grants one row stands for (a migration writes one row).",
    )
    seal = fields.Char(
        copy=False,
        readonly=True,
        help="The keyed hash chaining the row's content hash to the row sealed "
        "before it: a row changed or deleted after it was sealed breaks the "
        "chain from there on.",
    )
    seal_seq = fields.Integer(
        string="Seal Sequence",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    content_hash = fields.Char(
        copy=False,
        readonly=True,
        help="The row's content hashed under the seal key when it was sealed: "
        "the chain seals this hash, so a row erased later keeps its place.",
    )
    erasure_id = fields.Many2one(
        comodel_name="ir.access.log",
        string="Erased By",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
        help="The row recording this row's erasure: its content is gone, its "
        "content hash and its seal stay.",
    )

    def init(self) -> None:
        super().init()
        self.env.cr.execute(APPEND_ONLY)

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        actor_ids = {vals["actor_id"] for vals in vals_list if vals.get("actor_id")}
        logins = {
            user.id: user.login
            for user in self.env["res.users"]
            .with_context(active_test=False)
            .browse(actor_ids)
        }
        for vals in vals_list:
            if vals.get("actor_id") and not vals.get("actor_login"):
                vals["actor_login"] = logins.get(vals["actor_id"]) or False
        return super().create(vals_list)

    @api.model
    def _record(self, vals_list: list[ValuesType]) -> Self:
        if not vals_list:
            return self.browse()
        actor = self.env.uid
        return self.sudo().create([{"actor_id": actor, **vals} for vals in vals_list])

    @api.model
    def _record_privileged(self, model_name: str, operation: str, ids: tuple) -> None:
        privileges = self.env["res.groups"].sudo().browse(sorted(self.env.privileges))
        audited = self.env.registry[model_name]._access_audit
        privileges = privileges if audited else privileges.filtered("audit_privilege")
        if not privileges:
            return
        record_ids = [id_ for id_ in ids if isinstance(id_, int)]
        self._record(
            [
                {
                    "event": "privilege_used",
                    "subject_user_id": self.env.uid,
                    "group_id": privilege.id,
                    "model_name": model_name,
                    "operation": operation,
                    "res_ids": ",".join(map(str, record_ids[:100])),
                    "reason": self.env.context.get("privilege_reason") or False,
                }
                for privilege in privileges
            ]
        )

    def write(self, vals: dict[str, Any]) -> bool:
        if not self:
            return True
        raise UserError(self.env._("The authorization log cannot be changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_purge(self) -> None:
        if not _PURGING.get():
            raise UserError(self.env._("The authorization log cannot be deleted."))

    def _check_log_upkeep(self, reason: str) -> None:
        if self.env.uid != SUPERUSER_ID:
            raise UserError(self.env._("Only the superuser purges or erases the log."))
        if not reason:
            raise UserError(
                self.env._("A purge or an erasure of the log states its reason.")
            )

    def _set_log_operation(self, operation: str) -> None:
        self.env.cr.execute(
            SQL("SELECT set_config('odoo.access_log_operation', %s, true)", operation)
        )

    @api.model
    def _remove_rows(self, domain: list, reason: str) -> int:
        self._check_log_upkeep(reason)
        rows = self.search(domain)
        if not rows:
            return 0
        base = self._purged_chain_start(rows)
        token = _PURGING.set(True)
        try:
            self._set_log_operation("purge")
            rows.unlink()
            self._set_log_operation("")
        finally:
            _PURGING.reset(token)
        if base:
            self.env["ir.config_parameter"].set_param(SEAL_BASE, base)
        self._record(
            [{"event": "log_purged", "count": len(rows), "reason": reason[:255]}]
        )
        return len(rows)

    def _purged_chain_start(self, rows: Self) -> str | None:
        self.flush_model(["seal", "seal_seq"])
        self.env.cr.execute(
            SQL(
                """SELECT last.seal_seq, last.seal,
                          EXISTS (SELECT 1 FROM ir_access_log kept
                                   WHERE kept.seal_seq < last.seal_seq
                                     AND kept.id <> ALL(%(ids)s))
                     FROM ir_access_log last
                    WHERE last.id = ANY(%(ids)s) AND last.seal_seq IS NOT NULL
                 ORDER BY last.seal_seq DESC LIMIT 1""",
                ids=list(rows.ids),
            )
        )
        row = self.env.cr.fetchone()
        if not row:
            return None
        if row[2]:
            raise UserError(
                self.env._(
                    "A purge removes the oldest sealed rows of the log, never "
                    "rows inside its seal chain: erase those instead."
                )
            )
        return f"{row[0]}:{row[1]}"

    @api.model
    def _erase_rows(self, domain: list, reason: str) -> int:
        self._check_log_upkeep(reason)
        if self._get_seal_key() is None:
            raise UserError(
                self.env._(
                    "The authorization log cannot be erased while it cannot be "
                    "sealed: set access_log_seal_key in the server configuration."
                )
            )
        rows = self.search(
            Domain(domain)
            & Domain("erasure_id", "=", False)
            & Domain("event", "!=", "log_erased")
        )
        if not rows:
            return 0
        self._seal()
        cr = self.env.cr
        cr.execute(
            SQL(
                "SELECT id, seal IS NOT NULL FROM ir_access_log "
                "WHERE id = ANY(%s) AND erasure_id IS NULL ORDER BY id",
                rows.ids,
            )
        )
        found = cr.fetchall()
        if not all(sealed for _row_id, sealed in found):
            raise UserError(
                self.env._(
                    "The rows to erase could not be sealed first; the server log "
                    "says why."
                )
            )
        chunks = list(
            itertools.batched(
                (row_id for row_id, _sealed in found), ERASURE_BATCH, strict=False
            )
        )
        if not chunks:
            return 0
        erasures = self._record(
            [
                {
                    "event": "log_erased",
                    "model_name": self._name,
                    "res_ids": ",".join(map(str, chunk)),
                    "count": len(chunk),
                    "reason": reason[:255],
                }
                for chunk in chunks
            ]
        )
        emptied = [
            SQL("%s = NULL", SQL.identifier(name))
            for name, field in self._fields.items()
            if field.store
            and field.column_type
            and name not in (*ERASURE_KEPT, *CHAIN_COLUMNS)
        ]
        self._set_log_operation("erase")
        cr.execute(
            SQL(
                """UPDATE ir_access_log AS log
                      SET erasure_id = erased.erasure_id, %s
                     FROM unnest(%s::int4[], %s::int4[]) AS erased (id, erasure_id)
                    WHERE log.id = erased.id""",
                SQL(", ").join(emptied),
                [row_id for chunk in chunks for row_id in chunk],
                [
                    erasure.id
                    for erasure, chunk in zip(erasures, chunks, strict=True)
                    for _row_id in chunk
                ],
            )
        )
        self._set_log_operation("")
        self.invalidate_model()
        self._seal()
        if not all(erasures.mapped("seal")):
            raise UserError(
                self.env._("The erasure could not be sealed; the server log says why.")
            )
        return sum(map(len, chunks))

    def _seal_base(self) -> tuple[str, int]:
        base = self.env["ir.config_parameter"].get_param(SEAL_BASE) or "0:"
        seq, _colon, seal = base.partition(":")
        return seal, int(seq)

    @api.model
    def _get_seal_key(self) -> bytes | None:
        key = config["access_log_seal_key"]
        if not key:
            return None
        if len(key) < SEAL_KEY_MIN_LENGTH:
            raise UserError(
                self.env._(
                    "access_log_seal_key is shorter than %(length)s characters.",
                    length=SEAL_KEY_MIN_LENGTH,
                )
            )
        return key.encode()

    @api.model
    def _sealed_content(self) -> SQL:
        skipped = {
            *CHAIN_COLUMNS,
            *(
                name
                for name, field in self._fields.items()
                if field.type == "many2one" and field.ondelete == "set null"
            ),
        }
        return SQL("jsonb_strip_nulls(to_jsonb(log) - %s::text[])", sorted(skipped))

    def _lock_seal_chain(self) -> None:
        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtext('ir_access_log_seal'))"
        )

    def _store_seals(
        self, ids: list[int], seqs: list[int], hashes: list[str], seals: list[str]
    ) -> None:
        self.env.cr.execute(
            SQL(
                """UPDATE ir_access_log AS log
                      SET seal = sealed.seal, seal_seq = sealed.seq,
                          content_hash = sealed.content_hash
                     FROM unnest(%s::int4[], %s::int4[], %s::varchar[], %s::varchar[])
                          AS sealed (id, seq, content_hash, seal)
                    WHERE log.id = sealed.id""",
                ids,
                seqs,
                hashes,
                seals,
            )
        )

    def _store_seal_head(self, seq: int, seal: str) -> None:
        self.invalidate_model(["seal", "seal_seq", "content_hash"])
        self.env["ir.config_parameter"].set_param(SEAL_HEAD, f"{seq}:{seal}")
        _logger.info("authorization log sealed through row %s: %s", seq, seal)

    @api.model
    def _cron_seal(self) -> None:
        self._seal()

    @api.model
    def _seal(self, batch: int = 5000) -> int:
        if (key := self._get_seal_key()) is None:
            _logger.warning(NO_SEAL_KEY, SEAL_KEY_MIN_LENGTH)
            return 0
        cr = self.env.cr
        self._lock_seal_chain()
        if not self._adopt_legacy_chain(key):
            return 0
        cr.execute(
            "SELECT seal, seal_seq, content_hash FROM ir_access_log "
            "WHERE seal_seq IS NOT NULL ORDER BY seal_seq DESC LIMIT 2"
        )
        tail = cr.fetchall()
        if not tail:
            previous, seq = self._seal_base()
        else:
            previous, seq, content_hash = tail[0]
            before = tail[1][0] if len(tail) > 1 else self._seal_base()[0]
            if not content_hash or _chained(key, before, content_hash) != previous:
                _logger.error(
                    "The authorization log is not sealed: its last sealed row "
                    "(%s) does not verify under access_log_seal_key, so the key "
                    "or the row changed since it was sealed",
                    seq,
                )
                return 0
        content = self._sealed_content()
        sealed = 0
        while True:
            cr.execute(
                SQL(
                    "SELECT id, %s FROM ir_access_log log "
                    "WHERE seal IS NULL ORDER BY id LIMIT %s",
                    content,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            seqs, hashes, seals = [], [], []
            for _row_id, row_content in rows:
                seq += 1
                content_hash = _content_hash(key, row_content)
                previous = _chained(key, previous, content_hash)
                seqs.append(seq)
                hashes.append(content_hash)
                seals.append(previous)
            self._store_seals([row[0] for row in rows], seqs, hashes, seals)
            sealed += len(rows)
        if sealed:
            self._store_seal_head(seq, previous)
        return sealed

    def _adopt_legacy_chain(self, key: bytes) -> bool:
        if not self.env["ir.config_parameter"].get_param(SEAL_LEGACY):
            return True
        if broken := self._get_seal_chain_error():
            if self.search_count(
                [("event", "=", "log_chain_broken"), ("reason", "=", broken[:255])]
            ):
                _logger.error("The authorization log is still not sealed: %s", broken)
                return False
            _logger.critical(
                "The authorization log's seal chain was broken before it was "
                "keyed, so it is not sealed again and sealing stops until the rows "
                "sealed before the key are purged "
                '(_remove_rows([("seal_seq", "!=", False)], reason)): %s',
                broken,
            )
            self._record([{"event": "log_chain_broken", "reason": broken[:255]}])
            return False
        resealed = self._rewrite_seals(key)
        _logger.info("authorization log: %s rows sealed again under the key", resealed)
        return True

    def _get_legacy_chain_error(self, batch: int = 5000) -> str | None:
        cr = self.env.cr
        previous, expected = self._seal_base()
        if expected:
            cr.execute(
                "SELECT id FROM ir_access_log WHERE seal_seq <= %s LIMIT 1", [expected]
            )
            if kept := cr.fetchone():
                return f"the start of the chain was moved past sealed row {kept[0]}"
        expected += 1
        while True:
            cr.execute(
                SQL(
                    "SELECT id, %s, seal, seal_seq FROM ir_access_log log "
                    "WHERE seal_seq >= %s ORDER BY seal_seq LIMIT %s",
                    LEGACY_CONTENT,
                    expected,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            for row_id, content, seal, seq in rows:
                if seq != expected:
                    return f"sealed row {expected} is missing before row {row_id}"
                previous = _legacy_chained(previous, content)
                if previous != seal:
                    return f"row {row_id} changed after it was sealed"
                expected += 1
        head = self.env["ir.config_parameter"].get_param(SEAL_HEAD) or "0:"
        head_seq, _colon, head_seal = head.partition(":")
        if int(head_seq) >= expected:
            return f"sealed rows {expected} to {head_seq} are missing"
        if int(head_seq) == expected - 1 and head_seal and head_seal != previous:
            return "the last sealed row changed after it was sealed"
        return None

    @api.model
    def _reseal(self, previous_key: str) -> int:
        if self.env.uid != SUPERUSER_ID:
            raise UserError(self.env._("Only the superuser re-seals the log."))
        if (key := self._get_seal_key()) is None:
            raise UserError(
                self.env._(
                    "access_log_seal_key is not set in the server configuration."
                )
            )
        self._lock_seal_chain()
        if broken := self._get_seal_chain_error(key=previous_key.encode()):
            raise UserError(
                self.env._(
                    "The seal chain does not verify under the previous key, so it "
                    "is not sealed again: %(broken)s",
                    broken=broken,
                )
            )
        return self._rewrite_seals(key)

    def _rewrite_seals(self, key: bytes, batch: int = 5000) -> int:
        cr = self.env.cr
        self._lock_seal_chain()
        previous, seq = self._seal_base()
        content = self._sealed_content()
        self._set_log_operation("reseal")
        rewritten = 0
        while True:
            cr.execute(
                SQL(
                    "SELECT id, %s, seal_seq, content_hash, erasure_id IS NOT NULL "
                    "FROM ir_access_log log WHERE seal_seq > %s "
                    "ORDER BY seal_seq LIMIT %s",
                    content,
                    seq,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            seqs, hashes, seals = [], [], []
            for _row_id, row_content, seq, content_hash, erased in rows:
                if not erased:
                    content_hash = _content_hash(key, row_content)
                previous = _chained(key, previous, content_hash)
                seqs.append(seq)
                hashes.append(content_hash)
                seals.append(previous)
            self._store_seals([row[0] for row in rows], seqs, hashes, seals)
            rewritten += len(rows)
        self._set_log_operation("")
        self.env["ir.config_parameter"].set_param(SEAL_LEGACY, False)
        if rewritten:
            self._store_seal_head(seq, previous)
        return rewritten

    @api.model
    def _cron_check_seal_chain(self) -> None:
        if self._get_seal_key() is None:
            _logger.warning(NO_SEAL_KEY, SEAL_KEY_MIN_LENGTH)
            return
        if (broken := self._get_seal_chain_error()) is None:
            return
        _logger.critical("The authorization log's seal chain is broken: %s", broken)
        if not self.search_count(
            [("event", "=", "log_chain_broken"), ("reason", "=", broken[:255])]
        ):
            self._record([{"event": "log_chain_broken", "reason": broken[:255]}])

    @api.model
    def _get_seal_chain_error(
        self, batch: int = 5000, key: bytes | None = None
    ) -> str | None:
        if self.env["ir.config_parameter"].get_param(SEAL_LEGACY):
            if broken := self._get_legacy_chain_error(batch):
                return f"before the key: {broken}"
            return None
        if key is None and (key := self._get_seal_key()) is None:
            raise UserError(
                self.env._(
                    "The authorization log's seals cannot be checked: "
                    "access_log_seal_key is not set in the server configuration."
                )
            )
        cr = self.env.cr
        previous, expected = self._seal_base()
        if expected:
            cr.execute(
                "SELECT id FROM ir_access_log WHERE seal_seq <= %s "
                "ORDER BY seal_seq DESC LIMIT 1",
                [expected],
            )
            if kept := cr.fetchone():
                return (
                    f"the start of the chain was moved past sealed row {kept[0]}, "
                    "which no purge removed"
                )
        expected += 1
        content = self._sealed_content()
        while True:
            cr.execute(
                SQL(
                    """SELECT log.id, %s, log.seal, log.seal_seq, log.content_hash,
                              log.erasure_id IS NOT NULL,
                              COALESCE(erasure.event = 'log_erased'
                                       AND erasure.seal IS NOT NULL
                                       AND log.id::text = ANY(
                                           string_to_array(erasure.res_ids, ',')),
                                       false)
                         FROM ir_access_log log
                    LEFT JOIN ir_access_log erasure ON erasure.id = log.erasure_id
                        WHERE log.seal_seq >= %s
                     ORDER BY log.seal_seq LIMIT %s""",
                    content,
                    expected,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            for row_id, row_content, seal, seq, content_hash, erased, named in rows:
                if seq != expected:
                    return (
                        f"sealed row {expected} is missing: a sealed row was "
                        f"deleted before row {row_id}"
                    )
                if not content_hash:
                    return (
                        f"row {row_id} was sealed before the chain was keyed and "
                        "was never sealed again"
                    )
                if erased:
                    if not named:
                        return f"row {row_id} was erased by no erasure naming it"
                    if row_content.keys() - set(ERASURE_KEPT):
                        return f"row {row_id} changed after it was erased"
                elif _content_hash(key, row_content) != content_hash:
                    return f"row {row_id} changed after it was sealed"
                previous = _chained(key, previous, content_hash)
                if previous != seal:
                    return f"row {row_id} changed after it was sealed"
                expected += 1
        head = self.env["ir.config_parameter"].get_param(SEAL_HEAD) or "0:"
        head_seq, _colon, head_seal = head.partition(":")
        if int(head_seq) >= expected:
            return (
                f"sealed rows {expected} to {head_seq} are missing: the end of "
                "the chain was deleted"
            )
        if int(head_seq) == expected - 1 and head_seal and head_seal != previous:
            return "the last sealed row changed after it was sealed"
        return None
