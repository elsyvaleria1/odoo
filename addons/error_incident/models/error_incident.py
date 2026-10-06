import logging
import uuid
from typing import Any, TypedDict

from odoo import SUPERUSER_ID, api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.libs.redact import mask_text
from odoo.tools import SQL, frozendict

from ..tools import fingerprint as fp

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

SOURCES = [
    ("request", "Request"),
    ("cron", "Scheduled Action"),
    ("job", "Background Job"),
]

# What the error dialog follows, pushed to the users an incident affected.
JOURNEY_NOTIFICATION = "error_incident/journey"
JOURNEY_STEPS = ("recorded", "acknowledged", "resolved")
_JOURNEY_STEP_OF_STATE = {"acknowledged": "acknowledged", "resolved": "resolved"}


class JourneyDetails(TypedDict):
    count: int
    regressed: bool


class Journey(TypedDict, total=False):
    incident: int
    steps: list[str]
    step: str
    outcome: str | None
    details: JourneyDetails
    occurrence: str


class ErrorIncident(models.Model):
    _name = "error.incident"
    _description = "Error Incident"
    _inherit = ["mixin.mail.thread"]
    _order = "date_last_seen desc, id desc"
    # An error belongs to the server, not to a company; the users it affected
    # are whose it is.
    _access_anchors = frozendict({"company": "", "owner": "user_ids"})

    name = fields.Char(
        string="Title",
        readonly=True,
        required=True,
    )
    fingerprint = fields.Char(
        readonly=True,
        required=True,
        help="What makes two occurrences one incident: the exception's type and "
        "the innermost frame of our own code, without its line number.",
    )
    fingerprint_version = fields.Integer(
        readonly=True,
    )
    exception_type = fields.Char(
        readonly=True,
    )
    origin_module = fields.Char(
        string="Module",
        readonly=True,
    )
    origin_path = fields.Char(
        string="File",
        readonly=True,
    )
    origin_function = fields.Char(
        string="Function",
        readonly=True,
    )
    source = fields.Selection(
        selection=SOURCES,
        readonly=True,
        help="Where the incident was first seen.",
    )
    incident_state = fields.Selection(
        selection=[
            ("new", "New"),
            ("acknowledged", "Acknowledged"),
            ("resolved", "Resolved"),
            ("regressed", "Regressed"),
            ("set_aside", "Set Aside"),
        ],
        string="State",
        default="new",
        required=True,
        tracking=True,
    )
    rule_id = fields.Many2one(
        comodel_name="error.incident.rule",
        string="Set Aside By",
        readonly=True,
        ondelete="set null",
    )
    date_first_seen = fields.Datetime(
        string="First Seen",
        readonly=True,
    )
    date_last_seen = fields.Datetime(
        string="Last Seen",
        index=True,
        readonly=True,
    )
    count_occurrence = fields.Integer(
        string="Occurrence Count",
        readonly=True,
    )
    count_regression = fields.Integer(
        string="Regressions",
        readonly=True,
        help="How many times it occurred again after being resolved.",
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="error_incident_res_users_rel",
        column1="incident_id",
        column2="user_id",
        string="Affected Users",
        readonly=True,
    )
    occurrence_ids = fields.One2many(
        comodel_name="error.occurrence",
        inverse_name="incident_id",
        string="Occurrences",
        readonly=True,
    )

    _fingerprint_uniq = models.Constraint(
        "UNIQUE(fingerprint)",
        "An incident with this fingerprint already exists.",
    )

    def write(self, vals: dict[str, Any]) -> bool:
        if "incident_state" not in vals:
            return super().write(vals)
        before = {incident.id: incident.incident_state for incident in self}
        result = super().write(vals)
        moved = self.filtered(
            lambda incident: incident.incident_state != before[incident.id]
        )
        moved._notify_journey()
        moved.filtered(
            lambda incident: incident.incident_state == "resolved"
        )._notify_fixed()
        return result

    def action_acknowledge(self) -> None:
        self.incident_state = "acknowledged"

    def action_resolve(self) -> None:
        self.incident_state = "resolved"

    def action_reopen(self) -> None:
        self.write({"incident_state": "acknowledged", "rule_id": False})

    def action_set_aside(self) -> None:
        self.incident_state = "set_aside"

    def _journey(self) -> Journey:
        """Where the incident stands, in the dialog's terms: the steps it walks,
        the one reached, and what cut it short, if anything."""
        self.check_singleton()
        state = self.incident_state
        return {
            "incident": self.id,
            "steps": list(JOURNEY_STEPS),
            "step": _JOURNEY_STEP_OF_STATE.get(state, "recorded"),
            "outcome": "set_aside" if state == "set_aside" else None,
            "details": {
                "count": self.count_occurrence,
                "regressed": state == "regressed",
            },
        }

    def _notify_journey(
        self,
        users: models.BaseModel | None = None,
        occurrence_ref: str | None = None,
    ) -> None:
        """Push each incident's journey to the internal users it affected, or to
        ``users``; naming the occurrence lets the dialog that shows it, opened
        before the occurrence was written, recognise its own."""
        for incident in self:
            recipients = incident.user_ids if users is None else users
            recipients = recipients.filtered(lambda user: not user.share)
            if not recipients:
                continue
            journey = incident._journey()
            if occurrence_ref:
                journey["occurrence"] = occurrence_ref
            recipients._bus_send(JOURNEY_NOTIFICATION, journey)
            _debug.logic(
                "incident.journey_sent",
                incident=incident.id,
                step=journey["step"],
                users=len(recipients),
            )

    def _notify_fixed(self) -> None:
        """Tell every internal user an incident affected that it is fixed, in
        their own language, wherever they are in the web client."""
        for incident in self:
            for user in incident.user_ids.filtered(lambda user: not user.share):
                in_their_language = incident.with_context(lang=user.lang).env
                user._bus_send(
                    "simple_notification",
                    {
                        "type": "success",
                        "title": in_their_language._("An error you ran into was fixed"),
                        "message": incident.name,
                        "sticky": True,
                    },
                )
            _debug.logic("incident.fixed_sent", incident=incident.id)

    def _capture(self, payload: dict[str, Any]) -> int:
        """Record one occurrence; return its incident's id.

        Locks the incident's row, so concurrent occurrences of one fingerprint
        count up one after the other, and a resolved incident that occurs
        again is reopened exactly once.

        :param payload: what the capture hook saw -- see `_capture_payload`.
        """
        now = payload["date"]
        uid = self.env.uid
        # On the cron and job paths this runs inside a live transaction: what
        # the ORM still holds must reach the table before the SQL reads it.
        self.flush_model()
        incident_id, previous_state = self._lock_incident(payload)
        if incident_id is None:
            rule = self.env["error.incident.rule"]._match(payload)
            self.env.cr.execute(
                SQL(
                    """
                    INSERT INTO error_incident (
                        name, fingerprint, fingerprint_version, exception_type,
                        origin_module, origin_path, origin_function, source,
                        incident_state, rule_id, date_first_seen, date_last_seen,
                        count_occurrence, count_regression,
                        create_uid, create_date, write_uid, write_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0,
                            %s, %s, %s, %s)
                    ON CONFLICT (fingerprint) DO NOTHING
                    RETURNING id
                    """,
                    payload["title"],
                    payload["fingerprint"],
                    payload["fingerprint_version"],
                    payload["exception_type"],
                    payload["origin_module"],
                    payload["origin_path"],
                    payload["origin_function"],
                    payload["source"],
                    "set_aside" if rule else "new",
                    rule.id or None,
                    now,
                    now,
                    uid,
                    now,
                    uid,
                    now,
                )
            )
            row = self.env.cr.fetchone()
            if row:
                incident_id, previous_state = row[0], None
                _debug.logic(
                    "incident.created",
                    incident=incident_id,
                    source=payload["source"],
                    set_aside=bool(rule),
                )
            else:
                incident_id, previous_state = self._lock_incident(payload)
        regressed = previous_state == "resolved"
        self.env.cr.execute(
            SQL(
                """
                UPDATE error_incident
                   SET count_occurrence = count_occurrence + 1,
                       count_regression = count_regression + %s,
                       incident_state = CASE WHEN %s THEN 'regressed'
                                             ELSE incident_state END,
                       date_last_seen = GREATEST(date_last_seen, %s),
                       write_uid = %s, write_date = %s
                 WHERE id = %s
                """,
                int(regressed),
                regressed,
                now,
                uid,
                now,
                incident_id,
            )
        )
        if payload.get("user_id"):
            self.env.cr.execute(
                SQL(
                    """
                    INSERT INTO error_incident_res_users_rel (incident_id, user_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    incident_id,
                    payload["user_id"],
                )
            )
        hit_by = self.env["res.users"].browse(payload.get("user_id")).exists()
        self.env["error.occurrence"].create(
            self._prepare_occurrence_vals(incident_id, payload, hit_by)
        )
        self.invalidate_model()
        incident = self.browse(incident_id)
        if regressed:
            incident.message_post(
                body=self.env._("It occurred again after it was resolved."),
            )
            incident._notify_journey(users=incident.user_ids - hit_by)
        incident._notify_journey(users=hit_by, occurrence_ref=payload["occurrence_ref"])
        _debug.logic(
            "incident.occurrence",
            incident=incident_id,
            regressed=regressed,
            source=payload["source"],
        )
        return incident_id

    def _lock_incident(self, payload: dict[str, Any]) -> tuple[int | None, str | None]:
        self.env.cr.execute(
            SQL(
                "SELECT id, incident_state FROM error_incident"
                " WHERE fingerprint = %s FOR UPDATE",
                payload["fingerprint"],
            )
        )
        row = self.env.cr.fetchone()
        return (row[0], row[1]) if row else (None, None)

    def _prepare_occurrence_vals(
        self, incident_id: int, payload: dict[str, Any], user: models.BaseModel
    ) -> dict[str, Any]:
        return {
            "incident_id": incident_id,
            "occurrence_ref": payload["occurrence_ref"],
            "source": payload["source"],
            "date_occurred": payload["date"],
            "user_id": user.id,
            "company_id": user.company_id.id,
            "location": payload.get("location"),
            "request_ref": payload.get("request_ref"),
            "origin_line": payload.get("origin_line"),
            "message": payload["message"],
            "traceback": payload["traceback"],
        }

    def _capture_quietly(self, payload: dict[str, Any]) -> int | None:
        """`_capture`, for the error path: it never raises.

        It runs while something else has already gone wrong; a failure to
        record must not hide, replace or worsen the one being recorded. The
        system records it, whoever's code failed.
        """
        try:
            with self.env.cr.savepoint():
                system = api.Environment(self.env.cr, SUPERUSER_ID, {})
                return system["error.incident"]._capture(payload)
        except Exception:
            _logger.exception(
                "Could not record an occurrence of %s", payload.get("fingerprint")
            )
            return None


def capture_payload(
    exc: BaseException,
    source: str,
    *,
    user_id: int | None = None,
    location: str | None = None,
    request_ref: str | None = None,
    occurrence_ref: str | None = None,
) -> dict[str, Any]:
    """Everything recorded about one occurrence, taken while it is at hand.

    Built from the exception alone, without the database: on the request path
    it is taken before the cursor is handed back, and written after.
    """
    kind = fp.exception_type(exc)
    where = fp.origin(exc)
    title = f"{kind} in {where.function or '?'}"
    if where.module:
        title = f"{title} ({where.module})"
    return {
        "title": title[:200],
        "fingerprint": fp.fingerprint(kind, where),
        "fingerprint_version": fp.FINGERPRINT_VERSION,
        "exception_type": kind,
        "origin_module": where.module,
        "origin_path": where.path,
        "origin_function": where.function,
        "origin_line": where.line,
        "source": source,
        "user_id": user_id or None,
        "location": location,
        "request_ref": request_ref,
        "occurrence_ref": occurrence_ref or uuid.uuid4().hex,
        "date": fields.Datetime.now(),
        "message": mask_text(str(exc), 2000),
        "traceback": mask_text(fp.format_traceback(exc), 40000),
    }
