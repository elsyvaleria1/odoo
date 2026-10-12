import ast
import logging
from collections import defaultdict
from itertools import batched

from odoo import api, fields, models, modules
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)

RECYCLE_BATCH_AUTOMATIC = 5000
RECYCLE_BATCH_MANUAL = 50000


class Data_RecycleModel(models.Model):
    _name = "data_recycle.model"
    _inherit = ["mixin.data.cleaning.notification"]
    _description = "Recycling Model"
    _order = "name"

    _cleaning_mode_field = "recycle_mode"

    active = fields.Boolean(default=True)
    name = fields.Char(
        compute="_compute_name",
        store=True,
        copy=True,
        readonly=False,
        required=True,
    )

    res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Model",
        required=True,
        ondelete="cascade",
    )
    res_model_name = fields.Char(
        related="res_model_id.model",
        string="Model Name",
    )
    recycle_record_ids = fields.One2many(
        comodel_name="data_recycle.record",
        inverse_name="recycle_model_id",
    )
    records_to_recycle_count = fields.Integer(
        string="Records To Recycle",
        compute="_compute_records_to_recycle_count",
    )

    recycle_mode = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("automatic", "Automatic"),
        ],
        default="manual",
        required=True,
    )
    recycle_action = fields.Selection(
        selection=[
            ("archive", "Archive"),
            ("unlink", "Delete"),
        ],
        default="unlink",
        required=True,
    )

    domain = fields.Char(
        string="Filter",
        compute="_compute_domain",
        store=True,
        readonly=False,
    )
    include_archived = fields.Boolean(
        help="Propose archived records for deletion as well. Ignored when the action is Archive, "
        "where an already archived record has nothing left to recycle."
    )

    @api.constrains("recycle_action", "res_model_id")
    def _check_recycle_action(self) -> None:
        for recycle_model in self:
            model = recycle_model._get_model_target()
            if (
                recycle_model.recycle_action == "archive"
                and model is not None
                and not model._active_name
            ):
                raise ValidationError(
                    self.env._(
                        "%(model)s does not manage archived records. Only deletion is possible.",
                        model=recycle_model.res_model_id.display_name,
                    )
                )

    @api.constrains("domain", "res_model_id")
    def _check_domain(self) -> None:
        for recycle_model in self:
            model = recycle_model._get_model_target()
            if model is None:
                continue
            try:
                recycle_model._get_domain_candidates().check(model)
            except (ValueError, SyntaxError, TypeError) as error:
                raise ValidationError(
                    self.env._(
                        "The filter of rule %(rule)s is not a valid domain for %(model)s: %(error)s",
                        rule=recycle_model.display_name,
                        model=recycle_model.res_model_id.display_name,
                        error=error,
                    )
                ) from error

    @api.depends("res_model_id")
    def _compute_domain(self) -> None:
        for recycle_model in self:
            if recycle_model.domain:
                continue
            recycle_model.domain = "[]"

    @api.depends("res_model_id")
    def _compute_name(self):
        for recycle_model in self:
            if recycle_model.name:
                continue
            recycle_model.name = (
                recycle_model.res_model_id.name if recycle_model.res_model_id else ""
            )

    @api.depends("recycle_record_ids")
    def _compute_records_to_recycle_count(self) -> None:
        count_data = self.env["data_recycle.record"]._read_group(
            [("recycle_model_id", "in", self.ids)], ["recycle_model_id"], ["__count"]
        )
        counts = {recycle_model.id: count for recycle_model, count in count_data}
        for recycle_model in self:
            recycle_model.records_to_recycle_count = counts.get(recycle_model.id, 0)

    def _get_model_target(self):
        self.check_singleton()
        name = self.res_model_name
        return self.env[name] if name and name in self.env else None

    def _get_domain_candidates(self):
        self.check_singleton()
        return Domain(ast.literal_eval(self.domain or "[]"))

    def _cron_recycle_records(self) -> None:
        recycle_models = self.sudo().search([])
        for recycle_model in recycle_models:
            try:
                recycle_model._recycle_records(batch_commits=True)
            except UserError as error:
                _logger.warning(
                    "Data recycle: rule %r (id=%s) skipped: %s",
                    recycle_model.name,
                    recycle_model.id,
                    error,
                )
            except Exception:
                if not modules.module.current_test:
                    self.env.cr.rollback()
                _logger.exception(
                    "Data recycle: rule %r (id=%s) failed, the other rules still run",
                    recycle_model.name,
                    recycle_model.id,
                )
        recycle_models._notify_pending_records()

    def _recycle_records(self, batch_commits=False) -> None:
        commit = batch_commits and not modules.module.current_test
        Record = self.env["data_recycle.record"]
        queued_per_model = defaultdict(dict)
        for queued in Record.with_context(active_test=False).search_fetch(
            [("recycle_model_id", "in", self.ids)], ["res_id", "recycle_model_id"]
        ):
            queued_per_model[queued.recycle_model_id.id][queued.res_id] = queued.id

        for recycle_model in self:
            model = recycle_model._get_model_target()
            if model is None:
                raise UserError(
                    self.env._(
                        "Rule %(rule)s targets %(model)s, which is not installed.",
                        rule=recycle_model.display_name,
                        model=recycle_model.res_model_id.display_name,
                    )
                )
            domain = recycle_model._get_domain_candidates()
            if domain.is_true():
                raise UserError(
                    self.env._(
                        "Rule %(rule)s selects every %(model)s record: its filter matches "
                        "everything. Narrow it down -- an age condition is written as "
                        "('date', '<=', 'today -1y') -- or, if every record really is the "
                        "target, say so explicitly with a filter such as [('id', '>', 0)].",
                        rule=recycle_model.display_name,
                        model=recycle_model.res_model_id.display_name,
                    )
                )
            if (
                recycle_model.include_archived
                and recycle_model.recycle_action == "unlink"
            ):
                model = model.with_context(active_test=False)

            queued_res_ids = queued_per_model[recycle_model.id]
            candidate_ids = model.search(domain).ids
            candidate_res_ids = set(candidate_ids)

            stale_ids = [
                rec_id
                for res_id, rec_id in queued_res_ids.items()
                if res_id not in candidate_res_ids
            ]
            Record.browse(stale_ids).unlink()
            if commit and stale_ids:
                self.env["ir.cron"]._commit_progress()

            new_res_ids = [
                res_id for res_id in candidate_ids if res_id not in queued_res_ids
            ]
            is_automatic = recycle_model.recycle_mode == "automatic"
            batch_size = (
                RECYCLE_BATCH_AUTOMATIC if is_automatic else RECYCLE_BATCH_MANUAL
            )
            for res_id_batch in batched(new_res_ids, batch_size, strict=False):
                records = Record.create(
                    [
                        {"res_id": res_id, "recycle_model_id": recycle_model.id}
                        for res_id in res_id_batch
                    ]
                )
                if is_automatic:
                    records.action_validate()
                if commit:
                    self.env["ir.cron"]._commit_progress()

    def _get_count_pending(self):
        self.check_singleton()
        return self.env["data_recycle.record"].search_count(
            [
                ("recycle_model_id", "=", self.id),
            ]
        )

    def _get_notification_body(self, records_count):
        self.check_singleton()
        return self.env["ir.qweb"]._render(
            "data_recycle.notification",
            {
                "records_count": records_count,
                "res_model_label": self.res_model_id.name,
                "recycle_model_id": self.id,
                "menu_id": self.env.ref("data_recycle.menu_data_cleaning_root").id,
            },
        )

    def _get_notification_subject(self):
        return self.env._("Data to Recycle")

    def write(self, vals):
        stale = self.env["data_recycle.model"]
        if "active" in vals and not vals["active"]:
            stale = self
        elif "res_model_id" in vals:
            stale = self.filtered(lambda m: m.res_model_id.id != vals["res_model_id"])
        if stale:
            self.env["data_recycle.record"].with_context(active_test=False).search(
                [
                    ("recycle_model_id", "in", stale.ids),
                ]
            ).unlink()
        return super().write(vals)

    def open_records(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "data_recycle.action_data_recycle_record"
        )
        action["context"] = dict(
            self.env["ir.actions.actions"]._eval_action_context(action.get("context")),
            searchpanel_default_recycle_model_id=self.id,
        )
        return action

    def action_recycle_records(self):
        self.check_singleton()
        self.sudo()._recycle_records()
        if self.recycle_mode == "manual":
            return self.open_records()
        return None
