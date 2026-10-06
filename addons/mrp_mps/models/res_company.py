from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools.date_utils import add, end_of, start_of, subtract
from odoo.tools.misc import format_date

_debug = DebugLog(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    manufacturing_period = fields.Selection(
        selection=[
            ("year", "Yearly"),
            ("month", "Monthly"),
            ("week", "Weekly"),
            ("day", "Daily"),
        ],
        default="month",
        required=True,
        help="Default value for the time ranges in Master Production Schedule report.",
    )
    manufacturing_period_to_display_year = fields.Integer(
        string="Number of columns for the yearly period to display in Master Production Schedule",
        default=3,
    )
    manufacturing_period_to_display_month = fields.Integer(
        string="Number of columns for the monthly period to display in Master Production Schedule",
        default=12,
    )
    manufacturing_period_to_display_week = fields.Integer(
        string="Number of columns for the weekly period to display in Master Production Schedule",
        default=12,
    )
    manufacturing_period_to_display_day = fields.Integer(
        string="Number of columns for the daily period to display in Master Production Schedule",
        default=30,
    )
    mrp_mps_show_starting_inventory = fields.Boolean(
        string="Display Starting Inventory",
        default=True,
    )
    mrp_mps_show_demand_forecast = fields.Boolean(
        string="Display Demand Forecast",
        default=True,
    )
    mrp_mps_show_actual_demand = fields.Boolean(
        string="Display Actual Demand",
        default=False,
    )
    mrp_mps_show_indirect_demand = fields.Boolean(
        string="Display Indirect Demand",
        default=True,
    )
    mrp_mps_show_indirect_actual_demand = fields.Boolean(
        string="Display Indirect Actual Demand",
        default=False,
    )
    mrp_mps_show_to_replenish = fields.Boolean(
        string="Display To Replenish",
        default=True,
    )
    mrp_mps_show_actual_replenishment = fields.Boolean(
        string="Display Actual Replenishment",
        default=False,
    )
    mrp_mps_show_safety_stock = fields.Boolean(
        string="Display Safety Stock",
        default=True,
    )
    mrp_mps_show_available_to_promise = fields.Boolean(
        string="Display Available to Promise",
        default=False,
    )
    mrp_mps_show_actual_demand_year_minus_1 = fields.Boolean(
        string="Display Actual Demand Last Year",
        default=False,
    )
    mrp_mps_show_actual_demand_year_minus_2 = fields.Boolean(
        string="Display Actual Demand Before Year",
        default=False,
    )

    @api.model
    def _is_field_mps_display_group(self, fname) -> bool:
        field = self._fields.get(fname)
        return (
            field is not None
            and field.type == "boolean"
            and fname.startswith(("mrp_mps", "x_mrp_mps", "x_studio_mrp_mps"))
        )

    def _get_date_range(self, years=False, force_period=False):
        """Return the date range for a production schedude depending the
        manufacturing period and the number of columns to display specify by the
        user. It returns a list of tuple that contains the timestamp for each
        column.
        """
        self.check_singleton()
        date_range = []
        period = force_period or self.manufacturing_period
        if not years:
            years = 0
        first_day = start_of(subtract(fields.Date.today(), years=years), period)
        for _i in range(self["manufacturing_period_to_display_%s" % period]):
            last_day = end_of(first_day, period)
            date_range.append((first_day, last_day))
            first_day = add(last_day, days=1)
        return date_range

    def _date_range_to_str(self, force_period=False):
        date_range = self._get_date_range(force_period=force_period)
        dates_as_str = []
        period = force_period or self.manufacturing_period
        for date_start, date_stop in date_range:
            if period == "year":
                dates_as_str.append(
                    format_date(self.env, date_start, date_format="yyyy")
                )
            elif period == "month":
                dates_as_str.append(
                    format_date(self.env, date_start, date_format="MMM yyyy")
                )
            elif period == "week":
                dates_as_str.append(
                    self.env._(
                        "Week %(week_num)s (%(start_date)s-%(end_date)s/%(month)s)",
                        week_num=format_date(self.env, date_start, date_format="w"),
                        start_date=format_date(self.env, date_start, date_format="d"),
                        end_date=format_date(self.env, date_stop, date_format="d"),
                        month=format_date(self.env, date_stop, date_format="MMM"),
                    )
                )
            else:
                dates_as_str.append(
                    format_date(self.env, date_start, date_format="MMM d")
                )
        return dates_as_str

    def write(self, vals):
        if (
            (
                "manufacturing_period_to_display_year" in vals
                and vals["manufacturing_period_to_display_year"] <= 0
            )
            or (
                "manufacturing_period_to_display_month" in vals
                and vals["manufacturing_period_to_display_month"] <= 0
            )
            or (
                "manufacturing_period_to_display_week" in vals
                and vals["manufacturing_period_to_display_week"] <= 0
            )
            or (
                "manufacturing_period_to_display_day" in vals
                and vals["manufacturing_period_to_display_day"] <= 0
            )
        ):
            _debug.logic("mps_settings_refused", reason="zero_periods", companies=self)
            raise UserError(
                self.env._(
                    "Manufacturing Settings: Your Master Production Schedule must always display at least 1 period."
                )
            )
        if len(vals) == 1:
            (fname,) = vals.keys()
            if self._is_field_mps_display_group(fname) and self.env.user.has_group(
                "mrp.group_mrp_manager"
            ):
                _debug.logic(
                    "mps_settings_escalated",
                    companies=self,
                    field=fname,
                    by="mrp_manager_sudo",
                )
                return super(ResCompany, self.sudo()).write(vals)
        return super().write(vals)

    def save_company_settings(self, vals):
        """Function to call from JS to avoid a full reload of the page and context."""
        return self.write(vals)
