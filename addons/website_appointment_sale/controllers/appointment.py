from odoo.http import request
from odoo.tools.urls import keep_query

from odoo.addons.appointment_account_payment.controllers.appointment import (
    AppointmentAccountPayment,
)
from odoo.addons.portal.controllers.portal import CustomerPortal


class WebsiteAppointmentSale(AppointmentAccountPayment):
    def _redirect_to_payment(self, calendar_booking):
        order_sudo = request.cart or request.website._create_cart()

        tz = (
            request.session.get("timezone")
            or request.env.context.get("tz")
            or calendar_booking.appointment_type_id.appointment_tz
        )

        cart_values = order_sudo._cart_add(
            product_id=calendar_booking.appointment_type_id.product_id.id,
            quantity=calendar_booking.asked_capacity,
            calendar_booking_id=calendar_booking.id,
            calendar_booking_tz=tz,
        )
        if cart_values["quantity"] == calendar_booking.asked_capacity:
            if order_sudo._is_anonymous_cart():
                partner_values = {
                    "name": calendar_booking.name,
                    "email": calendar_booking.partner_id.email,
                    "phone": calendar_booking.partner_id.phone_ids._primary().number,
                }
                booked_by_partner, feedback_dict = (
                    CustomerPortal()._create_or_update_address(
                        request.env["res.partner"].sudo(),
                        order_sudo=order_sudo,
                        verify_address_values=False,
                        **partner_values,
                    )
                )
                if not feedback_dict.get("invalid_fields"):
                    order_sudo._update_address(booked_by_partner.id, ["partner_id"])
            return request.redirect("/shop/checkout?try_skip_step=true")

        appointment_type = calendar_booking.appointment_type_id
        calendar_booking.sudo().unlink()
        error_state = (
            "failed-staff-user"
            if appointment_type.schedule_based_on == "users"
            else "failed-resource"
        )
        return request.redirect(
            "/appointment/%s?%s"
            % (appointment_type.id, keep_query("*", state=error_state))
        )
