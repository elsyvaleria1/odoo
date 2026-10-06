from typing import Self

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinPosLoad(models.AbstractModel):
    _name = "mixin.pos.load"
    _description = "PoS data loading mixin"

    _pos_data_incremental = False
    _pos_data_incremental_fields = ("write_date",)

    @api.model
    def _load_pos_data_search_read(self, data, config):
        if not config:
            raise ValueError("config must be provided to search for PoS data.")

        domain = self._add_server_date_to_domain(
            self._load_pos_data_domain(data, config)
        )
        if domain is False:
            _debug.logic("load_domain_false", model=self._name)
            return []

        records = self.search(domain)
        _debug.pipeline("load_search", model=self._name, domain=domain, records=records)
        return self._load_pos_data_read(records, config)

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []

    @api.model
    def _get_referenced_ids(self, data, model, field_name) -> set:
        return {
            record[field_name]
            for record in data.get(model, [])
            if record.get(field_name)
        }

    @api.model
    def _add_server_date_to_domain(self, domain):
        if domain is False:
            return domain

        last_server_date = self.env.context.get("pos_last_server_date", False)
        limited_loading = self.env.context.get("pos_limited_loading", True)
        model_included = self._pos_data_incremental

        if limited_loading and last_server_date and model_included:
            _debug.logic(
                "load_incremental",
                model=self._name,
                fields=self._pos_data_incremental_fields,
                since=last_server_date,
            )
            changes = Domain.OR(
                [
                    [(field, ">", last_server_date)]
                    for field in self._pos_data_incremental_fields
                ]
            )
            domain = Domain.AND([domain, changes])

        return domain

    def _with_pos_company(self, config) -> Self:
        company_id = config.company_id.id
        if not company_id:
            return self
        allowed = self.env.companies.ids
        if allowed[:1] == [company_id]:
            return self
        _debug.logic(
            "load_company_promoted",
            model=self._name,
            company=company_id,
            allowed=allowed,
        )
        return self.with_context(
            allowed_company_ids=[company_id]
            + [other for other in allowed if other != company_id]
        )

    @api.model
    def _load_pos_data_projected_fields(self) -> dict:
        return {}

    @api.model
    def _load_pos_data_read(self, records, config):
        if not config:
            raise ValueError("config must be provided to read PoS data.")
        config.check_singleton()

        fields = self._load_pos_data_fields(config)
        with _debug.perf(
            "load_read",
            cr=self.env.cr,
            model=self._name,
            fields=len(fields),
            records=records,
        ):
            records = records._filtered_access("read").read(fields, load=False)
        return records or []

    def _get_inactive_ids(self, config):
        if "active" not in self._fields:
            return []
        try:
            return (self - self.filtered("active")).ids
        except AccessError:
            _debug.logic("load_active_access_error", model=self._name, records=self)
            return self.ids

    @api.model
    def _load_pos_data_fields(self, config):
        return []
