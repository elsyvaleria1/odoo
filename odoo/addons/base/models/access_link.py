import base64
import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Self

from odoo import SUPERUSER_ID, api, fields, models, tools
from odoo.api import ValuesType
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.fields import Command, Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

LINK_ROLES = [
    ("view", "View"),
    ("comment", "Comment"),
    ("edit", "Edit"),
]
ROLE_RANK = {role: rank for rank, (role, _label) in enumerate(LINK_ROLES)}

LINK_AUDIENCES = [
    ("anyone", "Anyone with the link"),
    ("signed_in", "Signed-in users"),
    ("partners", "These people"),
]

LINK_CAUSES = [
    ("share", "Shared by hand"),
    ("notification", "Notification"),
    ("request", "Request"),
    ("migration", "Migration"),
    ("system", "System"),
]

LINK_ACTIONS = [
    ("view", "View"),
    ("download", "Download"),
    ("comment", "Comment"),
    ("act", "Act"),
]

DEFAULT_LIFETIME = {
    "share": timedelta(days=30),
    "notification": timedelta(days=365),
    "request": timedelta(days=365),
    "system": timedelta(days=365),
    "migration": timedelta(days=365),
}

TOKEN_SCOPE = tools.register_signed_scope(
    "access.link",
    purpose="derive a share link's token from its nonce; the token opens the "
    "one record the link names, at the link's role",
    lifetime="the link's own date_to: the token is stored hashed and dies with "
    "the link",
)
MANAGE = "base.privilege_manage_links"
MIN_TOKEN_LENGTH = 16
MAX_TOKEN_LENGTH = 128

SERVER_FIELDS = frozenset(
    {
        "res_model",
        "res_id",
        "role",
        "audience",
        "partner_id",
        "audience_partner_ids",
        "company_id",
        "token_hash",
        "token_nonce",
        "token_hint",
        "revoked_at",
        "revoked_by_id",
        "revoke_reason",
        "cause",
        "cause_model",
        "cause_res_id",
        "legacy_source",
        "last_used_at",
        "use_count",
    }
)


class LinkRefused(Exception):
    pass


class LinkLoginRequired(Exception):
    pass


