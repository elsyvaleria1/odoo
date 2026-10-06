from odoo import fields, models
from odoo.db.schema import drop_view_if_exists
from odoo.tools import frozendict


class EditBillableTimeTarget(models.Model):
    _name = "edit.billable.time.target"
    _description = "Edit Billable Time Target wizard from Timesheet for users without employee access"
    _order = "name"
    _auto = False
    _depends = frozendict(
        {
            "hr.employee": [
                "billable_time_target",
                "coach_id",
                "company_id",
                "name",
                "parent_id",
                "partner_id",
                "timesheet_manager_id",
                "user_id",
            ],
            "hr.version": [
                "active",
                "address_id",
                "company_id",
                "create_date",
                "create_uid",
                "date_version",
                "department_id",
                "employee_id",
                "job_id",
                "resource_calendar_id",
                "work_location_id",
                "write_date",
                "write_uid",
            ],
            "phone.number": ["number", "primary", "sequence", "type", "partner_ids"],
            "res.company": ["timesheet_show_rates"],
            "res.partner": ["email"],
        }
    )
    _log_access = True
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
            "owner": "parent_id.user_id",
            "timesheet_manager_or_unset": models.Anchor(
                "timesheet_manager_id", kind="owner", shared=True
            ),
        }
    )

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    create_date = fields.Datetime(readonly=True)
    name = fields.Char(readonly=True)
    resource_calendar_id = fields.Many2one(
        comodel_name="resource.calendar",
        string="Working Hours",
        readonly=True,
    )
    billable_time_target = fields.Float(string="Monthly Billing Time Target")
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    department_id = fields.Many2one(
        comodel_name="hr.department",
        readonly=True,
    )
    job_id = fields.Many2one(
        comodel_name="hr.job",
        string="Job Position",
        readonly=True,
    )
    parent_id = fields.Many2one(
        comodel_name="hr.employee",
        string="Manager",
        readonly=True,
    )
    child_ids = fields.One2many(
        comodel_name="hr.employee",
        inverse_name="parent_id",
        string="Direct subordinates",
    )
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Work Address",
        readonly=True,
    )
    work_location_id = fields.Many2one(
        comodel_name="hr.work.location",
        readonly=True,
    )
    work_location_name = fields.Char(
        related="work_location_id.name",
        string="Work Location Name",
        readonly=True,
    )
    timesheet_manager_id = fields.Many2one(
        comodel_name="res.users",
        string="Timesheet Approver",
        readonly=True,
    )
    show_hr_icon_display = fields.Boolean(related="employee_id.show_hr_icon_display")
    hr_icon_display = fields.Selection(related="employee_id.hr_icon_display")
    hr_presence_state = fields.Selection(related="employee_id.hr_presence_state")
    image_128 = fields.Image(
        related="employee_id.image_128",
        string="Image 128",
        compute_sudo=True,
    )
    avatar_128 = fields.Image(
        related="employee_id.avatar_128",
        string="Avatar 128",
        compute_sudo=True,
    )
    avatar_1920 = fields.Image(
        related="employee_id.avatar_1920",
        string="Avatar 1920",
        compute_sudo=True,
    )
    image_1024 = fields.Image(
        related="employee_id.image_1024",
        string="Image 1024",
        compute_sudo=True,
    )
    work_email = fields.Char(readonly=True)
    work_phone = fields.Char(readonly=True)
    mobile_phone = fields.Char(readonly=True)
    birthday_public_display_string = fields.Char(
        related="employee_id.birthday_public_display_string"
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    coach_id = fields.Many2one(
        comodel_name="hr.employee",
        readonly=True,
    )
    member_of_department = fields.Boolean(related="employee_id.member_of_department")
    newly_hired = fields.Boolean(related="employee_id.newly_hired")
    active = fields.Boolean(readonly=True)

    def write(self, vals):
        """We only allow the user to edit the billable time target of his employees"""
        employee_vals = {}
        if "billable_time_target" in vals:
            employee_vals["billable_time_target"] = vals.pop("billable_time_target")
            # seed the cache of this SQL-view-backed model directly (the real
            # write goes to hr.employee below); use the Field cache API rather
            # than the legacy env.cache compatibility shim
            field = self._fields["billable_time_target"]
            field._update_cache(
                self,
                field.convert_to_cache(employee_vals["billable_time_target"], self),
            )

        self.check_access("write")
        res = True
        if employee_vals:
            res = self.env["hr.employee"].browse(self.ids).sudo().write(employee_vals)
        return res

    _PARTY_PHONE_SQL = """(
        SELECT pn.number
          FROM res_partner_phone_number_rel rel
          JOIN phone_number pn ON pn.id = rel.phone_number_id
         WHERE rel.partner_id = p.id AND pn.type = '%s'
         ORDER BY pn."primary" DESC, pn.sequence, pn.id
         LIMIT 1)"""

    _PARTY_COLUMNS = {
        "work_email": "p.email",
        "work_phone": _PARTY_PHONE_SQL % "landline",
        "mobile_phone": _PARTY_PHONE_SQL % "mobile",
    }

    def _get_column_names(self):
        return [
            name
            for name, field in self._fields.items()
            if field.store
            and field.type not in ["many2many", "one2many"]
            and name not in ["id", "name"]
        ]

    def _get_version_column_names(self) -> list:
        version_fields = self.env["hr.version"]._fields
        return [
            name
            for name in self._get_column_names()
            if name not in self._PARTY_COLUMNS
            and name in version_fields
            and version_fields[name].store
        ]

    def _get_fields(self):
        version_columns = self._get_version_column_names()
        return "e.id AS id,e.name AS name," + ",".join(
            (
                f"{self._PARTY_COLUMNS[name]} AS {name}"
                if name in self._PARTY_COLUMNS
                else f"v.{name}"
                if name in version_columns
                else f"e.{name}"
            )
            for name in self._get_column_names()
        )

    def init(self) -> None:
        drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            f"""
                CREATE OR REPLACE VIEW {self._table} AS (
                        SELECT {self._get_fields()}
                          FROM hr_employee e
                          JOIN (
                              SELECT DISTINCT ON (employee_id)
                                     {", ".join(dict.fromkeys(["employee_id", *self._get_version_column_names()]))}
                              FROM hr_version
                              ORDER BY employee_id, date_version DESC
                          ) v ON v.employee_id = e.id
                          JOIN res_partner p ON p.id = e.partner_id
                    INNER JOIN res_company company
                            ON e.company_id = company.id
                         WHERE company.timesheet_show_rates IS TRUE
                )
            """
        )
