from odoo import api, fields, models


class SmsTemplate(models.Model):

    _name = "sms.template"
    _inherit = ["mixin.mail.render", "mixin.template.reset"]
    _description = "SMS Templates"

    _unrestricted_rendering = True
    _dynamic_field_names = frozenset({"body", "lang"})

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if "model_id" in fields and not res.get("model_id") and res.get("model"):
            res["model_id"] = self.env["ir.model"]._get(res["model"]).id
        return res

    name = fields.Char(translate=True)
    model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Applies to",
        required=True,
        domain=["&", ("is_mail_thread_sms", "=", True), ("transient", "=", False)],
        ondelete="cascade",
        help="The type of document this template can be used with",
    )
    model = fields.Char(
        related="model_id.model",
        string="Related Document Model",
        readonly=True,
    )
    body = fields.Char(
        translate=True,
        required=True,
    )
    sidebar_action_id = fields.Many2one(
        comodel_name="ir.actions.act_window",
        string="Sidebar action",
        copy=False,
        readonly=True,
        help="Sidebar action to make this template available on records "
        "of the related document model",
    )

    @api.depends("model")
    def _compute_render_model(self) -> None:
        for template in self:
            template.render_model = template.model


    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [
            dict(vals, name=self.env._("%s (copy)", template.name))
            for template, vals in zip(self, vals_list, strict=True)
        ]

    def copy_translations(self, new, excluded=()) -> None:
        super().copy_translations(new, excluded=(*excluded, "name"))
        self._copy_translations_of_renamed_field(
            new, "name", lambda record, term: record.env._("%s (copy)", term)
        )

    def unlink(self):
        self.sudo().mapped("sidebar_action_id").unlink()
        return super().unlink()

    def _get_reset_preserved_fields(self):
        return super()._get_reset_preserved_fields() | {"sidebar_action_id"}

    def action_create_sidebar_action(self) -> None:
        ActWindow = self.env["ir.actions.act_window"]
        view = self.env.ref("sms.sms_composer_view_form")

        for template in self:
            button_name = self.env._("Send SMS (%s)", template.name)
            action = ActWindow.create(
                {
                    "name": button_name,
                    "type": "ir.actions.act_window",
                    "res_model": "wizard.sms.sms.send",
                    "context": "{'default_template_id' : %d, 'sms_composition_mode': 'guess', 'default_res_ids': active_ids, 'default_res_id': active_id}"
                    % (template.id),
                    "view_mode": "form",
                    "view_id": view.id,
                    "target": "new",
                    "binding_model_id": template.model_id.id,
                }
            )
            template.write({"sidebar_action_id": action.id})

    def action_unlink_sidebar_action(self) -> None:
        for template in self:
            if template.sidebar_action_id:
                template.sidebar_action_id.unlink()
