import logging
from itertools import batched

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.models import MAGIC_COLUMNS

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

IGNORED_FIELDS = MAGIC_COLUMNS
DM_CRON_BATCH_SIZE = 100


class Data_MergeGroup(models.Model):
    _name = "data_merge.group"
    _description = "Deduplication Group"
    _order = "similarity desc"

    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        comodel_name="data_merge.model",
        string="Deduplication Model",
        index=True,
        required=True,
        ondelete="cascade",
    )
    res_model_id = fields.Many2one(
        related="model_id.res_model_id",
        readonly=True,
    )
    res_model_name = fields.Char(
        related="model_id.res_model_name",
        readonly=True,
    )
    similarity = fields.Float(
        string="Similarity %",
        compute="_compute_similarity",
        store=True,
        readonly=True,
        help="Similarity coefficient based on the amount of text fields exactly in common.",
    )
    divergent_fields = fields.Char(
        compute="_compute_similarity",
        store=True,
    )
    record_ids = fields.One2many(
        comodel_name="data_merge.record",
        inverse_name="group_id",
    )

    @api.depends("model_id", "similarity")
    def _compute_display_name(self):
        for group in self:
            group.display_name = self.env._(
                "%(model)s - Similarity: %(similarity)s%%",
                model=group.model_id.name,
                similarity=int(group.similarity * 100),
            )

    def _get_fields_similarity(self) -> list:
        self.check_singleton()
        group_fields = self.env[self.res_model_name]._fields.items()
        return [name for name, field in group_fields if field.type == "char"]

    @api.depends("record_ids")
    def _compute_similarity(self) -> None:
        for group in self:
            if not group.record_ids:
                group.divergent_fields = ""
                group.similarity = 1
                continue

            read_fields = group._get_fields_similarity()

            record_ids = group.record_ids.mapped("res_id")
            records = (
                self.env[group.res_model_name].browse(record_ids).read(read_fields)
            )
            data = set(records[0].items())
            data = data.intersection(*[set(record.items()) for record in records[1:]])

            diff_fields = set(read_fields) - {
                k for k, v in data
            }
            group.divergent_fields = ",".join(diff_fields)
            group.similarity = min(1, len(data) / len(read_fields))

    def discard_records(self, records=None):
        domain = Domain("group_id", "=", self.id)

        if records is not None:
            domain &= Domain("id", "in", records)
        self.env["data_merge.record"].search(domain).write(
            {"is_discarded": True, "is_master": False}
        )
        if all(not record.active for record in self.record_ids):
            self.active = False
        self._elect_master_record()


    def _elect_master_record(self) -> None:
        for group in self:
            if hasattr(self.env[group.res_model_name], "_elect_method"):
                elect_master = self.env[group.res_model_name]._elect_method
            else:
                elect_master = group._elect_method

            records = group.record_ids._original_records()
            if not records:
                return

            master = elect_master(records)
            if master:
                master_record = group.record_ids.filtered_domain(
                    [("res_id", "=", master.id)]
                )
                master_record.is_master = True

    def _elect_method(self, records):
        records_sorted = records.sorted(lambda record: (record.create_date, record.id))
        _debug.logic(
            "master_elected",
            model=records._name,
            given=records.ids,
            elected=records_sorted[:1].id,
        )
        return records_sorted[0] if records_sorted else None


    @api.model
    def merge_multiple_records(self, group_records) -> None:
        group_ids = self.browse([int(group_id) for group_id in group_records])

        for group in group_ids:
            group.merge_records(group_records[str(group.id)])

    def merge_records(self, records=None) -> dict | None:
        self.check_singleton()
        if records is None:
            records = []

        domain = [("group_id", "=", self.id)]
        if records:
            domain += [("id", "in", records)]

        to_merge = (
            self.env["data_merge.record"]
            .with_context(active_test=False)
            .search(domain, order="id")
        )
        to_merge_count = len(to_merge)
        if to_merge_count <= 1:
            return None
        master_record = to_merge.filtered("is_master") or to_merge[0]
        to_merge -= master_record

        if not master_record._original_records():
            _logger.warning("The master record does not exist")
            return None

        _logger.info(
            "Merging %s records %s into %s",
            self.res_model_name,
            to_merge.mapped("res_id"),
            master_record.res_id,
        )

        model = self.env[self.res_model_name]
        if hasattr(model, "_merge_method"):
            merge = model._merge_method
        else:
            merge = self._merge_method

        chatter_data = {
            rec.res_id: {
                "res_id": rec.res_id,
                "merged_record": str(rec.name),
                "changes": rec._record_snapshot(),
            }
            for rec in to_merge
        }
        res = merge(master_record._original_records(), to_merge._original_records())
        if res.get("log_chatter"):
            self._log_merge(master_record, to_merge, chatter_data)

        if res.get("post_merge"):
            self._post_merge(master_record, to_merge)

        is_merge_action = master_record.model_id.is_contextual_merge_action
        (master_record + to_merge).unlink()

        return {
            "records_merged": res["records_merged"]
            if res.get("records_merged")
            else to_merge_count,
            "back_to_model": is_merge_action,
        }

    def _log_merge(self, master_record, merged_records, chatter_data) -> None:
        if not isinstance(
            self.env[self.res_model_name], self.env.registry["mixin.mail.thread"]
        ):
            return

        values = {
            "res_model_label": self.res_model_id.name,
            "res_model_name": self.res_model_name,
            "res_id": master_record.res_id,
            "master_record": master_record.name,
        }
        for rec in merged_records:
            master_values = chatter_data.get(rec.res_id, {})
            master_values.update(
                {
                    "res_model_label": self.res_model_id.name,
                    "res_model_name": self.res_model_name,
                    "archived": rec._original_records().exists(),
                }
            )
            if self.model_id.removal_mode == "archive":
                rec._original_records()._message_log_with_view(
                    "data_cleaning.data_merge_merged", render_values=values
                )
            master_record._original_records()._message_log_with_view(
                "data_cleaning.data_merge_main", render_values=master_values
            )

    def _merge_method(self, master, records) -> dict:
        self.env["data_merge.record"]._update_foreign_keys(
            destination=master, source=records
        )

        return {
            "post_merge": True,
            "log_chatter": True,
        }

    def _post_merge(self, master, records) -> None:
        origins = records._original_records()
        if self.model_id.removal_mode == "delete" or not origins._active_name:
            origins.unlink()
        else:
            origins.write({origins._active_name: False})


    def _cron_cleanup(self, auto_commit=True) -> None:
        groups = self.with_context(active_test=False).env["data_merge.group"].search([])

        for batched_groups in (
            self.with_context(active_test=False).browse(b)
            for b in batched(groups.ids, DM_CRON_BATCH_SIZE, strict=False)
        ):
            batched_groups._cleanup()

            if auto_commit:
                self.env["ir.cron"]._commit_progress(processed=len(batched_groups))

    def _cleanup(self) -> None:
        records_to_delete = self.env["data_merge.record"]
        groups_to_delete = self.env["data_merge.group"]

        for group in self:
            records_discarded = False
            records_kept = 0

            original_records = (
                {r.id: r for r in group.record_ids._original_records()}
                if group.record_ids
                else {}
            )
            if not original_records:
                groups_to_delete += group
                continue

            for rec in group.record_ids:
                original_record = original_records.get(rec.res_id)
                if not original_record:
                    records_to_delete += rec
                    continue

                origin_inactive = (
                    original_record._active_name
                    and not original_record[original_record._active_name]
                )
                if origin_inactive:
                    records_to_delete += rec
                    continue

                records_discarded = records_discarded or rec.is_discarded
                if not rec.is_discarded:
                    records_kept += 1

            if not records_discarded and records_kept <= 1:
                groups_to_delete += group

            if records_discarded and records_kept == 1:
                records_to_delete += group.record_ids.filtered(
                    lambda r: not r.is_discarded
                )

        records_to_delete.unlink()
        groups_to_delete.unlink()
