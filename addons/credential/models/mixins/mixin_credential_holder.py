from uuid import uuid4

from odoo import api, models
from odoo.libs.json import dumps as json_dumps

NATIVE_CREDENTIAL_FIELDS = frozenset({"api_key", "api_secret", "username", "password"})


class MixinCredentialHolder(models.AbstractModel):
    """A record whose own secret fields are doors onto one credential.

    The concrete model declares the Many2one named by `_credential_holder_field`,
    maps each door to a vault key in `_CREDENTIAL_FIELDS`, and declares every door
    as ``fields.Char(compute="_compute_credential_doors",
    inverse="_inverse_credential_doors")``, with ``copy=True`` when a copy of the
    record should carry the secret. A key in `NATIVE_CREDENTIAL_FIELDS`
    lands in that credential field; any other key is a member of
    `credential_data`.

    Secrets written through `create` and `write` are routed out of the values
    before the ORM sees them. The ORM protects every field computed by one
    method during a write, so an inverse shared by all doors would read the
    doors not being written as empty and clear them.
    """

    _name = "mixin.credential.holder"
    _description = "Credential Holder"

    _credential_holder_field = "credential_id"
    _credential_purpose = "credential:holder"
    _CREDENTIAL_FIELDS: dict[str, str] = {}

    def _credential_field_map(self) -> dict[str, str]:
        model_class = type(self)
        mro = model_class.__mro__
        cached = vars(model_class).get("_credential_field_map_merged")
        if cached is None or cached[0] is not mro:
            mapping: dict[str, str] = {}
            for cls in reversed(mro):
                mapping.update(vars(cls).get("_CREDENTIAL_FIELDS") or {})
            cached = model_class._credential_field_map_merged = (mro, mapping)
        return cached[1]

    def _credential_holder_name(self) -> str:
        self.check_singleton()
        return f"{self.display_name or self._description} [#{self.id}]"

    def _credential_company_id(self):
        self.check_singleton()
        return self.company_id.id if "company_id" in self._fields else False

    def _pop_door_values(self, vals: dict) -> dict:
        field_map = self._credential_field_map()
        return {
            field_map[door]: self._fields[door].convert_to_cache(vals.pop(door), self)
            or False
            for door in list(vals)
            if door in field_map
        }

    @api.model_create_multi
    def create(self, vals_list):
        holder = self._credential_holder_field
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            secrets = {k: v for k, v in self._pop_door_values(vals).items() if v}
            if secrets:
                vals[holder] = self._create_holding_credential(
                    f"{self._description} [{uuid4().hex[:12]}]", False, secrets
                ).id
        records = super().create(vals_list)
        for record in records.sudo():
            if record[holder]:
                record[holder].write(
                    {
                        "name": record._credential_holder_name(),
                        "company_id": record._credential_company_id(),
                    }
                )
        return records

    def write(self, vals):
        vals = dict(vals)
        field_map = self._credential_field_map()
        written = [door for door in vals if door in field_map]
        secrets = self._pop_door_values(vals)
        if secrets:
            written_fields = [self._fields[name] for name in vals]
            with self.env.protecting(written_fields, self):
                for record in self:
                    record._set_held_secrets(secrets)
                self.invalidate_recordset(written)
                self.modified(written)
        result = super().write(vals)
        if secrets:
            self._check_fields(written)
        return result

    @api.depends(lambda self: (self._credential_holder_field,))
    def _compute_credential_doors(self) -> None:
        field_map = self._credential_field_map()
        for record in self:
            secrets = record._get_held_secrets()
            for door, key in field_map.items():
                record[door] = secrets.get(key) or False

    def _inverse_credential_doors(self):
        pass

    def _get_held_secrets(self) -> dict:
        self.check_singleton()
        credential = self.sudo()[self._credential_holder_field]
        if not credential:
            return {}
        return credential._use_secret_payload(self._credential_purpose)

    def _get_held_secret(self, key: str):
        return self._get_held_secrets().get(key) or False

    def _get_held_main_secret(self, prefer: str):
        secrets = self._get_held_secrets()
        return secrets.get(prefer) or secrets.get("credential_value") or False

    def _post_held_oauth2_refresh_grant(
        self, token_url, refresh_key, client_auth, *, purpose, **options
    ):
        self.check_singleton()
        credential = self.sudo()[self._credential_holder_field]
        if not credential:
            return None
        credential._lock_for_oauth2_refresh()
        refresh_token = credential._use_secret_payload(f"{purpose}:oauth2_refresh").get(
            refresh_key
        )
        if not refresh_token:
            return None
        return credential._post_oauth2_refresh_grant(
            token_url, refresh_token, client_auth, purpose=purpose, **options
        )

    @api.model
    def _create_holding_credential(self, name, company_id, secrets):
        native = {k: v for k, v in secrets.items() if k in NATIVE_CREDENTIAL_FIELDS}
        extra = {k: v for k, v in secrets.items() if k not in native}
        return (
            self.env["credential.credential"]
            .sudo()
            .create(
                {
                    "name": name,
                    "category_id": self.env.ref(
                        "credential.credential_category_custom"
                    ).id,
                    "company_id": company_id,
                    **native,
                    **({"credential_data": json_dumps(extra)} if extra else {}),
                }
            )
        )

    def _set_held_secrets(self, secrets: dict) -> None:
        self.check_singleton()
        credential = self.sudo()[self._credential_holder_field]
        if not credential:
            if not any(secrets.values()):
                return
            credential = self._create_holding_credential(
                self._credential_holder_name(), self._credential_company_id(), {}
            )
            super(MixinCredentialHolder, self.sudo()).write(
                {self._credential_holder_field: credential.id}
            )

        native = {
            key: value or False
            for key, value in secrets.items()
            if key in NATIVE_CREDENTIAL_FIELDS
        }
        extra = {key: value for key, value in secrets.items() if key not in native}
        if native:
            credential.write(native)
        if extra:
            data = (
                {
                    key: value
                    for key, value in credential._use_secret_payload(
                        self._credential_purpose
                    ).items()
                    if key not in credential._JSON_ACCESSOR_FIELDS
                }
                if credential.storage_method == "json"
                else {}
            )
            for key, value in extra.items():
                if value:
                    data[key] = value
                else:
                    data.pop(key, None)
            credential.credential_data = json_dumps(data)

        if not any(credential._use_secret_payload(self._credential_purpose).values()):
            super(MixinCredentialHolder, self.sudo()).write(
                {self._credential_holder_field: False}
            )
            credential.unlink()
