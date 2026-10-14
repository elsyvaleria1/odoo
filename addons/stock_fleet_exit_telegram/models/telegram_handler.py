import logging
import re
from datetime import timedelta

from odoo import Command, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError, ValidationError
from odoo.tools.translate import LazyTranslate

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import TelegramCommand, log_command_execution

_logger = logging.getLogger(__name__)
_lt = LazyTranslate(__name__)

ROUTE = "rut:"
VEHICLE = f"{ROUTE}v:"
GROUP = f"{ROUTE}g:"
ACTIVITY = f"{ROUTE}t:"
ACTIVITIES_DONE = f"{ROUTE}td"
PASSENGER_ADD = f"{ROUTE}pa"
PASSENGER_NONE = f"{ROUTE}pn"
PASSENGER = f"{ROUTE}pe:"
USE_GPS = f"{ROUTE}gps"
CONFIRM = f"{ROUTE}ok"
ABORT = f"{ROUTE}no"
WITHDRAW = f"{ROUTE}x:"
OUT_ACTIVITY = f"{ROUTE}ma"
OUT_PASSENGER = f"{ROUTE}mp"
OUT_RETURN = f"{ROUTE}mr"
OUT_STAY = f"{ROUTE}ms"
CREW_ADD = f"{ROUTE}ca"
CREW_DONE = f"{ROUTE}cn"
PLACE = f"{ROUTE}pl:"
AUTHORISE = f"{ROUTE}A:"
REFUSE = f"{ROUTE}R:"
LIST_LIMIT = 8
NUMBER = re.compile(r"\d[\d.,\s]*")
TEXT_STEPS = ("vehicle", "passenger", "odometer", "place")


def parse_odometer(text) -> float | None:
    match = NUMBER.search(text or "")
    if not match:
        return None
    digits = re.sub(r"\s", "", match.group()).rstrip(".,")
    if "," in digits and "." in digits:
        digits = digits.replace(",", "")
    elif "," in digits:
        whole, _sep, decimals = digits.rpartition(",")
        digits = (
            digits.replace(",", "") if len(decimals) == 3 else f"{whole}.{decimals}"
        )
    elif digits.count(".") > 1 or (
        "." in digits and len(digits.rpartition(".")[2]) == 3
    ):
        digits = digits.replace(".", "")
    try:
        return float(digits)
    except ValueError:
        return None


