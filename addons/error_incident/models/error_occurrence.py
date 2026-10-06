import logging
from datetime import timedelta

from odoo import fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

from .error_incident import SOURCES

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

RETENTION_DAYS_PARAM = "error_incident.occurrence_retention_days"
KEPT_PER_INCIDENT_PARAM = "error_incident.occurrences_kept_per_incident"


class ErrorOccurrence(models.Model):
    _name = "error.occurrence"
    _description = "Error Occurrence"
    _order = "date_occurred desc, id desc"
    _rec_name = "occurrence_ref"
    _log_access = False

    incident_id = fields.Many2one(
        comodel_name="error.incident",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    occurrence_ref = fields.Char(
        string="Reference",
        readonly=True,
        required=True,
        help="Handed to the browser with the error, so it can name this "
        "occurrence back.",
    )
    source = fields.Selection(
        selection=SOURCES,
        readonly=True,
    )
    date_occurred = fields.Datetime(
        string="Occurred",
        index=True,
        readonly=True,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
        ondelete="set null",
    )
    location = fields.Char(
        readonly=True,
        help="The route, scheduled action or job that failed.",
    )
    request_ref = fields.Char(
        string="Request",
        readonly=True,
        help="The request's X-Request-Id, as the server log carries it.",
    )
    origin_line = fields.Integer(
        string="Line",
        readonly=True,
    )
    message = fields.Text(
        readonly=True,
    )
    traceback = fields.Text(
        readonly=True,
        help="Secrets masked before storage.",
    )

    _occurrence_ref_uniq = models.Constraint(
        "UNIQUE(occurrence_ref)",
        "An occurrence with this reference already exists.",
    )

    def _gc_occurrences(self) -> None:
        """Keep each incident's newest occurrences, and none past retention."""
        settings = self.env.registry.settings
        days = settings.get_int(self.env, RETENTION_DAYS_PARAM, 90)
        kept = settings.get_int(self.env, KEPT_PER_INCIDENT_PARAM, 50)
        floor = fields.Datetime.now() - timedelta(days=days)
        self.flush_model()
        self.env.cr.execute(
            SQL(
                """
                DELETE FROM error_occurrence
                 WHERE date_occurred < %s
                    OR id IN (
                        SELECT id FROM (
                            SELECT id, row_number() OVER (
                                PARTITION BY incident_id
                                ORDER BY date_occurred DESC, id DESC) AS rank
                              FROM error_occurrence) ranked
                         WHERE rank > %s)
                """,
                floor,
                kept,
            )
        )
        _debug.logic(
            "occurrences.gc", deleted=self.env.cr.rowcount, days=days, kept=kept
        )
        self.invalidate_model()
