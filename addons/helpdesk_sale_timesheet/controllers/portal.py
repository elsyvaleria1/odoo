from odoo.exceptions import AccessError, MissingError
from odoo.http import request

from odoo.addons.helpdesk.controllers import portal
from odoo.addons.hr_timesheet.controllers.portal import TimesheetCustomerPortal


class CustomerPortal(portal.CustomerPortal):
    def _ticket_get_page_view_values(self, ticket, access_token, /, **kwargs):
        values = super()._ticket_get_page_view_values(ticket, access_token, **kwargs)
        if ticket.use_helpdesk_sale_timesheet and ticket.sale_order_id:
            try:
                request.env["access.link"]._open_record(
                    "sale.order", ticket.sale_order_id.id
                )
                values["ticket_link_section"].append(
                    {
                        "access_url": ticket.sale_order_id.get_portal_url(),
                        "title": f"{request.env._('Sales Order')} - {ticket.sale_order_id.name}",
                        "sequence": 1,
                    }
                )
            except AccessError, MissingError:
                pass
        if ticket.use_helpdesk_sale_timesheet:
            Timesheet = request.env["account.analytic.line"]
            values["timesheets"] = ticket.timesheet_ids._get_portal_helpdesk_timesheet()
            is_encode_uom_day = Timesheet._is_timesheet_encode_uom_day()
            values["is_uom_day"] = is_encode_uom_day
            if is_encode_uom_day:
                values["convert_hours_to_days"] = Timesheet._convert_hours_to_days
        return values

    def _prepare_my_tickets_values(
        self,
        page=1,
        date_begin=None,
        date_end=None,
        sortby=None,
        filterby="all",
        search=None,
        groupby="none",
        search_in="name",
    ):
        if (search_in == "sale_order" or groupby == "sale_line_id") and not request.env[
            "team.team"
        ]._is_sale_timesheet_feature_enabled():
            search_in = "name" if search_in == "sale_order" else search_in
            groupby = "none" if groupby == "sale_line_id" else groupby
        values = super()._prepare_my_tickets_values(
            page, date_begin, date_end, sortby, filterby, search, groupby, search_in
        )
        Timesheet = request.env["account.analytic.line"]
        is_encode_uom_day = Timesheet._is_timesheet_encode_uom_day()
        values["is_uom_day"] = is_encode_uom_day
        if is_encode_uom_day:
            values["convert_hours_to_days"] = Timesheet._convert_hours_to_days
        return values

    def _ticket_get_searchbar_inputs(self):
        searchbar_inputs = super()._ticket_get_searchbar_inputs()
        if request.env["team.team"]._is_sale_timesheet_feature_enabled():
            searchbar_inputs |= {
                "sale_order": {
                    "input": "sale_order",
                    "label": request.env._("Search in Sales Order Item"),
                    "sequence": 60,
                }
            }
        return searchbar_inputs

    def _ticket_get_searchbar_groupby(self):
        searchbar_groupby = super()._ticket_get_searchbar_groupby()
        if request.env["team.team"]._is_sale_timesheet_feature_enabled():
            searchbar_groupby |= {
                "sale_line_id": {
                    "label": request.env._("Sales Order Item"),
                    "sequence": 70,
                },
            }
        return searchbar_groupby

    def _ticket_get_search_domain(self, search_in, search):
        if search_in == "sale_order":
            return [
                "|",
                ("sale_order_id.name", "ilike", search),
                ("sale_line_id.name", "ilike", search),
            ]
        else:
            return super()._ticket_get_search_domain(search_in, search)


class HelpdeskSaleTimesheetCustomerPortal(TimesheetCustomerPortal):
    def _get_searchbar_inputs(self):
        return super()._get_searchbar_inputs() | {
            "helpdesk_ticket_id": {
                "input": "helpdesk_ticket_id",
                "label": request.env._("Search in Ticket"),
                "sequence": 60,
            },
        }

    def _get_searchbar_groupby(self):
        return super()._get_searchbar_groupby() | {
            "helpdesk_ticket_id": {"label": request.env._("Ticket"), "sequence": 60},
        }
