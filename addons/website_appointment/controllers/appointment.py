from odoo import http
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools.urls import keep_query

from odoo.addons.calendar.controllers.booking import AppointmentController

_debug = DebugLog(__name__)


class WebsiteAppointment(AppointmentController):
    @http.route()
    def appointment_type_index(self, page=1, **kwargs):
        kwargs["domain"] = self._appointments_base_domain(
            filter_appointment_type_ids=kwargs.get("filter_appointment_type_ids"),
            search=kwargs.get("search"),
            invite_token=kwargs.get("invite_token"),
            additional_domain=self._appointment_website_domain(),
            filter_countries=True,
        )
        available_appointment_types = self._get_checked_private_appointment_types(
            kwargs.get("filter_appointment_type_ids"),
            kwargs.get("filter_staff_user_ids"),
            kwargs.get("filter_resource_ids"),
            kwargs.get("invite_token"),
            domain=kwargs["domain"],
        )
        if len(available_appointment_types) == 1 and not kwargs.get("search"):
            _debug.lifecycle(
                "index_redirect_single", appointment_type=available_appointment_types
            )
            return request.redirect(
                "/appointment/%s?%s" % (available_appointment_types.id, keep_query("*"))
            )

        cards_layout = request.website.viewref(
            "website_appointment.opt_appointments_list_cards"
        ).active

        _debug.pipeline(
            "index",
            page=page,
            available=len(available_appointment_types),
            cards_layout=cards_layout,
            searched=bool(kwargs.get("search")),
            invited=bool(kwargs.get("invite_token")),
        )
        if cards_layout:
            return request.render(
                "website_appointment.appointments_cards_layout",
                self._prepare_appointments_cards_data(
                    page, available_appointment_types, **kwargs
                ),
            )
        else:
            return request.render(
                "calendar.appointments_list_layout",
                self._prepare_appointments_list_data(
                    available_appointment_types, **kwargs
                ),
            )

    @http.route()
    def appointment_form_submit(self, *args, **kwargs):
        request.env["ir.http"]._check_request_recaptcha_token(
            "appointment_form_submission"
        )
        _debug.lifecycle("form_submit_recaptcha_passed")
        return super().appointment_form_submit(*args, **kwargs)

    def _get_appointment_type_resource_selection_view(
        self, appointment_type, page_values
    ):
        return request.render(
            "website_appointment.appointment_select_operator",
            {
                "appointment_type": appointment_type,
                "available_appointments": page_values["available_appointments"],
                "main_object": appointment_type,
                "users_possible": page_values["users_possible"],
                "resources_possible": page_values["resources_possible"],
            },
        )

    def _get_appointment_type_page_view(
        self, appointment_type, page_values, state=False, **kwargs
    ):
        skip_resource_selection = (
            kwargs.get("skip_resource_selection")
            or not appointment_type.active
            or appointment_type.is_auto_assign
            or appointment_type.is_date_first
        )
        operator_selection = (
            not skip_resource_selection
            and appointment_type.schedule_based_on == "users"
            and not page_values["user_selected"]
            and len(page_values["users_possible"]) > 1
        )
        resource_selection = (
            not skip_resource_selection
            and appointment_type.schedule_based_on == "resources"
            and not page_values["resource_selected"]
            and len(page_values["resources_possible"]) > 1
        )
        if operator_selection or resource_selection:
            _debug.logic(
                "selection_page",
                appointment_type=appointment_type,
                schedule_based_on=appointment_type.schedule_based_on,
                users_possible=len(page_values["users_possible"]),
                resources_possible=len(page_values["resources_possible"]),
            )
            return self._get_appointment_type_resource_selection_view(
                appointment_type, page_values
            )
        _debug.logic(
            "slots_page",
            appointment_type=appointment_type,
            skipped_selection=bool(skip_resource_selection),
            auto_assign=appointment_type.is_auto_assign,
            date_first=appointment_type.is_date_first,
        )
        return super()._get_appointment_type_page_view(
            appointment_type, page_values, state, **kwargs
        )

    def _prepare_appointment_type_page_values(
        self,
        appointment_type,
        staff_user_id=False,
        resource_selected_id=False,
        skip_resource_selection=False,
        **kwargs,
    ):
        values = super()._prepare_appointment_type_page_values(
            appointment_type, staff_user_id, resource_selected_id, **kwargs
        )
        values["skip_resource_selection"] = skip_resource_selection
        if skip_resource_selection:
            values["user_selected"] = values["user_default"] = request.env["res.users"]
            values["resource_selected"] = values["resource_default"] = request.env[
                "resource.resource"
            ]
        else:
            resource_or_user_selected = (
                values["user_selected"]
                if appointment_type.schedule_based_on == "users"
                else values["resource_selected"]
            )
            values["hide_select_dropdown"] = values["hide_select_dropdown"] or (
                resource_or_user_selected
                and not (
                    appointment_type.is_date_first
                    and not appointment_type.is_auto_assign
                )
            )
            _debug.logic(
                "page_values",
                appointment_type=appointment_type,
                selected=resource_or_user_selected,
                hide_select_dropdown=values["hide_select_dropdown"],
            )
        return values

    def _prepare_appointments_cards_data(self, page, appointment_types, **kwargs):
        APPOINTMENTS_PER_PAGE = 12
        website = request.website
        appointment_count = len(appointment_types)

        pager = website.pager(
            url="/appointment",
            url_args=kwargs,
            total=appointment_count,
            page=page,
            step=APPOINTMENTS_PER_PAGE,
            scope=5,
        )
        appointment_types = appointment_types.sorted("is_published", reverse=True)[
            pager["offset"] : pager["offset"] + APPOINTMENTS_PER_PAGE
        ]

        _debug.pipeline(
            "cards_page",
            total=appointment_count,
            offset=pager["offset"],
            shown=len(appointment_types),
        )
        return {
            "appointment_types": appointment_types,
            "current_search": kwargs.get("search"),
            "pager": pager,
            "filter_appointment_type_ids": kwargs.get("filter_appointment_type_ids"),
            "filter_staff_user_ids": kwargs.get("filter_staff_user_ids"),
            "invite_token": kwargs.get("invite_token"),
            "search_count": appointment_count,
        }

    def _get_allowed_companies(self, organizer):
        companies = super()._get_allowed_companies(organizer)
        website_company = (
            request.website.company_id
            if request.website
            else request.env["res.company"]
        )
        _debug.logic(
            "allowed_companies",
            organizer=organizer,
            allowed=companies,
            website_company=website_company,
            narrowed=website_company in companies,
        )
        return website_company if website_company in companies else companies

    def _get_customer_partner(self):
        partner = super()._get_customer_partner()
        if not partner:
            visitor = request.env["website.visitor"]._get_visitor_from_request()
            if visitor.partner_id:
                partner = visitor.partner_id
                _debug.logic(
                    "customer_partner_from_visitor", visitor=visitor, partner=partner
                )
            elif visitor and request.env.user._is_public():
                partner = (
                    self.env["calendar.event"]
                    .sudo()
                    .search(
                        [
                            ("visitor_id", "=", visitor.id),
                            ("appointment_booker_id", "!=", False),
                        ],
                        order="id desc",
                        limit=1,
                    )
                    .appointment_booker_id
                )
                _debug.logic(
                    "customer_partner_from_booking", visitor=visitor, partner=partner
                )
        return partner

    @staticmethod
    def _get_customer_country():
        country = AppointmentController._get_customer_country()
        if not country:
            visitor = request.env["website.visitor"]._get_visitor_from_request()
            country = visitor.country_id
        return country

    @classmethod
    def _appointments_base_domain(
        cls,
        filter_appointment_type_ids,
        search=False,
        invite_token=False,
        additional_domain=None,
        filter_countries=False,
    ):
        domain = super()._appointments_base_domain(
            filter_appointment_type_ids,
            search,
            invite_token,
            additional_domain,
            filter_countries,
        )
        domain &= request.website.website_domain()
        return domain
