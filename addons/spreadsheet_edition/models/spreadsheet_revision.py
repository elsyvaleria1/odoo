from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SpreadsheetRevision(models.Model):
    _name = "spreadsheet.revision"
    _description = "Collaborative spreadsheet revision"
    _rec_name = "revision_uuid"
    _rec_names_search = ["name", "revision_uuid"]

    name = fields.Char(string="Revision name")
    active = fields.Boolean(default=True)
    res_model = fields.Char(
        string="Model",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Record id",
        required=True,
    )
    commands = fields.Char(required=True)
    revision_uuid = fields.Char(
        index=True,
        required=True,
    )
    parent_revision_id = fields.Many2one(
        comodel_name="spreadsheet.revision",
        copy=False,
    )
    author_id = fields.Many2one(
        comodel_name="res.users",
        default=lambda self: self.env.user,
        required=True,
    )
    revision_date = fields.Datetime(
        default=fields.Datetime.now,
        required=True,
    )

    _initial_unique = models.UniqueIndex(
        "(res_model, res_id) WHERE parent_revision_id IS NULL",
        "There can be only one initial revision per spreadsheet",
    )
    _parent_unique = models.UniqueIndex(
        "(parent_revision_id, res_model, res_id) WHERE parent_revision_id IS NOT NULL",
        "A revision based on the same revision already exists",
    )
    _res_model_res_id_idx = models.Index("(res_model, res_id)")

    @api.depends("name", "revision_uuid")
    def _compute_display_name(self):
        for revision in self:
            revision.display_name = revision.name or revision.revision_uuid

    @api.autovacuum
    def _gc_revisions(self, domain=(), inactivity_days=365) -> None:
        config_param = self.env.registry.settings.get(
            self.env, "spreadsheet_edition.gc_revisions_inactivity_in_days", ""
        )
        if config_param:
            inactivity_days = int(config_param)
        one_year_ago = fields.Datetime.now() - relativedelta(days=inactivity_days)
        inactive_spreadsheets = self.with_context(active_test=False)._read_group(
            domain=domain,
            groupby=["res_model", "res_id"],
            aggregates=["write_date:max"],
            having=[("write_date:max", "<=", one_year_ago)],
        )
        ids_by_model = defaultdict(list)
        for res_model, res_id, _last_revision_date in inactive_spreadsheets:
            ids_by_model[res_model].append(res_id)
        _debug.pipeline(
            "spreadsheet_revisions_gc_selected",
            inactivity_days=inactivity_days,
            spreadsheets=len(inactive_spreadsheets),
            models=len(ids_by_model),
        )
        for res_model, res_ids in ids_by_model.items():
            _debug.logic(
                "spreadsheet_revisions_gc_model",
                model=res_model,
                spreadsheets=len(res_ids),
                known=res_model in self.env,
            )
            if res_model in self.env:
                records = (
                    self.env[res_model]
                    .browse(res_ids)
                    .with_context(preserve_spreadsheet_revisions=True)
                )
                for record in records.filtered("spreadsheet_snapshot"):
                    record.spreadsheet_binary_data = record.spreadsheet_snapshot
            stale_revisions = self.search(
                [
                    ("res_model", "=", res_model),
                    ("res_id", "in", res_ids),
                    ("active", "=", False),
                ]
            )
            _debug.pipeline(
                "spreadsheet_revisions_gc_unlinked",
                model=res_model,
                spreadsheets=len(res_ids),
                revisions=len(stale_revisions),
            )
            stale_revisions.unlink()
