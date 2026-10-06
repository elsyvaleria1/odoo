from collections import defaultdict
from typing import Any

from odoo import api, models
from odoo.fields import Domain
from odoo.models import ValuesType

from .utils import changed_vals


class MixinResourceLedger(models.AbstractModel):
    _name = "mixin.resource.ledger"
    _description = "Resource Ledger Mixin"

    @api.model
    def _get_fields_projection_key(self) -> tuple[str, ...]:
        return ("resource_id",)

    @api.model
    def _get_domain_projection(self, record: models.BaseModel) -> Domain:
        return Domain(
            [("res_model", "=", record._name), ("res_id", "=", record.id)],
        )

    def _get_projection_key(self, vals: ValuesType | None = None) -> tuple[Any, ...]:
        if vals is None:
            return tuple(
                self._fields[fname].convert_to_write(self[fname], self)
                for fname in self._get_fields_projection_key()
            )
        return tuple(
            vals.get(fname) or False for fname in self._get_fields_projection_key()
        )

    @api.model
    def _prepare_projection_link_vals(self, record: models.BaseModel) -> ValuesType:
        return {"res_model": record._name, "res_id": record.id}

    @api.model
    def _sync_projection_batch(self, entries) -> models.BaseModel:
        """Reconcile the rows of several records at once.

        `entries` holds (record, vals_list, existing-or-None). A row already
        equal to a wanted value is kept untouched; the rest are deleted, then
        rewritten, then created, so no intermediate state holds both an
        outgoing and an incoming claim at the same time.
        """
        entries = [
            (record, vals_list, existing)
            for record, vals_list, existing in entries
            if record.id and isinstance(record.id, int)
        ]
        links = [self._prepare_projection_link_vals(record) for record, *_ in entries]
        missing = [record for record, _vals, existing in entries if existing is None]
        found_by_link = defaultdict(self.browse)
        if missing:
            found = (
                self.sudo()
                .with_context(active_test=False)
                .search(Domain.OR(self._get_domain_projection(r) for r in missing))
            )
            link_fields = {tuple(sorted(link)) for link in links}
            for row in found:
                for fnames in link_fields:
                    key = tuple(
                        (fname, row._fields[fname].convert_to_write(row[fname], row))
                        for fname in fnames
                    )
                    found_by_link[key] |= row
        kept = to_delete = self.browse()
        writes, to_create = [], []
        for (_record, vals_list, existing), link_vals in zip(
            entries, links, strict=True
        ):
            if existing is None:
                existing = found_by_link[tuple(sorted(link_vals.items()))]
            wanted = []
            for vals in vals_list:
                base_vals = {**vals, **link_vals}
                if "active" in self._fields:
                    base_vals.setdefault("active", True)
                wanted.append(base_vals)
            buckets = defaultdict(list)
            for row in existing:
                buckets[row._get_projection_key()].append(row)
            unmatched = []
            for base_vals in wanted:
                bucket = buckets.get(self._get_projection_key(base_vals), [])
                same = next(
                    (row for row in bucket if not row._get_changed_vals(base_vals)),
                    None,
                )
                if same:
                    bucket.remove(same)
                    kept |= same
                else:
                    unmatched.append(base_vals)
            for base_vals in unmatched:
                bucket = buckets.get(self._get_projection_key(base_vals))
                if bucket:
                    row = bucket.pop(0)
                    writes.append((row, row._get_changed_vals(base_vals)))
                    kept |= row
                else:
                    to_create.append(base_vals)
            for bucket in buckets.values():
                for row in bucket:
                    to_delete |= row
        if to_delete:
            to_delete.sudo().unlink()
        for row, changes in writes:
            row.sudo().write(changes)
        created = self.sudo().create(to_create) if to_create else self.browse()
        return kept | created

    def _get_changed_vals(self, vals: ValuesType) -> ValuesType:
        return changed_vals(self, vals)
