from typing import Literal, TypedDict

from werkzeug.exceptions import Forbidden

from odoo import Command, fields, http
from odoo.exceptions import ValidationError
from odoo.http import request, route


class AppointmentInvitationData(TypedDict):
    appointment_type_id: int
    invite_url: str
    view_id: int | Literal[False]


class AppointmentCalendarView(http.Controller):
    @route("/appointment/appointment_type/create_custom", type="jsonrpc", auth="user")
    def appointment_type_create_custom(self, slots, context=None):
        if not slots:
            raise ValidationError(
                request.env._(
                    "A list of slots information is needed to create a custom appointment type"
                )
            )
        if not request.env.user._is_internal():
            raise Forbidden
        if context:
            request.update_context(**context)
        AppointmentType = request.env["appointment.type"]
        appointment_type = AppointmentType.with_context(
            AppointmentType._prepare_clean_appointment_context()
        ).create(
            {
                "name": request.env._(
                    "%(name)s - My availabilities", name=request.env.user.name
                ),
                "category": "custom",
                "slot_ids": [
                    Command.create(
                        {
                            "start_datetime": fields.Datetime.from_string(
                                slot.get("start")
                            ),
                            "end_datetime": fields.Datetime.from_string(
                                slot.get("end")
                            ),
                            "allday": slot.get("allday"),
                            "slot_type": "unique",
                        }
                    )
                    for slot in slots
                ],
                "staff_user_ids": request.env.user.ids,
            }
        )

        return self._acquire_staff_invitation_data(appointment_type)

    @route("/appointment/appointment_type/update_custom", type="jsonrpc", auth="user")
    def appointment_type_update_custom(self, appointment_type_id, slots):
        if not appointment_type_id or not request.env.user._is_internal():
            raise Forbidden
        if not slots:
            raise ValidationError(
                request.env._(
                    "A list of slots information is needed to update this custom appointment type"
                )
            )

        appointment_type = request.env["appointment.type"].browse(
            int(appointment_type_id)
        )
        if (
            appointment_type.category != "custom"
            or appointment_type.create_uid != request.env.user
        ):
            raise Forbidden

        appointment_type.write(
            {
                "slot_ids": [Command.clear()]
                + [
                    Command.create(
                        {
                            "allday": slot.get("allday"),
                            "end_datetime": fields.Datetime.from_string(
                                slot.get("end")
                            ),
                            "slot_type": "unique",
                            "start_datetime": fields.Datetime.from_string(
                                slot.get("start")
                            ),
                        }
                    )
                    for slot in slots
                ],
            }
        )
        return True

    @route("/appointment/appointment_type/get_book_url", type="jsonrpc", auth="user")
    def appointment_get_book_url(self, appointment_type_id, context=None):
        if context:
            request.update_context(**context)
        appointment_type = (
            request.env["appointment.type"].browse(int(appointment_type_id)).exists()
        )
        if not appointment_type:
            raise ValidationError(
                request.env._("An appointment type is needed to get the link.")
            )
        return self._acquire_staff_invitation_data(appointment_type)

    @route(
        "/appointment/appointment_type/get_staff_user_appointment_types",
        type="jsonrpc",
        auth="user",
    )
    def appointment_get_user_appointment_types(self):
        appointment_types_info = []
        domain = [
            ("schedule_based_on", "=", "users"),
            ("staff_user_ids", "in", [request.env.user.id]),
            ("category", "in", ["punctual", "recurring"]),
        ]
        appointment_types_info = request.env["appointment.type"].search_read(
            domain, ["name", "category"]
        )
        return {
            "appointment_types_info": appointment_types_info,
        }

    @route(
        "/appointment/appointment_type/search_create_anytime",
        type="jsonrpc",
        auth="user",
    )
    def appointment_type_search_create_anytime(self, context=None):
        return self._appointment_type_search_create_anytime(context=context)

    @classmethod
    def _appointment_type_search_create_anytime(cls, context=None, user=None):
        user = user or request.env.user
        if not user._is_internal():
            raise Forbidden
        AppointmentType = request.env["appointment.type"].sudo()
        appointment_type = AppointmentType.search(
            [("category", "=", "anytime"), ("staff_user_ids", "in", user.ids)]
        )
        if context:
            request.update_context(**context)
        if not appointment_type:
            appt_type_vals = cls._prepare_appointment_type_anytime_values(user)
            appointment_type = AppointmentType.with_context(
                AppointmentType._prepare_clean_appointment_context()
            ).create(appt_type_vals)
        return cls._acquire_staff_invitation_data(appointment_type)

    @classmethod
    def _prepare_appointment_type_anytime_values(cls, user):
        return {
            "name": request.env._("Meeting with %(name)s", name=user.name),
            "max_schedule_days": 15,
            "category": "anytime",
            "staff_user_ids": [user.id],
        }

    @classmethod
    def _acquire_staff_invitation_data(
        cls, appointment_type, user=None
    ) -> AppointmentInvitationData:
        user = user or request.env.user
        appointment_invitation_domain = cls._get_domain_staff_user_appointment_invite(
            appointment_type, user
        )
        appointment_invitation = (
            request.env["appointment.invite"]
            .sudo()
            .search(appointment_invitation_domain, limit=1)
        )
        if not appointment_invitation:
            invitation_values = {
                "appointment_type_ids": appointment_type.ids,
                "resources_choice": "current_user",
                "staff_user_ids": user.ids,
                "short_code": request.env["appointment.invite"]._get_unique_short_code(
                    appointment_type=appointment_type
                ),
            }
            if appointment_type.category == "custom":
                invitation_values.update(
                    {
                        "resources_choice": "all_assigned_resources",
                        "staff_user_ids": False,
                    }
                )
            appointment_invitation = (
                request.env["appointment.invite"]
                .sudo()
                .with_context(
                    request.env["appointment.type"]._prepare_clean_appointment_context()
                )
                .create(invitation_values)
            )

        dialog_form_view = request.env.ref(
            "calendar.appointment_type_view_form_custom_share",
            raise_if_not_found=False,
        )
        return {
            "appointment_type_id": appointment_type.id,
            "invite_url": appointment_invitation.book_url,
            "view_id": dialog_form_view.id if dialog_form_view else False,
        }

    @classmethod
    def _get_domain_staff_user_appointment_invite(cls, appointment_type, user):
        if appointment_type.category == "custom":
            return [
                ("appointment_type_ids", "=", appointment_type.id),
                ("create_uid", "=", user.id),
            ]
        return [
            ("appointment_type_ids", "=", appointment_type.id),
            ("staff_user_ids", "=", user.id),
        ]
