from collections import Counter

from odoo import Command, api, fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountMoveSendBatch(models.TransientModel):
    _name = "wizard.account.move.send.batch"
    _inherit = ["mixin.account.move.send"]
    _description = "Account Move Send Batch Wizard"

    move_ids = fields.Many2many(
        comodel_name="account.move",
        required=True,
    )
    summary_data = fields.Json(compute="_compute_summary_data")
    alerts = fields.Json(compute="_compute_summary_data")

    @api.model
    @_debug.perf.timed
    def default_get(self, fields):
        _debug.lifecycle("default_get", records=self)
        results = super().default_get(fields)
        if "move_ids" in fields and "move_ids" not in results:
            move_ids = self.env.context.get("active_ids", [])
            results["move_ids"] = [Command.set(move_ids)]
        return results

    @api.model
    def _get_preview_sending_settings(self, move) -> dict:
        sending_methods = self._get_default_sending_methods(move)
        settings = {
            "sending_methods": sending_methods,
            "extra_edis": self._get_default_extra_edis(move),
            "invoice_edi_format": self._get_default_invoice_edi_format(
                move, sending_methods=sending_methods
            ),
        }
        if "email" in sending_methods:
            mail_template = self._get_default_mail_template_id(move)
            settings["mail_partner_ids"] = self._get_default_mail_partner_ids(
                move,
                mail_template,
                self._get_default_mail_lang(move, mail_template),
                no_create=True,
            )
        return settings

    @api.depends("move_ids")
    @_debug.perf.timed
    def _compute_summary_data(self) -> None:
        extra_edis = self._get_all_extra_edis()
        sending_methods = dict(
            self.env["res.partner"]
            ._fields["invoice_sending_method"]
            ._description_selection(self.env)
        )
        sending_methods["manual"] = self.env._("Manually")

        for wizard in self:
            moves = wizard.move_ids._origin
            moves_data = {
                move: self._get_preview_sending_settings(move) for move in moves
            }
            edi_counter = Counter()
            sending_method_counter = Counter()

            for move, move_data in moves_data.items():
                edi_counter += Counter(list(move_data["extra_edis"]))
                sending_method_counter += Counter(
                    [
                        sending_method
                        for sending_method in move_data["sending_methods"]
                        if self._is_applicable_to_move(
                            sending_method, move, **move_data
                        )
                    ]
                )

            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "send_summary_counted",
                    move=moves,
                    edis=dict(edi_counter),
                    sending_methods=dict(sending_method_counter),
                )
            summary_data = {}
            for edi, edi_count in edi_counter.items():
                summary_data[edi] = {
                    "count": edi_count,
                    "label": self.env._("by %s", extra_edis[edi]["label"]),
                }
            for sending_method, sending_method_count in sending_method_counter.items():
                summary_data[sending_method] = {
                    "count": sending_method_count,
                    "label": sending_methods[sending_method],
                }

            wizard.summary_data = summary_data
            wizard.alerts = self._get_alerts(moves, moves_data)

    @api.constrains("move_ids")
    @_debug.perf.timed
    def _check_move_ids_constraints(self) -> None:
        for wizard in self:
            self._check_move_constraints(wizard.move_ids)

    @_debug.perf.timed
    def action_send_and_print(self, force_synchronous=False, allow_fallback_pdf=False):
        _debug.lifecycle("action_send_and_print", records=self)
        self.check_singleton()
        if self.alerts:
            self._raise_danger_alerts(self.alerts)
        _debug.logic(
            "batch_send_mode_chosen",
            move=self.move_ids,
            synchronous=force_synchronous,
            allow_fallback_pdf=allow_fallback_pdf,
        )
        if force_synchronous:
            self.env["mixin.account.move.send"]._generate_and_send_invoices(
                self.move_ids, allow_fallback_pdf=allow_fallback_pdf
            )
            return None

        account_move_send_cron = self.env.ref("account.ir_cron_account_move_send")
        if not account_move_send_cron.sudo().active:
            if self.env.user.has_group("base.group_system"):
                raise RedirectWarning(
                    self.env._(
                        "Batch invoice sending is unavailable. Please, activate the cron to enable batch sending of invoices."
                    ),
                    {
                        "views": [(False, "form")],
                        "res_model": "ir.cron",
                        "type": "ir.actions.act_window",
                        "res_id": account_move_send_cron.id,
                        "target": "current",
                    },
                    self.env._("Go to cron configuration"),
                )
            raise UserError(
                self.env._(
                    "Batch invoice sending is unavailable. Please, contact your system administrator to activate the cron to enable batch sending of invoices."
                )
            )

        self.move_ids._as_sending_queue().sending_data = {
            "author_user_id": self.env.user.id
        }
        _debug.pipeline(
            "batch_send_queued",
            move=self.move_ids,
            cron=account_move_send_cron,
        )
        account_move_send_cron._trigger()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "info",
                "title": self.env._("Sending invoices"),
                "message": self.env._("Invoices are being sent in the background."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
