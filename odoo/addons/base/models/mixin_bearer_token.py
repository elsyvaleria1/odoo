import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from odoo import api, fields, models, tools
from odoo.api import ValuesType
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)

CIPHER_SCOPE = tools.register_signed_scope(
    "mixin.bearer.token",
    purpose="derive the Fernet key that seals a model's bearer tokens at rest",
    lifetime="undated: a key, not a token; it changes with database.secret",
)


def hash_bearer_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class MixinBearerToken(models.AbstractModel):
    _name = "mixin.bearer.token"
    _description = "Bearer Token Kept Sealed"

    access_token = fields.Char(
        string="Security Token",
        compute="_compute_bearer_token",
        inverse="_inverse_bearer_token",
        search="_search_bearer_token",
    )
    access_token_hash = fields.Char(
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    access_token_sealed = fields.Char(
        copy=False,
        readonly=True,
    )

    def _bearer_cipher(self) -> Fernet:
        digest = tools.hmac(self.env(su=True), CIPHER_SCOPE, self._name)
        return Fernet(base64.urlsafe_b64encode(bytes.fromhex(digest)))

    @api.depends("access_token_hash", "access_token_sealed")
    def _compute_bearer_token(self) -> None:
        cipher = None
        for record in self:
            token = False
            if record.access_token_sealed:
                cipher = cipher or self._bearer_cipher()
                try:
                    token = cipher.decrypt(record.access_token_sealed.encode()).decode()
                except InvalidToken:
                    _debug.logic(
                        "bearer_token_unopenable", model=self._name, id=record.id
                    )
                if token and not tools.consteq(
                    hash_bearer_token(token), record.access_token_hash or ""
                ):
                    token = False
            record.access_token = token

    def _prepare_create_values(self, vals_list: list[ValuesType]) -> list[ValuesType]:
        vals_list = super()._prepare_create_values(vals_list)
        cipher = None
        for vals in vals_list:
            token = vals.pop("access_token", None)
            if token:
                cipher = cipher or self._bearer_cipher()
                vals.update(self._bearer_token_columns(str(token), cipher))
        return vals_list

    def _bearer_token_columns(
        self, token: str | None, cipher: Fernet
    ) -> dict[str, str | None]:
        if not token:
            return {"access_token_hash": None, "access_token_sealed": None}
        return {
            "access_token_hash": hash_bearer_token(token),
            "access_token_sealed": cipher.encrypt(token.encode()).decode(),
        }

    def _inverse_bearer_token(self) -> None:
        self._store_bearer_tokens(
            {record.id: record.access_token or False for record in self}
        )

    def _store_bearer_tokens(self, tokens: dict[int, Any]) -> None:
        rows = {
            record_id: token
            for record_id, token in tokens.items()
            if isinstance(record_id, int)
        }
        if not rows:
            return
        cipher = self._bearer_cipher()
        columns_by_id = {
            record_id: self._bearer_token_columns(str(token) if token else None, cipher)
            for record_id, token in rows.items()
        }
        names = list(next(iter(columns_by_id.values())))
        self.flush_model(names)
        self.env.cr.execute(
            SQL(
                "UPDATE %s AS record SET %s FROM unnest(%s::int4[], %s) AS stored(id, %s) "
                "WHERE record.id = stored.id",
                SQL.identifier(self._table),
                SQL(", ").join(
                    SQL("%s = stored.%s", SQL.identifier(name), SQL.identifier(name))
                    for name in names
                ),
                list(columns_by_id),
                SQL(", ").join(
                    SQL(
                        "%s::varchar[]",
                        [columns[name] for columns in columns_by_id.values()],
                    )
                    for name in names
                ),
                SQL(", ").join(SQL.identifier(name) for name in names),
            )
        )
        self.browse(list(columns_by_id)).invalidate_recordset(["access_token", *names])

    def _search_bearer_token(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        values = [value] if isinstance(value, str) or value is None else list(value)
        hashes = sorted({hash_bearer_token(str(token)) for token in values if token})
        without = any(not token for token in values)

        def to_sql(model: Any, alias: str, query: Any) -> SQL:
            model.flush_model(["access_token_hash"])
            column = SQL.identifier(alias, "access_token_hash")
            if operator == "in":
                conditions = []
                if hashes:
                    conditions.append(SQL("%s = ANY(%s)", column, hashes))
                if without:
                    conditions.append(SQL("%s IS NULL", column))
                if not conditions:
                    return SQL("FALSE")
                return SQL("(%s)", SQL(" OR ").join(conditions))
            others = SQL("%s <> ALL(%s)", column, hashes) if hashes else SQL("TRUE")
            if without:
                return SQL("(%s IS NOT NULL AND %s)", column, others)
            return SQL("(%s IS NULL OR %s)", column, others)

        return Domain.custom(to_sql=to_sql)

    def _access_token_opens(self, token: str | None) -> bool:
        self.check_singleton()
        if not token or not isinstance(token, str) or not self.access_token_hash:
            return False
        return tools.consteq(hash_bearer_token(token), self.access_token_hash)