class TelegramHandlerFleetExit(models.AbstractModel):
    _name = "telegram.handler.stock_fleet_exit"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Vehicle Routes"
    _telegram_flow_ttl = timedelta(hours=12)

    def _telegram_commands(self) -> dict:
        return {
            "/rutas": TelegramCommand(
                "_handle_route_command",
                "internal",
                starts_flow=True,
                access=("stock.picking.batch", "create"),
                description=_lt(
                    "Ask for a vehicle route, or tell what happens on yours"
                ),
            ),
        }

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        self._send(
            bot,
            chat,
            self._tr(bot, chat)._(
                "Only whoever drives the vehicles registers their routes here; ask "
                "an administrator for inventory rights."
            ),
        )

    def _telegram_callback_prefixes(self):
        return (ROUTE,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("vehicle routes")

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._offers_command(bot, chat, "/rutas", partner, internal_user):
            return []
        tr = self._tr(bot, chat)
        return [
            (
                tr._("Vehicles"),
                [
                    tr._(
                        "%(command)s - Ask for a route: the vehicle, what it goes "
                        "to do, who rides along and its odometer; it leaves once it "
                        "is authorised. Out, the same command adds an activity or a "
                        "passenger, and registers the return or where the vehicle "
                        "stays."
                    )
                    % {"command": tg.bold("/rutas")}
                ],
            )
        ]

    def _send(self, bot, chat, text, markup=None) -> None:
        bot.send_message(chat.chat_id, text, reply_markup=markup)

    def _employee(self, user):
        return self.env["hr.employee"].search(
            [("user_id", "=", user.id), ("company_id", "in", user.company_ids.ids)],
            limit=1,
        )

    def _routes(self, user, lang=None):
        Batch = self.env["stock.picking.batch"].with_user(user)
        return Batch.with_context(lang=lang) if lang else Batch

    def _route_of(self, chat, user):
        return (
            self._routes(user).browse(self._flow_data(chat).get("route") or 0).exists()
        )

    def _names(self, route) -> dict:
        return {
            "route": tg.bold(route.name),
            "vehicle": tg.escape(route.vehicle_id.display_name),
            "activities": tg.escape(route.exit_activity_summary or "—"),
        }

    @log_command_execution
    def _handle_route_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr = self._tr(bot, chat)
        employee = self._employee(internal_user)
        if not employee:
            self._send(
                bot,
                chat,
                tr._(
                    "Your Odoo user is not linked to an employee, so I cannot "
                    "tell which driver you are. Ask administration to link it."
                ),
            )
            return
        Batch = self._routes(internal_user, tr.lang)
        mine = [
            ("is_fleet_exit", "=", True),
            ("operator_id", "=", employee.id),
            ("state", "!=", "cancel"),
            ("date_return", "=", False),
        ]
        out = Batch.search([*mine, ("date_departure", "!=", False)], limit=1)
        if out:
            self._flow_start(chat, "out", {"route": out.id})
            self._offer_out_menu(bot, chat, out)
            return
        waiting = Batch.search([*mine, ("exit_requested_uid", "!=", False)], limit=1)
        if waiting:
            self._send(
                bot,
                chat,
                tr._(
                    "%(route)s, %(vehicle)s for %(activities)s, is waiting to be "
                    "authorised. I tell you here as soon as it is."
                )
                % self._names(waiting),
                kb.single(tr._("Withdraw the request"), f"{WITHDRAW}{waiting.id}"),
            )
            return
        self._flow_start(chat, "vehicle", {"employee": employee.id})
        self._ask_vehicle(bot, chat, internal_user, employee)

    def _offer_out_menu(self, bot, chat, route) -> None:
        tr = self._tr(bot, chat)
        self._send(
            bot,
            chat,
            tr._(
                "You are out on %(route)s with %(vehicle)s: %(activities)s. What "
                "happened?"
            )
            % self._names(route),
            kb.keyboard(
                [
                    kb.button(tr._("Add an activity"), OUT_ACTIVITY),
                    kb.button(tr._("Add a passenger"), OUT_PASSENGER),
                ],
                [kb.button(tr._("Back at the warehouse"), OUT_RETURN)],
                [kb.button(tr._("The vehicle stays here"), OUT_STAY)],
                [kb.button(tr._("Nothing"), ABORT)],
            ),
        )

    def _vehicles_of(self, user, employee):
        Vehicle = self.env["resource.asset.vehicle"].with_user(user)
        held = Vehicle.search([("operator_employee_id", "=", employee.id)])
        recent = (
            self._routes(user)
            .search(
                [("operator_id", "=", employee.id), ("vehicle_id", "!=", False)],
                limit=20,
            )
            .vehicle_id
        )
        return (held | recent)[:LIST_LIMIT]

    def _ask_vehicle(self, bot, chat, user, employee, vehicles=None) -> None:
        tr = self._tr(bot, chat)
        if vehicles is None:
            vehicles = self._vehicles_of(user, employee)
        self._send(
            bot,
            chat,
            tr._("Which vehicle leaves? Choose it, or type part of its plate or name.")
            if vehicles
            else tr._("Which vehicle leaves? Type part of its plate or name."),
            kb.record_list(
                vehicles,
                lambda vehicle: vehicle.display_name,
                lambda vehicle: f"{VEHICLE}{vehicle.id}",
                limit=LIST_LIMIT,
                width=56,
            )
            if vehicles
            else None,
        )

    def _activity_types(self, user):
        return (
            self.env["mail.activity.type"]
            .with_user(user)
            .search([("fleet_exit_role", "=", "destination")])
        )

    def _ask_activities(self, bot, chat, user, group=None) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        chosen = set(data.get("activities") or [])
        types = self._activity_types(user).with_context(lang=tr.lang)
        rows = []
        if group:
            shown = types.filtered(lambda t: t.fleet_exit_group == group)
        else:
            shown = types.filtered(lambda t: not t.fleet_exit_group)
            groups = []
            for activity_type in types.filtered("fleet_exit_group"):
                if activity_type.fleet_exit_group not in groups:
                    groups.append(activity_type.fleet_exit_group)
            rows += [
                [kb.button(f"{name} ›", f"{GROUP}{index}")]
                for index, name in enumerate(groups)
            ]
            chat._flow_update({"groups": groups})
        rows = [
            [
                kb.button(
                    f"✅ {activity_type.name}"
                    if activity_type.id in chosen
                    else activity_type.name,
                    f"{ACTIVITY}{activity_type.id}",
                )
            ]
            for activity_type in shown
        ] + rows
        single = self._flow_step(chat) == "add_activity"
        if not single:
            rows.append([kb.button(tr._("Done"), ACTIVITIES_DONE)])
        self._send(
            bot,
            chat,
            tr._("What does it go to do: %(group)s?") % {"group": tg.bold(group)}
            if group
            else tr._("What does it go to do? Choose one or more, then Done.")
            if not single
            else tr._("Which activity do you add?"),
            kb.keyboard(*rows),
        )

    def _ask_passenger(self, bot, chat) -> None:
        tr = self._tr(bot, chat)
        self._send(
            bot,
            chat,
            tr._("Does anybody ride along besides you?"),
            kb.confirm_cancel(
                tr._("Add a passenger"),
                PASSENGER_ADD,
                tr._("No passengers"),
                PASSENGER_NONE,
            ),
        )

    def _ask_odometer(self, bot, chat, user, vehicle, step) -> None:
        tr = self._tr(bot, chat)
        reading = self.env["stock.picking.batch"]._get_exit_gps_odometer(vehicle)
        chat._flow_advance(step, {**self._flow_data(chat), "gps": reading or 0})
        if reading:
            self._send(
                bot,
                chat,
                tr._(
                    "The GPS reads %(odometer)s on the odometer. Use it, or type "
                    "the one on the dashboard."
                )
                % {"odometer": tg.bold(f"{reading:g}")},
                kb.single(
                    tr._("Use %(odometer)s") % {"odometer": f"{reading:g}"}, USE_GPS
                ),
            )
            return
        self._send(
            bot,
            chat,
            tr._(
                "Type the odometer of the vehicle now, the number alone. You may "
                "send a photo of the dashboard with it."
            ),
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        step = self._flow_step(chat)
        if step not in TEXT_STEPS:
            return False
        chat._flow_advance()
        self._guarded(
            bot, chat, lambda: self._on_text(bot, chat, message, internal_user, step)
        )
        return True

    def _guarded(self, bot, chat, run) -> None:
        try:
            with self.env.cr.savepoint():
                run()
        except PG_RETRY_EXCEPTIONS:
            raise
        except (UserError, ValidationError) as error:
            self._send(bot, chat, tg.escape(str(error)))
        except Exception:
            _logger.exception("Failed to handle /rutas in chat %s", chat.id)
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._(
                    "Something went wrong; send /rutas again to start over."
                ),
            )

    def _on_text(self, bot, chat, message, user, step) -> None:
        tr = self._tr(bot, chat)
        text = (message.get("text") or message.get("caption") or "").strip()
        if step == "vehicle":
            self._on_vehicle_text(bot, chat, user, text)
        elif step == "passenger":
            self._on_passenger_text(bot, chat, user, text)
        elif step == "place":
            if text:
                self._close_here(bot, chat, user, text)
        else:
            photo = (message.get("photo") or [None])[-1]
            if photo:
                chat._flow_update({"photo": photo["file_id"]})
            reading = parse_odometer(text)
            if reading is None:
                self._send(
                    bot,
                    chat,
                    tr._("Photo kept. Now type the odometer, the number alone.")
                    if photo
                    else tr._(
                        "Type the odometer, the number alone, for example 45210."
                    ),
                )
                return
            self._on_odometer(bot, chat, user, reading)

    def _on_vehicle_text(self, bot, chat, user, text) -> None:
        tr = self._tr(bot, chat)
        employee = self.env["hr.employee"].browse(self._flow_data(chat)["employee"])
        if len(text) < 2:
            self._ask_vehicle(bot, chat, user, employee)
            return
        vehicles = (
            self.env["resource.asset.vehicle"]
            .with_user(user)
            .search(
                ["|", ("license_plate", "ilike", text), ("name", "ilike", text)],
                limit=LIST_LIMIT,
            )
        )
        if not vehicles:
            self._send(
                bot,
                chat,
                tr._("No vehicle matches %(text)s. Type another part of its plate.")
                % {"text": tg.escape(text)},
            )
            return
        self._ask_vehicle(bot, chat, user, employee, vehicles)

    def _on_passenger_text(self, bot, chat, user, text) -> None:
        tr = self._tr(bot, chat)
        employees = (
            self.env["hr.employee"]
            .with_user(user)
            .search([("name", "ilike", text)], limit=LIST_LIMIT)
        )
        if not employees:
            self._send(
                bot,
                chat,
                tr._("Nobody is called %(text)s. Type another part of the name.")
                % {"text": tg.escape(text)},
            )
            return
        self._send(
            bot,
            chat,
            tr._("Who is it?"),
            kb.record_list(
                employees,
                lambda employee: employee.name,
                lambda employee: f"{PASSENGER}{employee.id}",
                width=48,
            ),
        )

    def _on_odometer(self, bot, chat, user, reading) -> None:
        step = self._flow_data(chat).get("then")
        if step == "return":
            self._register_return(bot, chat, user, reading)
        elif step == "stay":
            self._ask_place(bot, chat, user, reading)
        else:
            chat._flow_advance(
                "confirm", {**self._flow_data(chat), "odometer": reading}
            )
            self._ask_confirmation(bot, chat, user)

    def _ask_confirmation(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        env = self.env(context={**self.env.context, "lang": tr.lang})
        vehicle = env["resource.asset.vehicle"].browse(data["vehicle"])
        types = env["mail.activity.type"].browse(data.get("activities") or [])
        passengers = env["hr.employee"].browse(data.get("passengers") or [])
        employee = env["hr.employee"].browse(data["employee"])
        self._send(
            bot,
            chat,
            tr._(
                "Vehicle: %(vehicle)s\nDriver: %(driver)s\nPassengers: "
                "%(passengers)s\nActivities: %(activities)s\nOdometer: "
                "%(odometer)s\n\nDo I ask for the authorisation?"
            )
            % {
                "vehicle": tg.escape(vehicle.display_name),
                "driver": tg.escape(employee.name),
                "passengers": tg.escape(", ".join(passengers.mapped("name")) or "—"),
                "activities": tg.escape(", ".join(t._get_exit_label() for t in types)),
                "odometer": tg.escape(f"{data['odometer']:g}"),
            },
            kb.confirm_cancel(tr._("Ask for it"), CONFIRM, tr._("Cancel"), ABORT),
        )

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        self._clear_keyboard(bot, chat, callback_query)
        self._guarded(
            bot, chat, lambda: self._on_choice(bot, chat, data, internal_user)
        )
        return True

    def _on_choice(self, bot, chat, data, user) -> None:
        tr = self._tr(bot, chat)
        if data.startswith((AUTHORISE, REFUSE)):
            self._decide(bot, chat, user, data)
            return
        if data == ABORT:
            self._flow_end(chat)
            self._send(bot, chat, tr._("Nothing registered."))
            return
        if data.startswith(WITHDRAW):
            self._withdraw(bot, chat, user, self._record_id(data, WITHDRAW))
            return
        step = self._flow_step(chat)
        handler = {
            "vehicle": self._on_vehicle_choice,
            "activities": self._on_activity_choice,
            "add_activity": self._on_activity_choice,
            "passengers": self._on_passenger_choice,
            "passenger": self._on_passenger_choice,
            "odometer": self._on_odometer_choice,
            "confirm": self._on_confirm_choice,
            "out": self._on_out_choice,
            "crew": self._on_crew_choice,
            "place": self._on_place_choice,
        }.get(step)
        if not handler or not handler(bot, chat, user, data):
            self._send(bot, chat, tr._("That button is no longer valid."))

    @staticmethod
    def _record_id(data, prefix) -> int:
        value = data.removeprefix(prefix)
        return int(value) if value.isdecimal() else 0

    def _on_vehicle_choice(self, bot, chat, user, data) -> bool:
        if not data.startswith(VEHICLE):
            return False
        vehicle = (
            self.env["resource.asset.vehicle"]
            .with_user(user)
            .browse(self._record_id(data, VEHICLE))
            .exists()
        )
        if not vehicle:
            return False
        chat._flow_advance(
            "activities", {**self._flow_data(chat), "vehicle": vehicle.id}
        )
        self._ask_activities(bot, chat, user)
        return True

    def _on_activity_choice(self, bot, chat, user, data) -> bool:
        flow = self._flow_data(chat)
        if data.startswith(GROUP):
            groups = flow.get("groups") or []
            index = self._record_id(data, GROUP)
            if index >= len(groups):
                return False
            self._ask_activities(bot, chat, user, groups[index])
            return True
        if data == ACTIVITIES_DONE and self._flow_step(chat) == "activities":
            if not flow.get("activities"):
                self._send(
                    bot,
                    chat,
                    self._tr(bot, chat)._("Choose at least one activity."),
                )
                self._ask_activities(bot, chat, user)
                return True
            chat._flow_advance("passengers")
            self._ask_passenger(bot, chat)
            return True
        if not data.startswith(ACTIVITY):
            return False
        activity_type = self._activity_types(user).filtered(
            lambda t: t.id == self._record_id(data, ACTIVITY)
        )
        if not activity_type:
            return False
        if self._flow_step(chat) == "add_activity":
            route = self._route_of(chat, user)
            route._add_exit_activity(activity_type, user=user)
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._("%(activity)s added to %(route)s.")
                % {
                    "activity": tg.bold(activity_type._get_exit_label()),
                    "route": tg.bold(route.name),
                },
            )
            self._flow_end(chat)
            return True
        chosen = list(flow.get("activities") or [])
        if activity_type.id in chosen:
            chosen.remove(activity_type.id)
        else:
            chosen.append(activity_type.id)
        chat._flow_update({"activities": chosen})
        self._ask_activities(bot, chat, user, activity_type.fleet_exit_group or None)
        return True

    def _on_passenger_choice(self, bot, chat, user, data) -> bool:
        tr = self._tr(bot, chat)
        flow = self._flow_data(chat)
        if data == PASSENGER_ADD:
            chat._flow_advance("passenger")
            self._send(bot, chat, tr._("Type part of the passenger's name."))
            return True
        if data == PASSENGER_NONE:
            vehicle = self.env["resource.asset.vehicle"].browse(flow["vehicle"])
            chat._flow_update({"then": "depart"})
            self._ask_odometer(bot, chat, user, vehicle, "odometer")
            return True
        if not data.startswith(PASSENGER):
            return False
        employee = (
            self.env["hr.employee"]
            .with_user(user)
            .browse(self._record_id(data, PASSENGER))
            .exists()
        )
        if not employee:
            return False
        route = self._route_of(chat, user)
        if route:
            route.passenger_ids |= employee
            if flow.get("then") in ("return", "stay"):
                self._ask_crew(bot, chat, route)
                return True
            self._flow_end(chat)
            self._send(
                bot,
                chat,
                tr._("%(passenger)s rides on %(route)s.")
                % {"passenger": tg.bold(employee.name), "route": tg.bold(route.name)},
            )
            return True
        passengers = list(flow.get("passengers") or [])
        if employee.id not in passengers:
            passengers.append(employee.id)
        chat._flow_advance("passengers", {**flow, "passengers": passengers})
        self._send(
            bot,
            chat,
            tr._("%(passenger)s rides along. Anybody else?")
            % {"passenger": tg.bold(employee.name)},
            kb.confirm_cancel(
                tr._("Add another"),
                PASSENGER_ADD,
                tr._("That is all"),
                PASSENGER_NONE,
            ),
        )
        return True

    def _on_odometer_choice(self, bot, chat, user, data) -> bool:
        reading = self._flow_data(chat).get("gps")
        if data != USE_GPS or not reading:
            return False
        self._on_odometer(bot, chat, user, reading)
        return True

    def _on_confirm_choice(self, bot, chat, user, data) -> bool:
        if data != CONFIRM:
            return False
        self._ask_route(bot, chat, user)
        return True

    def _route_type(self, user):
        return (
            self.env["stock.warehouse"]
            .with_user(user)
            .search(
                [
                    ("fleet_exit_log", "=", True),
                    ("fleet_exit_type_id", "!=", False),
                    ("company_id", "=", user.company_id.id),
                ],
                limit=1,
            )
            .fleet_exit_type_id
        )

    def _ask_route(self, bot, chat, user) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        self._flow_end(chat)
        route_type = self._route_type(user)
        if not route_type:
            self._send(
                bot,
                chat,
                tr._(
                    "No warehouse of yours keeps a vehicle exit log; ask "
                    "administration to tick it on the warehouse."
                ),
            )
            return
        Batch = self._routes(user, tr.lang)
        route = Batch.create(
            {
                "picking_type_id": route_type.id,
                "vehicle_id": data["vehicle"],
                "operator_id": data["employee"],
                "passenger_ids": [Command.set(data.get("passengers") or [])],
                "odometer_departure": data["odometer"],
            }
        )
        for activity_type in self.env["mail.activity.type"].browse(
            data.get("activities") or []
        ):
            route._add_exit_activity(activity_type, user=user)
        self._attach_photo(bot, route, data.get("photo"))
        route.action_exit_request()
        self._send(
            bot,
            chat,
            tr._(
                "%(route)s asked: %(vehicle)s for %(activities)s. I tell you here "
                "when it is authorised; do not leave before."
            )
            % self._names(route),
        )

    def _attach_photo(self, bot, route, file_id) -> None:
        if not file_id:
            return
        downloaded = bot.get_file(file_id)
        if not downloaded:
            return
        route.message_post(
            body=self.env._("Dashboard photo sent from Telegram."),
            attachments=[("odometer.jpg", downloaded["content"])],
            message_type="comment",
        )

    def _on_out_choice(self, bot, chat, user, data) -> bool:
        tr = self._tr(bot, chat)
        route = self._route_of(chat, user)
        if not route or route.date_return:
            return False
        if data == OUT_ACTIVITY:
            chat._flow_advance("add_activity")
            self._ask_activities(bot, chat, user)
            return True
        if data == OUT_PASSENGER:
            chat._flow_advance("passenger")
            self._send(bot, chat, tr._("Type part of the passenger's name."))
            return True
        if data in (OUT_RETURN, OUT_STAY):
            chat._flow_update({"then": "return" if data == OUT_RETURN else "stay"})
            self._ask_crew(bot, chat, route)
            return True
        return False

    def _ask_crew(self, bot, chat, route) -> None:
        tr = self._tr(bot, chat)
        chat._flow_advance("crew")
        self._send(
            bot,
            chat,
            tr._(
                "Before closing %(route)s: who rode with you on it?\n"
                "Registered: %(passengers)s"
            )
            % {
                "route": tg.bold(route.name),
                "passengers": tg.escape(
                    ", ".join(route.passenger_ids.mapped("name")) or "—"
                ),
            },
            kb.confirm_cancel(
                tr._("Add someone"),
                CREW_ADD,
                tr._("Nobody else"),
                CREW_DONE,
            ),
        )

    def _on_crew_choice(self, bot, chat, user, data) -> bool:
        route = self._route_of(chat, user)
        if not route or route.date_return:
            return False
        if data == CREW_ADD:
            chat._flow_advance("passenger")
            self._send(
                bot,
                chat,
                self._tr(bot, chat)._("Type part of the passenger's name."),
            )
            return True
        if data == CREW_DONE:
            self._ask_odometer(bot, chat, user, route.vehicle_id, "odometer")
            return True
        return False

    def _register_return(self, bot, chat, user, reading) -> None:
        tr = self._tr(bot, chat)
        route = self._route_of(chat, user).with_context(lang=tr.lang)
        try:
            with self.env.cr.savepoint():
                route.odometer_return = reading
                self._attach_photo(bot, route, self._flow_data(chat).get("photo"))
                route.action_return()
        except (UserError, ValidationError) as error:
            self._send(
                bot,
                chat,
                tr._("%(error)s\n\nType the odometer again.")
                % {"error": tg.escape(str(error))},
            )
            return
        self._flow_end(chat)
        self._send(
            bot,
            chat,
            tr._("Return of %(route)s registered: %(distance)s travelled. Thank you.")
            % {
                "route": tg.bold(route.name),
                "distance": tg.escape(
                    f"{route.trip_distance:g} {route.odometer_uom_id.name or ''}".strip()
                ),
            },
        )

    def _ask_place(self, bot, chat, user, reading) -> None:
        tr = self._tr(bot, chat)
        route = self._route_of(chat, user).with_context(lang=tr.lang)
        place = self.env["stock.picking.batch"]._get_exit_gps_place(route.vehicle_id)
        labels = [
            activity.activity_type_id._get_exit_label()
            for activity in route._get_exit_activities()
        ]
        options = [place] if place else []
        options += [label for label in labels if label not in options]
        chat._flow_advance(
            "place", {**self._flow_data(chat), "odometer": reading, "places": options}
        )
        self._send(
            bot,
            chat,
            tr._("Where does %(vehicle)s stay? Choose it, or type the place.")
            % {"vehicle": tg.escape(route.vehicle_id.display_name)},
            kb.keyboard(
                *(
                    [kb.button(kb.shorten(option, 48), f"{PLACE}{index}")]
                    for index, option in enumerate(options[:LIST_LIMIT])
                )
            )
            if options
            else None,
        )

    def _on_place_choice(self, bot, chat, user, data) -> bool:
        options = self._flow_data(chat).get("places") or []
        index = self._record_id(data, PLACE)
        if not data.startswith(PLACE) or index >= len(options):
            return False
        self._close_here(bot, chat, user, options[index])
        return True

    def _close_here(self, bot, chat, user, place) -> None:
        tr = self._tr(bot, chat)
        data = self._flow_data(chat)
        route = self._route_of(chat, user).with_context(lang=tr.lang)
        route.write({"odometer_return": data["odometer"], "exit_stay_location": place})
        self._attach_photo(bot, route, data.get("photo"))
        route.action_exit_close_here()
        self._flow_end(chat)
        self._send(
            bot,
            chat,
            tr._(
                "%(route)s closed: %(vehicle)s stays at %(place)s and goes back to "
                "%(holder)s. Thank you."
            )
            % {
                "route": tg.bold(route.name),
                "vehicle": tg.escape(route.vehicle_id.display_name),
                "place": tg.bold(place),
                "holder": tg.escape(route.vehicle_id.operator_employee_id.name or "—"),
            },
        )

    def _withdraw(self, bot, chat, user, route_id) -> None:
        tr = self._tr(bot, chat)
        route = (
            self._routes(user)
            .browse(route_id)
            .exists()
            .filtered(lambda r: r.exit_requested_uid == user and not r.date_departure)
        )
        if not route or route.state == "cancel":
            self._send(bot, chat, tr._("That request is no longer waiting."))
            return
        route._get_exit_activities(done=False).unlink()
        route.action_cancel()
        self._send(
            bot, chat, tr._("%(route)s withdrawn.") % {"route": tg.bold(route.name)}
        )

    def _decide(self, bot, chat, user, data) -> None:
        tr = self._tr(bot, chat)
        authorise = data.startswith(AUTHORISE)
        route = (
            self._routes(user, tr.lang)
            .browse(self._record_id(data, AUTHORISE if authorise else REFUSE))
            .exists()
        )
        if not route:
            self._send(bot, chat, tr._("That route no longer exists."))
            return
        if authorise:
            route.action_exit_authorise()
            self._send(
                bot,
                chat,
                tr._("%(route)s authorised: %(vehicle)s leaves now.")
                % self._names(route),
            )
            return
        route.action_exit_refuse()
        self._send(
            bot, chat, tr._("%(route)s refused.") % {"route": tg.bold(route.name)}
        )
