import contextvars
import hashlib
import json
import logging
from typing import Any, Self

from odoo import api, fields, models
from odoo.api import SUPERUSER_ID, ValuesType
from odoo.exceptions import UserError
from odoo.tools import SQL

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
    ("log_chain_broken", "Log seal chain broken"),
]

# a row's sealed content: the row as the database holds it, less its seal,
# the references a deletion elsewhere empties (ON DELETE SET NULL) and the
# columns no value was written to, so a column a module adds later leaves the
# rows sealed before it as they were
SEALED_CONTENT = SQL(
    """
    jsonb_strip_nulls(
        to_jsonb(log) - ARRAY['seal', 'seal_seq', 'actor_id', 'subject_user_id',
                              'group_id', 'grant_id', 'link_id', 'create_uid',
                              'write_uid']
    )
    """
)

# the database refuses any change to a row but its sealing, once, and the
# emptying of a reference whose record was deleted; and any delete but a purge
# (a plain string: its plpgsql % placeholders are no query parameters)
APPEND_ONLY = """
    CREATE OR REPLACE FUNCTION ir_access_log_append_only() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        changed text;
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF current_setting('odoo.access_log_purge', true) = 'on' THEN
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
            IF changed IN ('seal', 'seal_seq') AND OLD.seal IS NULL THEN
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

# the last row sealed, as "sequence:seal": a sealed row deleted from the end of
# the chain leaves no gap, only a head the chain no longer reaches
SEAL_HEAD = "base.access_log_seal_head"

_PURGING: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "access_log_purging", default=False
)


def _keep_rows(records: Any) -> None:
    # uninstalling the module that wrote an event keeps its rows: the log
    # outlives the code that wrote it
    return


def kept_on_uninstall(events: list[tuple[str, str]]) -> dict[str, Any]:
    """The ondelete of the log events a module adds: its rows stay."""
    return dict.fromkeys((event for event, _label in events), _keep_rows)


def _chained(previous: str, content: dict[str, Any]) -> str:
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
        help="The hash chaining the row to the one sealed before it: a row changed "
        "or deleted after it was sealed breaks the chain from there on.",
    )
    seal_seq = fields.Integer(
        string="Seal Sequence",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )

    def init(self) -> None:
        super().init()
        self.env.cr.execute(APPEND_ONLY)

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        # every row names its actor by login too, whichever path writes it; a
        # row is only ever written by the log's own elevated paths (_record,
        # the refusal's cursor of its own), which read any user's login
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
        # a create, write or delete made under a privilege, on a model that
        # declares _access_audit or under a privilege that asks for it
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
        # nobody deletes a row, the superuser included, but through _remove_rows,
        # which the log records; the database refuses any other delete
        if not _PURGING.get():
            raise UserError(self.env._("The authorization log cannot be deleted."))

    @api.model
    def _remove_rows(self, domain: list, reason: str) -> int:
        """Delete the rows `domain` matches, for a stated reason (retention, an
        erasure request); only the superuser does, and the purge is logged."""
        if self.env.uid != SUPERUSER_ID:
            raise UserError(self.env._("Only the superuser purges the log."))
        if not reason:
            raise UserError(self.env._("A purge of the log states its reason."))
        rows = self.with_context(active_test=False).search(domain)
        if not rows:
            return 0
        token = _PURGING.set(True)
        try:
            self.env.cr.execute("SET LOCAL odoo.access_log_purge = 'on'")
            rows.unlink()
            self.env.cr.execute("SET LOCAL odoo.access_log_purge = 'off'")
        finally:
            _PURGING.reset(token)
        self._record(
            [{"event": "log_purged", "count": len(rows), "reason": reason[:255]}]
        )
        return len(rows)

    @api.model
    def _cron_seal(self) -> None:
        self._seal()

    @api.model
    def _seal(self, batch: int = 5000) -> int:
        # chain every committed row not sealed yet, in the order it is sealed:
        # a row a transaction still holds is sealed once it commits
        cr = self.env.cr
        cr.execute("SELECT pg_advisory_xact_lock(hashtext('ir_access_log_seal'))")
        cr.execute(
            "SELECT seal, seal_seq FROM ir_access_log "
            "WHERE seal_seq IS NOT NULL ORDER BY seal_seq DESC LIMIT 1"
        )
        previous, seq = cr.fetchone() or ("", 0)
        sealed = 0
        while True:
            cr.execute(
                SQL(
                    "SELECT id, %s FROM ir_access_log log "
                    "WHERE seal IS NULL ORDER BY id LIMIT %s",
                    SEALED_CONTENT,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            for row_id, content in rows:
                seq += 1
                previous = _chained(previous, content)
                cr.execute(
                    "UPDATE ir_access_log SET seal = %s, seal_seq = %s WHERE id = %s",
                    [previous, seq, row_id],
                )
            sealed += len(rows)
        if sealed:
            self.invalidate_model(["seal", "seal_seq"])
            self.env["ir.config_parameter"].set_param(SEAL_HEAD, f"{seq}:{previous}")
            # the server log keeps the head outside the database too
            _logger.info("authorization log sealed through row %s: %s", seq, previous)
        return sealed

    @api.model
    def _cron_check_seal_chain(self) -> None:
        if (broken := self._get_seal_chain_error()) is None:
            return
        _logger.critical("The authorization log's seal chain is broken: %s", broken)
        if not self.search_count(
            [("event", "=", "log_chain_broken"), ("reason", "=", broken[:255])]
        ):
            self._record([{"event": "log_chain_broken", "reason": broken[:255]}])

    @api.model
    def _get_seal_chain_error(self, batch: int = 5000) -> str | None:
        """Where the seal chain breaks, or None: a sealed row changed, or one
        missing from the sequence."""
        cr = self.env.cr
        previous, expected = "", 1
        while True:
            cr.execute(
                SQL(
                    "SELECT id, %s, seal, seal_seq FROM ir_access_log log "
                    "WHERE seal_seq >= %s ORDER BY seal_seq LIMIT %s",
                    SEALED_CONTENT,
                    expected,
                    batch,
                )
            )
            rows = cr.fetchall()
            if not rows:
                break
            for row_id, content, seal, seq in rows:
                if seq != expected:
                    return (
                        f"sealed row {expected} is missing: a sealed row was "
                        f"deleted before row {row_id}"
                    )
                previous = _chained(previous, content)
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
