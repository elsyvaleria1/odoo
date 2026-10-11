from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardHrEmployeeRegisterDeparture(models.TransientModel):
    _name = "wizard.hr.employee.register.departure"
    _description = "Departure Wizard"

    def _default_departure_date(self):
        if len(active_ids := self.env.context.get("active_ids", [])) == 1:
            employee = self.env["hr.employee"].browse(active_ids[0]).sudo()
            departure_date = employee and employee._get_departure_date()
        else:
            departure_date = False

        _debug.logic(
            "default_departure_date",
            active_ids=active_ids,
            date=departure_date or "today",
        )
        return departure_date or fields.Date.today()

    def _default_employee_ids(self):
        active_ids = self.env.context.get("active_ids", [])
        if active_ids:
            return (
                self.env["hr.employee"]
                .browse(active_ids)
                .filtered(lambda e: e.company_id in self.env.companies)
            )
        return self.env["hr.employee"]

    def _domain_employee_ids(self):
        return [("active", "=", True), ("company_id", "in", self.env.companies.ids)]

    departure_reason_id = fields.Many2one(
        comodel_name="hr.departure.reason",
        default=lambda self: self.env["hr.departure.reason"].search([], limit=1),
        required=True,
    )
    departure_description = fields.Html(string="Additional Information")
    departure_date = fields.Date(
        string="Contract End Date",
        default=lambda self: self._default_departure_date(),
        required=True,
    )
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Employees",
        default=lambda self: self._default_employee_ids(),
        required=True,
        domain=_domain_employee_ids,
        context={"active_test": False},
    )

    is_user_employee = fields.Boolean(
        string="User Employee",
        compute="_compute_is_user_employee",
    )
    remove_related_user = fields.Boolean(
        string="Related User",
        help="If checked, the related user will be removed from the system.",
    )

    set_date_end = fields.Boolean(
        string="Set Contract End Date",
        default=lambda self: self.env.user.has_group("hr.group_hr_manager"),
        help="Set the end date on the current contract.",
    )

    @api.depends("employee_ids.user_id")
    def _compute_is_user_employee(self) -> None:
        for wizard in self:
            wizard.is_user_employee = bool(wizard.employee_ids.user_id)

    def _prepare_action_user_archive_notification(
        self, message, message_type, next_action
    ) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("User Archive Notification"),
                "type": message_type,
                "message": message,
                "next": next_action,
            },
        }

    def _split_users_archivable_and_kept(self) -> tuple:
        archivable = kept = self.env["res.users"]
        if not self.remove_related_user:
            return archivable, kept
        employees_per_user = self.employee_ids.grouped("user_id")
        total_per_user = dict(
            self.env["hr.employee"]
            .sudo()
            .with_context(active_test=False)
            ._read_group(
                domain=[("user_id", "in", self.employee_ids.user_id.ids)],
                groupby=["user_id"],
                aggregates=["id:count"],
            )
        )
        for user, employees in employees_per_user.items():
            if not user:
                continue
            if len(employees) == total_per_user.get(user, 0):
                archivable |= user
            else:
                kept |= user
        _debug.logic(
            "users_archivable", wizard=self.id, archivable=archivable, kept=kept
        )
        return archivable, kept

    def _check_departure_date_against_contracts(self, versions) -> None:
        if any(
            version.contract_date_start
            and version.contract_date_start > self.departure_date
            for version in versions.sudo()
        ):
            raise UserError(
                self.env._(
                    "Departure date can't be earlier than the start date of current contract."
                )
            )

    @_debug.perf.timed
    def action_register_departure(self):
        employee_ids = self.employee_ids
        active_versions = employee_ids.version_id
        _debug.lifecycle(
            "departure_started",
            departure=self.id,
            employees=employee_ids,
            date=self.departure_date,
            reason=self.departure_reason_id.id,
            termination=bool(self.env.context.get("employee_termination")),
            remove_user=self.remove_related_user,
            set_date_end=self.set_date_end,
        )
        self._check_departure_date_against_contracts(active_versions)

        allow_archived_users, unarchived_users = self._split_users_archivable_and_kept()

        archived_employees = self.env["hr.employee"]
        archived_users = self.env["res.users"]
        if self.env.context.get("employee_termination", False):
            archived_employees = employee_ids.filtered("active")
            if self.remove_related_user:
                archived_users = archived_employees.user_id & allow_archived_users

        _debug.pipeline(
            "employees_archived", departure=self.id, employees=archived_employees
        )
        archived_employees.with_context(no_wizard=True).action_archive()
        archived_users = archived_users.filtered(
            lambda u: u.id not in (self.env.uid, SUPERUSER_ID)
        )
        _debug.pipeline("users_archived", departure=self.id, users=archived_users)
        archived_users.sudo().action_archive()

        _debug.pipeline(
            "departure_fields_written", departure=self.id, employees=employee_ids
        )
        employee_ids.write(
            {
                "departure_reason_id": self.departure_reason_id,
                "departure_description": self.departure_description,
                "departure_date": self.departure_date,
            }
        )
        employee_ids._dispose_departed_resources()

        if self.set_date_end:
            active_versions.check_access("write")
            contracts = active_versions.with_privilege(
                "hr.privilege_end_departed_contract",
                reason="a departure ends its employee's running contract",
            ).filtered(lambda v: v.contract_date_start)
            _debug.pipeline(
                "contract_ended",
                departure=self.id,
                date=self.departure_date,
                versions=contracts,
            )
            contracts.write({"contract_date_end": self.departure_date})

        next_action = {"type": "ir.actions.act_window_close"}
        for users, message_type, message in (
            (
                archived_users,
                "success",
                self.env._(
                    "The following users have been archived: %s",
                    ", ".join(archived_users.mapped("name")),
                ),
            ),
            (
                unarchived_users,
                "danger",
                self.env._(
                    "The following users have not been archived as they are still linked to another active employees: %s",
                    ", ".join(unarchived_users.mapped("name")),
                ),
            ),
        ):
            if users:
                next_action = self._prepare_action_user_archive_notification(
                    message, message_type, next_action
                )
        _debug.lifecycle("departure_done", departure=self.id)
        return next_action
