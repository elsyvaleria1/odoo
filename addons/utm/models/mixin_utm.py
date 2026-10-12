import itertools
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from typing import Literal, cast

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.http import request


class MixinUtm(models.AbstractModel):
    _name = "mixin.utm"
    _description = "UTM Mixin"

    campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        index="btree_not_null",
        help="This is a name that helps you keep track of your different campaign efforts, e.g. Fall_Drive, Christmas_Special",
    )
    source_id = fields.Many2one(
        comodel_name="utm.source",
        index="btree_not_null",
        help="This is the source of the link, e.g. Search Engine, another domain, or name of email list",
    )
    medium_id = fields.Many2one(
        comodel_name="utm.medium",
        index="btree_not_null",
        help="This is the method of delivery, e.g. Postcard, Email, or Banner Ad",
    )

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)

        if not self.env.is_superuser() and self.env.user.has_group(
            "sale.group_sale_salesman"
        ):
            return values

        for _url_param, field_name, cookie_name in cast(
            "MixinUtm", self.env["mixin.utm"]
        ).tracking_fields():
            if field_name in fields:
                field = self._fields[field_name]
                value = False
                if request:
                    value = request.cookies.get(cookie_name)
                if field.type == "many2one" and isinstance(value, str) and value:
                    record = self._get_or_create_record(field.comodel_name, value)
                    value = record.id
                if value:
                    values[field_name] = value
        return values

    def tracking_fields(self) -> list:
        return [
            ("utm_campaign", "campaign_id", "odoo_utm_campaign"),
            ("utm_source", "source_id", "odoo_utm_source"),
            ("utm_medium", "medium_id", "odoo_utm_medium"),
        ]

    def _tracking_models(self) -> set:
        fnames = {fname for _, fname, _ in self.tracking_fields()}
        return {
            self._fields[fname].comodel_name
            for fname in fnames
            if fname in self._fields and self._fields[fname].type == "many2one"
        }

    @api.model
    def get_or_create_record(self, model_name, name) -> dict:
        if model_name in self._tracking_models():
            record = self._get_or_create_record(model_name, name)
        else:
            record = self.env[model_name].create({self.env[model_name]._rec_name: name})
        return {"id": record.id, "name": record.display_name}

    def _get_or_create_record(self, model_name, name):
        Model = self.env[model_name]

        cleaned_name = name.strip()
        record = Model
        if cleaned_name:
            record = Model.with_context(active_test=False).search(
                [("name", "=ilike", cleaned_name)], limit=1
            )

        if not record:
            record_values = {"name": cleaned_name}
            if "is_auto_campaign" in record._fields:
                record_values["is_auto_campaign"] = True
            record = Model.create(record_values)

        return record

    @api.model
    def _get_unique_names(
        self, model_name: str, names: Sequence[str | Literal[False] | None]
    ) -> list[str | Literal[False]]:
        skip_record_ids = self.env.context.get("utm_check_skip_record_ids") or []
        names_without_counter = {
            self._split_name_and_count(name)[0] for name in names if name
        }

        existing_names: set[str] = set()
        if names_without_counter:
            search_domain = Domain.OR(
                Domain("name", "ilike", name) for name in names_without_counter
            )
            if skip_record_ids:
                search_domain &= Domain("id", "not in", skip_record_ids)
            existing_names = {
                vals["name"]
                for vals in self.env[model_name].search_read(search_domain, ["name"])
            }

        used_counters_per_name = {
            name: {
                self._split_name_and_count(existing_name)[1]
                for existing_name in existing_names
                if existing_name == name or existing_name.startswith(f"{name} [")
            }
            for name in names_without_counter
        }
        current_counter_per_name: defaultdict[str, Iterator[int]] = defaultdict(
            lambda: itertools.count(1)
        )

        result: list[str | Literal[False]] = []
        for name in names:
            if not name:
                result.append(False)
                continue

            name_without_counter, asked_counter = self._split_name_and_count(name)
            existing = used_counters_per_name.get(name_without_counter, set())
            if asked_counter and asked_counter not in existing:
                count = asked_counter
            else:
                for count in current_counter_per_name[name_without_counter]:
                    if count not in existing:
                        break
            existing.add(count)
            result.append(
                f"{name_without_counter} [{count}]"
                if count > 1
                else name_without_counter
            )

        return result

    @staticmethod
    def _split_name_and_count(
        name: str | Literal[False] | None,
    ) -> tuple[str, int]:
        name = name or ""
        name_counter_re = r"(.*)\s+\[([0-9]+)\]"
        match = re.match(name_counter_re, name)
        if match:
            return match.group(1), int(match.group(2) or "1")
        return name, 1
