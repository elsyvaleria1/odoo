import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools.view_ir import Node, to_string

from .hr_homeworking import DAYS

_debug = DebugLog(__name__)

TODAY_LOCATION_MARKER = "today_location_name"
_MARKER_TOKEN = re.compile(rf"\b{TODAY_LOCATION_MARKER}\b")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    monday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Monday",
    )
    tuesday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Tuesday",
    )
    wednesday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Wednesday",
    )
    thursday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Thursday",
    )
    friday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Friday",
    )
    saturday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Saturday",
    )
    sunday_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Sunday",
    )
    location_ids = fields.One2many(
        comodel_name="hr.employee.location",
        inverse_name="employee_id",
        string="Exceptional Work Locations",
        groups="hr.group_hr_user",
    )
    exceptional_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        string="Current",
        compute="_compute_exceptional_location_id",
        compute_sudo=True,
        groups="hr.group_hr_user",
        help="This is the exceptional, non-weekly, location set for today.",
    )
    today_location_name = fields.Char(
        related="work_location_name",
        string="Today's Work Location",
    )
    hr_icon_display = fields.Selection(
        selection_add=[
            ("presence_home", "At Home"),
            ("presence_office", "At Office"),
            ("presence_other", "At Other"),
        ]
    )

    @api.model
    def _get_current_day_location_field(self):
        return DAYS[fields.Date.context_today(self).weekday()]

    def _today_by_employee(self):
        now = datetime.now(UTC)
        by_zone = {}
        today = {}
        for employee in self:
            zone = employee.tz or "UTC"
            if zone not in by_zone:
                by_zone[zone] = now.astimezone(ZoneInfo(zone)).date()
            today[employee.id] = by_zone[zone]
        return today

    @api.model
    def _rewrite_today_location_marker(self, root: Node, dayfield: str) -> bool:
        changed = False
        for _path, node in root.walk():
            if node.kind == "field" and node.attrs.get("name") == TODAY_LOCATION_MARKER:
                node.attrs["name"] = dayfield
                changed = True
            context = node.attrs.get("context")
            if context and _MARKER_TOKEN.search(context):
                node.attrs["context"] = _MARKER_TOKEN.sub(dayfield, context)
                changed = True
        return changed

    @api.model
    def get_views(self, views, options=None):
        res = super().get_views(views, options)
        dayfield = self._get_current_day_location_field()
        rewritten_types = []
        for view_type in ("search", "list"):
            view = res["views"].get(view_type)
            if not view:
                continue
            root = Node.from_dict(view["ir"])
            if not self._rewrite_today_location_marker(root, dayfield):
                continue
            view["ir"] = root.to_dict()
            if "arch" in view:
                view["arch"] = to_string(root)
            rewritten_types.append(view_type)
        res["models"][self._name]["fields"].update(self.fields_get([dayfield]))
        _debug.logic(
            "get_views.today_location", dayfield=dayfield, views=rewritten_types
        )
        return res

    def _get_today_location(self) -> dict:
        today = self._today_by_employee()
        return {
            employee.id: (
                employee.exceptional_location_id
                or employee[DAYS[today[employee.id].weekday()]]
            )
            for employee in self
        }

    @api.depends("tz", "location_ids.date", "location_ids.work_location_id")
    def _compute_exceptional_location_id(self) -> None:
        today = self._today_by_employee()
        dates = set(today.values())
        exceptions = self.env["hr.employee.location"].search(
            [("employee_id", "in", self.ids), ("date", "in", list(dates))]
        )
        by_employee_and_date = {
            (exception.employee_id.id, exception.date): exception.work_location_id
            for exception in exceptions
        }
        _debug.logic(
            "exceptional_location.resolved",
            employees=self,
            dates=sorted(str(date) for date in dates),
            exceptions=len(exceptions),
        )
        for employee in self:
            employee.exceptional_location_id = by_employee_and_date.get(
                (employee.id, today[employee.id]), False
            )

    @api.depends(*DAYS, "tz", "exceptional_location_id", "active")
    def _compute_presence_icon(self):
        super()._compute_presence_icon()
        today_locations = self._get_today_location()
        for employee in self:
            location = today_locations[employee.id]
            if not location or not employee.active:
                continue
            employee.hr_icon_display = f"presence_{location.location_type}"
            employee.show_hr_icon_display = True

    @api.depends(*DAYS, "tz", "exceptional_location_id")
    def _compute_work_location_name(self) -> None:
        today_locations = self._get_today_location()
        for employee in self:
            employee.work_location_name = today_locations[employee.id].name

    @api.depends(*DAYS, "tz", "exceptional_location_id")
    def _compute_work_location_type(self) -> None:
        today_locations = self._get_today_location()
        for employee in self:
            employee.work_location_type = today_locations[employee.id].location_type
