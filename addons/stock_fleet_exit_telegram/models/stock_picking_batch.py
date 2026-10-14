from odoo import api, models
from odoo.fields import Domain

from .telegram_handler import AUTHORISE, REFUSE
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import operating
from odoo.addons.telegram.tools.dispatch import translation_env


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    @api.model
    def _get_exit_bots(self, company):
        return operating(self.env["telegram.bot"]).search(
            self.env["telegram.bot"]._get_delivering_domain()
            & Domain("command_ids.name", "=", "/rutas")
            & Domain("company_ids", "in", company.id)
        )

    def _send_exit_message(self, users, render, markup=None) -> int:
        bots = self._get_exit_bots(self.company_id or self.env.company)
        if not bots:
            return 0
        sent = 0
        for user in users:
            chat = self.env["telegram.chat"]._for_user(user, bots)[:1]
            if not chat:
                continue
            env = translation_env(chat.bot_id, chat)
            chat.bot_id._queue_text(
                chat,
                render(self.with_env(env)),
                reply_markup=markup(self.with_env(env)) if markup else None,
            )
            sent += 1
        return sent

    @api.model
    def _notify_authorisers(self, render, company) -> int:
        users = self._get_exit_authorisers(company)
        return self.browse()._send_exit_message(users, render)

    def action_exit_request(self):
        self.check_singleton()
        asked = self._get_exit_authorisers(self.company_id)
        return super(
            StockPickingBatch,
            self.with_context(mail_telegram_skip_partner_ids=asked.partner_id.ids),
        ).action_exit_request()

    def _get_exit_request_text(self) -> str:
        self.check_singleton()
        passengers = ", ".join(self.passenger_ids.mapped("name")) or "—"
        return self.env._(
            "🚗 %(route)s asks to leave\nVehicle: %(vehicle)s\nDriver: "
            "%(driver)s\nPassengers: %(passengers)s\nActivities: %(activities)s\n"
            "Odometer: %(odometer)s"
        ) % {
            "route": tg.bold(self.name),
            "vehicle": tg.escape(self.vehicle_id.display_name),
            "driver": tg.escape(self.operator_id.name),
            "passengers": tg.escape(passengers),
            "activities": tg.escape(self.exit_activity_summary or "—"),
            "odometer": tg.escape(f"{self.odometer_departure:g}"),
        }

    def _notify_exit_requested(self, activities) -> None:
        super()._notify_exit_requested(activities)
        self._send_exit_message(
            activities.user_id,
            lambda route: route._get_exit_request_text(),
            lambda route: kb.confirm_cancel(
                route.env._("Authorise"),
                f"{AUTHORISE}{route.id}",
                route.env._("Refuse"),
                f"{REFUSE}{route.id}",
            ),
        )

    def _notify_exit_decided(self, authorised, others) -> None:
        super()._notify_exit_decided(authorised, others)
        decider = self.env.user.name

        def render(route):
            names = {
                "route": tg.bold(route.name),
                "vehicle": tg.escape(route.vehicle_id.display_name),
                "user": tg.escape(decider),
            }
            if authorised:
                return (
                    route.env._(
                        "✅ %(route)s authorised by %(user)s: %(vehicle)s may leave."
                    )
                    % names
                )
            return route.env._("❌ %(route)s refused by %(user)s.") % names

        self._send_exit_message(
            (self.exit_requested_uid | self.operator_id.user_id | others)
            - self.env.user,
            render,
        )
