import logging
import uuid
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.tools import SQL

_logger = logging.getLogger(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"

    avatar_128 = fields.Image(
        export_string_translation=False,
        compute="_compute_avatar_128",
    )
    planning_token = fields.Char(
        string="Security Token",
        export_string_translation=False,
        default=lambda self: str(uuid.uuid4()),
        copy=False,
        readonly=True,
        groups="hr.group_hr_user",
        help="Identifies this person on the schedule they are sent, whether or not they are an employee.",
    )
    default_role_id = fields.Many2one(
        groups="hr.group_hr_user",
        help="Role selected by default when creating a shift for this resource.",
    )

    _planning_token_unique = models.Constraint(
        "unique(planning_token)",
        "Error: each planning token must be unique",
    )

    def _init_column(self, column_name, *, new_column=False):
        if column_name != "planning_token":
            super()._init_column(column_name, new_column=new_column)
            return
        _logger.debug(
            "Table '%s': setting default value of new column %s to unique values for each row",
            self._table,
            column_name,
        )
        self.env.cr.execute(
            SQL(
                "SELECT id FROM %s WHERE planning_token IS NULL",
                SQL.identifier(self._table),
            )
        )
        rows = self.env.cr.dictfetchall()
        values_args = [(row["id"], str(uuid.uuid4())) for row in rows]
        if not values_args:
            return
        table = SQL.identifier(self._table).code
        query = f"""
            UPDATE {table}
            SET planning_token = vals.token
            FROM (VALUES %s) AS vals(id, token)
            WHERE {table}.id = vals.id
        """
        self.env.cr.execute_values(query, values_args)

    def _planning_get_url(self, date_start, date_end, planning=None):
        result = {}
        for resource in self:
            user = resource.sudo().user_id
            if user and not user._is_portal():
                result[resource.id] = (
                    f"/odoo/action-planning.planning_action_view_shift?date_start={date_start}&date_end={date_end}"
                )
            else:
                result[resource.id] = "/planning/%s/%s" % (
                    planning._page_token(resource),
                    resource.sudo().planning_token,
                )
        return result

    def action_reset_planning_token(self):
        for resource in self:
            resource.planning_token = str(uuid.uuid4())

    def _get_planning_email(self):
        self.check_singleton()
        return self.sudo().partner_id.email

    def get_formview_id(self, access_uid=None):
        if self.env.context.get("from_planning"):
            view = self.env.ref(
                "planning.resource_resource_with_employee_form_view_inherit",
                raise_if_not_found=False,
            )
            if view:
                return view.id
        return super().get_formview_id(access_uid)

    @api.model_create_multi
    def create(self, vals_list):
        resources = super().create(vals_list)
        if self.env.context.get("from_planning"):
            create_vals = [
                {
                    "name": resource.name,
                    "resource_id": resource.id,
                }
                for resource in resources.filtered(lambda r: r.type == "human")
            ]
            self.env["hr.employee"].sudo().with_context(from_planning=False).create(
                create_vals
            )
        return resources

    @api.depends("employee_id")
    @api.depends_context("show_job_title")
    def _compute_display_name(self):
        if not self.env.context.get("show_job_title"):
            return super()._compute_display_name()
        for resource in self:
            resource_default_role_id = resource.sudo().default_role_id
            if resource.type != "human" and resource_default_role_id:
                resource.display_name = self.env._(
                    "%(resource_name)s (%(role)s)",
                    resource_name=resource.name,
                    role=resource_default_role_id.name,
                )
            else:
                resource.display_name = (
                    resource.employee_id.display_name
                    if resource.employee_id
                    else resource.name
                )
        return None

    def action_archive(self):
        res = super().action_archive()
        departure_date = datetime.combine(
            fields.Date.context_today(self) + timedelta(days=1), time.min
        )
        planning_slots = (
            self.env["planning.slot"]
            .sudo()
            .search(
                [
                    ("resource_id", "in", self.ids),
                    ("resource_type", "!=", "human"),
                    ("end_datetime", ">=", departure_date),
                ]
            )
        )
        planning_slots._manage_archived_resources(departure_date)
        return res

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.type == "human" or not self.env.context.get("from_planning"):
            super()._onchange_company_id()

    def get_avatar_card_data(self, field_names):
        if self.env.user.has_group("hr.group_hr_user"):
            field_names = [*field_names, "default_role_id"]
        result = super().get_avatar_card_data(field_names)
        if not result:
            return []
        roles_ids = result[0].get("role_ids")
        if roles_ids:
            result[0]["role_ids"] = self.env["resource.role"].search_read(
                domain=[("id", "in", roles_ids)],
                fields=["name", "color"],
            )
        return result
