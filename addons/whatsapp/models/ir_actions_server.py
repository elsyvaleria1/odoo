from odoo import api, fields, models


class IrActionsServer(models.Model):
    """Add WhatsApp option in server actions."""

    _inherit = "ir.actions.server"

    # force insert before followers option
    state = fields.Selection(
        selection_add=[
            ("whatsapp", "Send WhatsApp"),
            ("followers",),
        ],
        ondelete={"whatsapp": "cascade"},
    )
    # WhatsApp
    wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="WhatsApp Template",
        compute="_compute_wa_template_id",
        store=True,
        readonly=False,
        domain="[('model_id', '=', model_id), ('status', '=', 'approved')]",
        ondelete="restrict",
    )

    @api.model
    def _get_states_needing_a_live_record(self):
        return super()._get_states_needing_a_live_record() | {"whatsapp"}

    def _is_batchable(self) -> bool:
        self.check_singleton()
        return bool(self.state == "whatsapp" or super()._is_batchable())

    def _get_fields_name_depends(self):
        return [*super()._get_fields_name_depends(), "wa_template_id"]

    def _prepare_automated_name(self):
        self.check_singleton()
        if self.state == "whatsapp" and self.wa_template_id:
            return self.env._(
                "Send %(template_name)s", template_name=self.wa_template_id.name
            )
        return super()._prepare_automated_name()

    @api.depends("model_id", "state")
    def _compute_wa_template_id(self) -> None:
        to_reset = self.filtered(
            lambda act: (
                act.state != "whatsapp" or (act.model_id != act.wa_template_id.model_id)
            )
        )
        if to_reset:
            to_reset.wa_template_id = False

    def _run_action_whatsapp_multi(self, eval_context=None) -> bool:
        records = eval_context.get("records") or eval_context.get("record")
        if records:
            records -= self._get_recompute_pending(records)
        if not self.wa_template_id or not records:
            return False

        self.env["wizard.whatsapp.message.send"].create(
            {
                "res_ids": records.ids,
                "res_model": records._name,
                "wa_template_id": self.wa_template_id.id,
            }
        )._send_whatsapp_template(force_send_by_cron=True)

        return False