@dataclass(frozen=True, slots=True)
class LinkResolution:
    link: Any
    record: Any

    @property
    def partner(self) -> Any:
        return self.link.partner_id


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccessLink(models.Model):
    _name = "access.link"
    _description = "External Link"
    _order = "id desc"
    _rec_name = "record_name"
    _allow_sudo_commands = False

    res_model = fields.Char(
        string="Model",
        index=True,
        readonly=True,
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record",
        index=True,
        readonly=True,
        required=True,
    )
    record_name = fields.Char(
        string="Shared Record",
        compute="_compute_record_name",
    )
    role = fields.Selection(
        selection=LINK_ROLES,
        default="view",
        readonly=True,
        required=True,
        help="What the link lets its holder do: view the record; view it and "
        "comment as the person it was issued to; or edit it.",
    )
    audience = fields.Selection(
        selection=LINK_AUDIENCES,
        default="anyone",
        readonly=True,
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Issued To",
        index=True,
        readonly=True,
        ondelete="set null",
        help="The person the link was sent to: what they write through it is "
        "theirs, and revoking the link ends their access only.",
    )
    audience_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="access_link_audience_partner_rel",
        column1="link_id",
        column2="partner_id",
        string="People",
        readonly=True,
    )
    token_hash = fields.Char(
        copy=False,
        readonly=True,
        required=True,
        classification="base.link_token",
        write_groups=MANAGE,
        groups=MANAGE,
    )
    token_nonce = fields.Char(
        copy=False,
        readonly=True,
        classification="base.link_token",
        write_groups=MANAGE,
        groups=MANAGE,
        help="Set when the token is derived from the database secret, so the "
        "link can be shown again; empty for a token carried over from before.",
    )
    token_hint = fields.Char(
        string="Token",
        readonly=True,
        help="The first characters of the token, to tell links apart.",
    )
    date_to = fields.Datetime(
        string="Expires",
        index=True,
    )
    revoked_at = fields.Datetime(
        copy=False,
        readonly=True,
    )
    revoked_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="set null",
    )
    revoke_reason = fields.Char(readonly=True)
    cause = fields.Selection(
        selection=LINK_CAUSES,
        default="share",
        readonly=True,
        required=True,
    )
    cause_model = fields.Char(readonly=True)
    cause_res_id = fields.Many2oneReference(
        model_field="cause_model",
        string="Cause Record",
        readonly=True,
    )
    legacy_source = fields.Char(
        readonly=True,
        help="The column the token was stored in before links were rows.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        index=True,
        readonly=True,
        ondelete="set null",
    )
    last_used_at = fields.Datetime(
        string="Last Used",
        copy=False,
        readonly=True,
    )
    use_count = fields.Integer(
        string="Uses",
        copy=False,
        readonly=True,
    )
    use_ids = fields.One2many(
        comodel_name="access.link.use",
        inverse_name="link_id",
        string="Uses Log",
        readonly=True,
    )
    state = fields.Selection(
        selection=[("live", "Live"), ("expired", "Expired"), ("revoked", "Revoked")],
        compute="_compute_state",
        search="_search_state",
    )

    _token_hash_unique = models.Constraint(
        "UNIQUE (token_hash)",
        "A token opens one link.",
    )
    _anyone_expires = models.Constraint(
        "CHECK (audience <> 'anyone' OR date_to IS NOT NULL "
        "OR revoked_at IS NOT NULL OR expiry_waived)",
        "A link anyone can use has an expiry date.",
    )
    expiry_waived = fields.Boolean(
        readonly=True,
        write_classification="base.link_token",
        write_groups="base.group_system",
        help="An administrator chose that this link anyone can use never expires.",
    )
    _res_index = models.Index("(res_model, res_id)")

    @api.depends("res_model", "res_id")
    def _compute_record_name(self) -> None:
        by_model: dict[str, list[Self]] = {}
        for link in self:
            by_model.setdefault(link.res_model, []).append(link)
        for model_name, links in by_model.items():
            if model_name not in self.env:
                for link in links:
                    link.record_name = f"{model_name},{link.res_id}"
                continue
            records = self.env[model_name].browse([link.res_id for link in links])
            names = {
                record.id: record.display_name
                for record in records.exists()._filtered_access("read")
            }
            for link in links:
                link.record_name = names.get(link.res_id, f"{model_name},{link.res_id}")

    @api.depends("revoked_at", "date_to")
    def _compute_state(self) -> None:
        now = fields.Datetime.now()
        for link in self:
            if link.revoked_at:
                link.state = "revoked"
            elif link.date_to and link.date_to <= now:
                link.state = "expired"
            else:
                link.state = "live"

    def _search_state(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "="):
            return NotImplemented
        states = {value} if isinstance(value, str) else set(value)
        now = fields.Datetime.now()
        by_state = {
            "revoked": Domain("revoked_at", "!=", False),
            "expired": Domain("revoked_at", "=", False)
            & Domain("date_to", "!=", False)
            & Domain("date_to", "<=", now),
            "live": self._live_domain(now),
        }
        return Domain.OR(by_state[state] for state in states if state in by_state)

    @api.model
    def _live_domain(self, now: datetime | None = None) -> Domain:
        now = now or fields.Datetime.now()
        return Domain("revoked_at", "=", False) & (
            Domain("date_to", "=", False) | Domain("date_to", ">", now)
        )


    @api.model
    def _derive_token(self, nonce: str) -> str:
        digest = tools.hmac(self.env(su=True), TOKEN_SCOPE, nonce)
        return base64.urlsafe_b64encode(bytes.fromhex(digest)[:24]).decode()

    def _token(self) -> str | None:
        self.check_singleton()
        return self._tokens().get(self.id)

    def _tokens(self) -> dict[int, str]:
        if not self.ids:
            return {}
        self.env.cr.execute(
            SQL(
                "SELECT id, token_nonce, token_hash FROM access_link "
                "WHERE id IN %s AND token_nonce IS NOT NULL",
                tuple(self.ids),
            )
        )
        tokens = {}
        for link_id, nonce, stored_hash in self.env.cr.fetchall():
            token = self._derive_token(nonce)
            if tools.consteq(hash_token(token), stored_hash):
                tokens[link_id] = token
        return tokens


    @api.model
    def _find_reusable(
        self,
        record: models.BaseModel,
        *,
        partner: models.BaseModel | None = None,
        role: str = "view",
        audience: str = "anyone",
        audience_partners: models.BaseModel | None = None,
        cause: str = "share",
        cause_record: models.BaseModel | None = None,
        date_to: datetime | None = None,
    ) -> tuple[Self, str | None]:
        record.check_singleton()
        self._check_may_issue(record, role)
        partner = partner or self.env["res.partner"]
        people = set((audience_partners or partner).ids)
        found = (
            self.with_privilege(
                "base.privilege_manage_links",
                reason=f"find a link to {record._name} to hand out again",
            )
            .search(
                Domain("res_model", "=", record._name)
                & Domain("res_id", "=", record.id)
                & Domain("partner_id", "=", partner.id or False)
                & Domain("role", "=", role)
                & Domain("audience", "=", audience)
                & Domain("cause", "=", cause)
                & Domain(
                    "cause_model", "=", cause_record._name if cause_record else False
                )
                & Domain(
                    "cause_res_id", "=", cause_record.id if cause_record else False
                )
                & Domain("token_nonce", "!=", False)
                & (Domain("date_to", "=", date_to) if date_to else Domain.TRUE)
                & self._live_domain(),
                order="id desc",
            )
            .filtered(
                lambda link: (
                    audience != "partners"
                    or set(link.audience_partner_ids.ids) == people
                )
            )[:1]
        )
        token = found._token() if found else None
        _debug.logic(
            "link.reusable",
            model=record._name,
            role=role,
            cause=cause,
            link=found.id if token else None,
        )
        if not token:
            return self.browse(), None
        return found.with_env(self.env), token

    @api.model
    def _issue(
        self,
        record: models.BaseModel,
        *,
        partner: models.BaseModel | None = None,
        role: str = "view",
        audience: str = "anyone",
        audience_partners: models.BaseModel | None = None,
        date_to: datetime | None = None,
        cause: str = "share",
        cause_record: models.BaseModel | None = None,
        waive_expiry: bool = False,
    ) -> tuple[Self, str]:
        reusable, token = self._find_reusable(
            record,
            partner=partner,
            role=role,
            audience=audience,
            audience_partners=audience_partners,
            cause=cause,
            cause_record=cause_record,
            date_to=date_to,
        )
        if token:
            _debug.logic("link.reused", link=reusable.id, model=record._name)
            return reusable, token
        partner = partner or self.env["res.partner"]
        if audience == "anyone" and not date_to and not waive_expiry:
            date_to = fields.Datetime.now() + DEFAULT_LIFETIME[cause]
        issuer = self.with_privilege(
            "base.privilege_manage_links", reason=f"issue a link to {record._name}"
        )
        nonce = secrets.token_hex(16)
        token = self._derive_token(nonce)
        link = issuer.create(
            {
                "res_model": record._name,
                "res_id": record.id,
                "role": role,
                "audience": audience,
                "partner_id": partner.id or False,
                "audience_partner_ids": [
                    Command.set((audience_partners or partner).ids)
                ]
                if audience == "partners"
                else [],
                "token_hash": hash_token(token),
                "token_nonce": nonce,
                "token_hint": token[:4],
                "date_to": date_to or False,
                **({"expiry_waived": True} if waive_expiry and not date_to else {}),
                "cause": cause,
                "cause_model": cause_record._name if cause_record else False,
                "cause_res_id": cause_record.id if cause_record else False,
                "company_id": self._record_company(record),
            }
        )
        link._log("link_created")
        _debug.lifecycle("link.issued", link=link.id, model=record._name, role=role)
        return link.with_env(self.env), token

    @api.model
    def _issue_each(
        self,
        records: models.BaseModel,
        *,
        partner_field: str,
        role: str = "view",
        cause: str = "notification",
        date_to: Callable[[models.BaseModel], datetime | None] | None = None,
    ) -> dict[int, str]:
        if not records:
            return {}
        issuer = self._each_issuer(records, role)
        found = issuer.search(
            Domain("res_model", "=", records._name)
            & Domain("res_id", "in", records.ids)
            & Domain("role", "=", role)
            & Domain("audience", "=", "anyone")
            & Domain("cause", "=", cause)
            & Domain("token_nonce", "!=", False)
            & self._live_domain(),
            order="id desc",
        )
        tokens: dict[int, str] = {}
        if found:
            shown = found._tokens()
            partner_of = {record.id: record[partner_field].id for record in records}
            for link in found:
                if (
                    link.res_id not in tokens
                    and link.partner_id.id == partner_of.get(link.res_id)
                    and (token := shown.get(link.id))
                ):
                    tokens[link.res_id] = token
        missing = records.filtered(lambda record: record.id not in tokens)
        tokens.update(
            issuer._create_each(
                missing,
                partner_field=partner_field,
                role=role,
                cause=cause,
                date_to=date_to,
            )
        )
        return tokens

    @api.model
    def _issue_each_new(
        self,
        records: models.BaseModel,
        *,
        partner_field: str,
        role: str = "view",
        cause: str = "notification",
        date_to: Callable[[models.BaseModel], datetime | None] | None = None,
    ) -> dict[int, str]:
        if not records:
            return {}
        return self._each_issuer(records, role)._create_each(
            records,
            partner_field=partner_field,
            role=role,
            cause=cause,
            date_to=date_to,
        )

    @api.model
    def _each_issuer(self, records: models.BaseModel, role: str) -> Self:
        if not self._runs_the_machinery():
            records.check_access("write" if role == "edit" else "read")
        return self.with_privilege(
            "base.privilege_manage_links", reason=f"issue links to {records._name}"
        )

    @api.model
    def _create_each(
        self,
        records: models.BaseModel,
        *,
        partner_field: str,
        role: str,
        cause: str,
        date_to: Callable[[models.BaseModel], datetime | None] | None,
    ) -> dict[int, str]:
        companies = self._record_companies(records)
        now = fields.Datetime.now()
        tokens: dict[int, str] = {}
        vals_list = []
        for record in records:
            nonce = secrets.token_hex(16)
            tokens[record.id] = token = self._derive_token(nonce)
            vals_list.append(
                {
                    "res_model": records._name,
                    "res_id": record.id,
                    "role": role,
                    "audience": "anyone",
                    "partner_id": record[partner_field].id or False,
                    "token_hash": hash_token(token),
                    "token_nonce": nonce,
                    "token_hint": token[:4],
                    "date_to": (date_to and date_to(record))
                    or now + DEFAULT_LIFETIME[cause],
                    "cause": cause,
                    "company_id": companies.get(record.id, False),
                }
            )
        if vals_list:
            self.create(vals_list)._log("link_created")
            _debug.lifecycle(
                "link.issued_each", model=records._name, count=len(vals_list)
            )
        return tokens

    @api.model
    def _issue_many(
        self,
        record: models.BaseModel,
        partners: models.BaseModel,
        *,
        role: str = "view",
        cause: str = "share",
        date_to: datetime | None = None,
    ) -> dict[int, str]:
        record.check_singleton()
        self._check_may_issue(record, role)
        date_to = date_to or fields.Datetime.now() + DEFAULT_LIFETIME[cause]
        issuer = self.with_privilege(
            "base.privilege_manage_links", reason=f"issue links to {record._name}"
        )
        tokens: dict[int, str] = {}
        found = issuer.search(
            Domain("res_model", "=", record._name)
            & Domain("res_id", "=", record.id)
            & Domain("partner_id", "in", partners.ids)
            & Domain("role", "=", role)
            & Domain("audience", "=", "anyone")
            & Domain("cause", "=", cause)
            & Domain("token_nonce", "!=", False)
            & self._live_domain(),
            order="id desc",
        )
        shown = found._tokens()
        for link in found:
            if link.partner_id.id not in tokens and (token := shown.get(link.id)):
                tokens[link.partner_id.id] = token
        vals_list = []
        company = self._record_company(record)
        for partner in partners.filtered(lambda p: p.id not in tokens):
            nonce = secrets.token_hex(16)
            tokens[partner.id] = token = self._derive_token(nonce)
            vals_list.append(
                {
                    "res_model": record._name,
                    "res_id": record.id,
                    "role": role,
                    "audience": "anyone",
                    "partner_id": partner.id,
                    "token_hash": hash_token(token),
                    "token_nonce": nonce,
                    "token_hint": token[:4],
                    "date_to": date_to,
                    "cause": cause,
                    "company_id": company,
                }
            )
        if vals_list:
            issuer.create(vals_list)._log("link_created")
            _debug.lifecycle(
                "link.issued_many", model=record._name, count=len(vals_list)
            )
        return tokens

    @api.model
    def _record_companies(self, records: models.BaseModel) -> dict[int, int]:
        field = records._fields.get("company_id")
        if not records or not field or not field.store or field.type != "many2one":
            return {}
        records.flush_recordset(["company_id"])
        self.env.cr.execute(
            SQL(
                "SELECT id, company_id FROM %s WHERE id = ANY(%s)",
                SQL.identifier(records._table),
                list(records.ids),
            )
        )
        return dict(self.env.cr.fetchall())

    def _record_company(self, record: models.BaseModel) -> int | bool:
        field = record._fields.get("company_id")
        if not field or not field.store or field.type != "many2one":
            return False
        record.flush_recordset(["company_id"])
        self.env.cr.execute(
            SQL(
                "SELECT company_id FROM %s WHERE id = %s",
                SQL.identifier(record._table),
                record.id,
            )
        )
        row = self.env.cr.fetchone()
        return (row and row[0]) or False

    @api.model
    def _check_may_issue(self, record: models.BaseModel, role: str) -> None:
        if self._runs_the_machinery():
            return
        record.check_access("write" if role == "edit" else "read")


    @api.model
    def _resolve(
        self,
        token: Any,
        *,
        model: str | None = None,
        res_id: int | None = None,
        role: str = "view",
        action: str | None = "view",
    ) -> LinkResolution:
        if (
            not isinstance(token, str)
            or not MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH
        ):
            raise LinkRefused
        digest = hash_token(token)
        self.env.cr.execute(
            SQL(
                "SELECT id FROM access_link WHERE token_hash = %s",
                digest,
            )
        )
        row = self.env.cr.fetchone()
        if not row:
            _debug.logic("link.refused", reason="unknown")
            raise LinkRefused
        link = self.with_privilege(
            "base.privilege_resolve_links", reason="resolve a presented token"
        ).browse(row[0])
        reason = link._refusal(model, res_id, role)
        if reason:
            _debug.logic("link.refused", link=link.id, reason=reason)
            raise LinkRefused
        if not link._admits_session():
            if self.env.user._is_public():
                raise LinkLoginRequired
            _debug.logic("link.refused", link=link.id, reason="audience")
            raise LinkRefused
        record = self.env[link.res_model].sudo().browse(link.res_id).exists()
        if not record:
            _debug.logic("link.refused", link=link.id, reason="record_gone")
            raise LinkRefused
        if action:
            link._record_use(action)
        return LinkResolution(link=link, record=record)

    @api.model
    def _open_record(
        self,
        model: str,
        res_id: int,
        access_token: str | None = None,
        role: str = "view",
    ) -> models.BaseModel:
        record = self.env[model].browse(res_id)
        record_sudo = record.with_user(SUPERUSER_ID).exists()
        if not record_sudo:
            raise MissingError(self.env._("This document does not exist."))
        if record.has_access("read"):
            _debug.logic("link.opened", model=model, by="session")
            return record_sudo
        try:
            resolution = self._resolve(
                access_token,
                model=model,
                res_id=record_sudo.id,
                role=role,
                action="view" if role == "view" else "act",
            )
        except LinkRefused, LinkLoginRequired:
            raise AccessError(
                self.env._("This link does not open this record.")
            ) from None
        self._note_presented(resolution.record, access_token)
        return record_sudo

    @api.model
    def _note_presented(self, record: models.BaseModel, token: str) -> None:
        if not request:
            return
        presented = getattr(request, "presented_link_tokens", None)
        if not isinstance(presented, dict):
            presented = request.presented_link_tokens = {}
        presented[record._name, record.id] = token
        if "access_token" in record._fields:
            record.invalidate_recordset(["access_token"])

    def _refusal(self, model: str | None, res_id: int | None, role: str) -> str:
        self.check_singleton()
        if model and self.res_model != model:
            return "other_model"
        if res_id is not None and self.res_id != int(res_id):
            return "other_record"
        if self.revoked_at:
            return "revoked"
        if self.date_to and self.date_to <= fields.Datetime.now():
            return "expired"
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            return "role"
        return self._record_refusal()

    def _record_refusal(self) -> str:
        return ""

    def _admits_session(self) -> bool:
        self.check_singleton()
        if self.audience == "anyone":
            return True
        user = self.env.user
        if user._is_public():
            return False
        if self.audience == "signed_in":
            return True
        partner = user.partner_id
        allowed = self.audience_partner_ids | self.partner_id
        return bool(
            partner & allowed
            or partner.commercial_partner_id & allowed.commercial_partner_id
        )

    def _record_use(self, action: str) -> None:
        self.check_singleton()
        user_id = 0 if self.env.user._is_public() else self.env.uid
        remote_addr = self.env["ir.http"]._get_request_remote_addr() or ""
        statements = [
            SQL(
                """
                INSERT INTO access_link_use
                    (link_id, bucket, remote_addr, user_id, action, count)
                VALUES (%s, date_trunc('hour', now() AT TIME ZONE 'UTC'), %s, %s, %s, 1)
                ON CONFLICT (link_id, bucket, remote_addr, user_id, action)
                DO UPDATE SET count = access_link_use.count + 1
                """,
                self.id,
                remote_addr,
                user_id,
                action,
            ),
            SQL(
                "UPDATE access_link SET use_count = COALESCE(use_count, 0) + 1, "
                "last_used_at = now() AT TIME ZONE 'UTC' WHERE id = %s",
                self.id,
            ),
        ]
        if self.env.cr.readonly:
            _debug.logic("link.use_not_recorded", link=self.id, reason="readonly")
            return
        for statement in statements:
            self.env.cr.execute(statement)
        self.invalidate_recordset(["use_count", "last_used_at"])


    def _check_may_manage(self) -> None:
        self.check_access("write")

    def action_revoke(self, reason: str | None = None) -> bool:
        self._check_may_manage()
        live = self.with_privilege(
            "base.privilege_manage_links", reason=reason or "revoke a link"
        ).filtered(lambda link: not link.revoked_at)
        if not live:
            return True
        live.write(
            {
                "revoked_at": fields.Datetime.now(),
                "revoked_by_id": self.env.uid,
                "revoke_reason": reason or False,
            }
        )
        live._log("link_revoked", reason=reason)
        _debug.lifecycle("link.revoked", links=live.ids, reason=reason)
        return True

    def action_extend(self, date_to: datetime | str) -> None:
        self._check_may_manage()
        date_to = fields.Datetime.to_datetime(date_to)
        if not date_to or date_to <= fields.Datetime.now():
            raise UserError(self.env._("A link is extended to a date to come."))
        self._check_lifetime(date_to)
        live = self.with_privilege(
            "base.privilege_manage_links", reason="extend a link"
        ).filtered(lambda link: not link.revoked_at)
        live.write({"date_to": date_to})
        live._log("link_extended", reason=fields.Datetime.to_string(date_to))

    @api.model
    def _record_links(
        self, records: models.BaseModel, domain: Domain | None = None
    ) -> Self:
        if not self._runs_the_machinery():
            records = records._filtered_access("read")
        return self.with_privilege(
            "base.privilege_resolve_links", reason="list a record's links"
        ).search(
            Domain("res_model", "=", records._name)
            & Domain("res_id", "in", records.ids)
            & self._live_domain()
            & (domain or Domain.TRUE)
        )

    @api.model
    def _revoke_record_links(
        self, records: models.BaseModel, reason: str, domain: Domain | None = None
    ) -> None:
        if not self._runs_the_machinery():
            records.check_access("write")
        links = self.with_privilege(
            "base.privilege_manage_links", reason=reason
        ).search(
            Domain("res_model", "=", records._name)
            & Domain("res_id", "in", records.ids)
            & Domain("revoked_at", "=", False)
            & (domain or Domain.TRUE)
        )
        links.action_revoke(reason)

    @api.model
    def _update_record_links(
        self,
        records: models.BaseModel,
        vals: ValuesType,
        domain: Domain | None = None,
    ) -> None:
        if set(vals) - {"role", "date_to"}:
            raise UserError(
                self.env._("A link's role and expiry change; nothing else.")
            )
        if not self._runs_the_machinery():
            records.check_access("write")
        links = self.with_privilege(
            "base.privilege_manage_links", reason="update a record's links"
        ).search(
            Domain("res_model", "=", records._name)
            & Domain("res_id", "in", records.ids)
            & self._live_domain()
            & (domain or Domain.TRUE)
        )
        links.write(vals)
        if "date_to" in vals:
            links._log(
                "link_extended", reason=fields.Datetime.to_string(vals["date_to"])
            )

    def _log(self, event: str, reason: str | None = None) -> None:
        self.env["ir.access.log"]._record(
            [
                {
                    "event": event,
                    "model_name": link.res_model,
                    "res_ids": str(link.res_id),
                    "cause": link.cause,
                    "reason": reason or False,
                    "link_id": link.id,
                }
                for link in self
            ]
        )


    def _runs_the_machinery(self) -> bool:
        if self.env.su:
            return True
        manage = self.env.registry.access_policy.privilege_ids(self.env, (MANAGE,))
        return bool(manage) and manage <= self.env.privileges

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if not self._runs_the_machinery() and any(
            SERVER_FIELDS & vals.keys() for vals in vals_list
        ):
            raise AccessError(
                self.env._(
                    "Links are issued by the record they open, not created by hand."
                )
            )
        return super().create(vals_list)

    def write(self, vals: ValuesType) -> bool:
        by_hand = not self._runs_the_machinery()
        if by_hand and SERVER_FIELDS & vals.keys():
            raise AccessError(
                self.env._("Revoke or extend a link; its token and record are fixed.")
            )
        if by_hand and "date_to" in vals:
            self._check_lifetime(vals["date_to"])
        result = super().write(vals)
        if by_hand and "date_to" in vals:
            self._log(
                "link_extended",
                reason=fields.Datetime.to_string(vals["date_to"]) or "no expiry",
            )
        return result

    def _check_lifetime(self, date_to: Any) -> None:
        if self.env.user._is_system():
            return
        date_to = fields.Datetime.to_datetime(date_to)
        now = fields.Datetime.now()
        for link in self:
            if not date_to and link.date_to:
                raise UserError(
                    self.env._("Only an administrator removes a link's expiry.")
                )
            limit = now + DEFAULT_LIFETIME[link.cause]
            if date_to and date_to > limit:
                raise UserError(
                    self.env._(
                        "This link can be extended to %(limit)s at most; ask an "
                        "administrator for longer.",
                        limit=fields.Datetime.to_string(limit),
                    )
                )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_by_the_superuser(self) -> None:
        if not self.env.su:
            raise UserError(self.env._("A link is revoked, never deleted."))


class AccessLinkUse(models.Model):
    _name = "access.link.use"
    _description = "External Link Use"
    _order = "bucket desc, id desc"
    _log_access = False
    _allow_sudo_commands = False

    link_id = fields.Many2one(
        comodel_name="access.link",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    bucket = fields.Datetime(
        string="Hour",
        readonly=True,
        required=True,
    )
    remote_addr = fields.Char(
        string="Address",
        readonly=True,
        required=True,
    )
    user_id = fields.Integer(
        readonly=True,
        required=True,
        help="The signed-in user who used the link, 0 for an anonymous visitor.",
    )
    action = fields.Selection(
        selection=LINK_ACTIONS,
        readonly=True,
        required=True,
    )
    count = fields.Integer(
        readonly=True,
        required=True,
    )

    _use_unique = models.Constraint(
        "UNIQUE (link_id, bucket, remote_addr, user_id, action)",
        "One row per link, hour, address, user and action.",
    )
