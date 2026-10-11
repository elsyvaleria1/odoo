import logging
from collections import defaultdict
from itertools import batched

from odoo import api, fields, models
from odoo.db.errors import PG_USER_FAULT_EXCEPTIONS
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

VALIDATE_BATCH = 1000

RECYCLE_REFUSALS = (UserError, ValidationError, *PG_USER_FAULT_EXCEPTIONS)

RECYCLE_METHODS = {"archive": "action_archive", "unlink": "unlink"}


class Data_RecycleRecord(models.Model):
    _name = "data_recycle.record"
    _description = "Recycling Record"

    active = fields.Boolean(default=True)
    name = fields.Char(
        string="Record Name",
        compute="_compute_name",
        compute_sudo=True,
    )
    recycle_model_id = fields.Many2one(
        comodel_name="data_recycle.model",
        index="btree_not_null",
        ondelete="cascade",
    )

    res_id = fields.Integer(
        string="Record ID",
        index=True,
    )
    res_model_id = fields.Many2one(
        related="recycle_model_id.res_model_id",
    )
    res_model_name = fields.Char(
        related="recycle_model_id.res_model_name",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        compute="_compute_company_id",
        store=True,
    )

    @api.model
    def _get_company_id(self, record):
        company_field = record._fields.get("company_id")
        if company_field is not None and company_field.comodel_name == "res.company":
            return record.company_id
        return self.env["res.company"]

    @api.depends("res_id", "res_model_name")
    def _compute_name(self):
        original_records = self._original_records()
        for record in self:
            original_record = original_records.get(
                (record.res_model_name, record.res_id)
            )
            if original_record:
                record.name = original_record.display_name or self.env._(
                    "Undefined Name"
                )
            else:
                record.name = self.env._("**Record Deleted**")

    @api.depends("res_id", "res_model_name")
    def _compute_company_id(self):
        original_records = self._original_records()
        for record in self:
            original_record = original_records.get(
                (record.res_model_name, record.res_id)
            )
            record.company_id = (
                self._get_company_id(original_record) if original_record else False
            )

    def _original_records(self):
        res_ids_per_model = defaultdict(list)
        for record in self:
            if record.res_model_name:
                res_ids_per_model[record.res_model_name].append(record.res_id)

        original_records = {}
        for model_name, res_ids in res_ids_per_model.items():
            if model_name not in self.env:
                continue
            records = (
                self.env[model_name]
                .with_context(active_test=False)
                .sudo()
                .browse(res_ids)
            )
            for original_record in records.exists():
                original_records[model_name, original_record.id] = original_record
        return original_records

    def action_validate(self):
        original_records = self._original_records()
        res_ids_per_action = defaultdict(list)
        for record in self:
            key = (record.res_model_name, record.res_id)
            if key in original_records:
                res_ids_per_action[
                    record.recycle_model_id.recycle_action, record.res_model_name
                ].append(record.res_id)

        refused = set()
        for (recycle_action, model_name), res_ids in res_ids_per_action.items():
            refused |= {
                (model_name, res_id)
                for res_id in self._recycle_originals(
                    model_name, res_ids, recycle_action
                )
            }

        self.filtered(lambda r: (r.res_model_name, r.res_id) not in refused).unlink()

    def _recycle_originals(self, model_name, res_ids, recycle_action):
        model = self.env[model_name].sudo()
        method = RECYCLE_METHODS[recycle_action]
        refused = set()
        for res_id_batch in batched(res_ids, VALIDATE_BATCH, strict=False):
            try:
                with self.env.cr.savepoint():
                    getattr(model.browse(res_id_batch), method)()
                continue
            except RECYCLE_REFUSALS:
                _logger.info(
                    "Data recycle: a batch of %d %s refused to be recycled, retrying one by one",
                    len(res_id_batch),
                    model_name,
                )
            for res_id in res_id_batch:
                try:
                    with self.env.cr.savepoint():
                        getattr(model.browse(res_id), method)()
                except RECYCLE_REFUSALS as error:
                    refused.add(res_id)
                    _logger.warning(
                        "Data recycle: %s(%s) cannot be recycled: %s",
                        model_name,
                        res_id,
                        error,
                    )
        return refused

    def action_discard(self) -> None:
        self.write({"active": False})
