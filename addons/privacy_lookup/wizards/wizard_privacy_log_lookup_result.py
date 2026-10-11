from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError


class WizardPrivacyLogLookupResult(models.TransientModel):
    _name = "wizard.privacy.log.lookup.result"
    _description = "Privacy Lookup Wizard Line"
    _transient_max_count = 0
    _transient_max_hours = 24

    @api.model
    def _selection_target_model(self):
        return [
            (model.model, model.name)
            for model in self.env["ir.model"].sudo().search([])
        ]

    wizard_id = fields.Many2one(comodel_name="wizard.privacy.log.lookup")
    res_id = fields.Integer(
        string="Resource ID",
        required=True,
    )
    res_name = fields.Char(
        string="Resource name",
        compute="_compute_res_name",
        store=True,
    )
    res_model_id = fields.Many2one(
        comodel_name="ir.model",
        string="Related Document Model",
        ondelete="cascade",
    )
    res_model = fields.Char(
        related="res_model_id.model",
        string="Document Model",
        readonly=True,
    )
    resource_ref = fields.Reference(
        selection="_selection_target_model",
        string="Record",
        compute="_compute_resource_ref",
        inverse="_inverse_resource_ref",
    )
    has_active = fields.Boolean(
        compute="_compute_has_active",
        store=True,
    )
    is_active = fields.Boolean()
    is_unlinked = fields.Boolean()
    execution_details = fields.Char(default="")

    @api.depends("res_model", "res_id", "is_unlinked")
    def _compute_resource_ref(self) -> None:
        for line in self:
            if line.res_model and line.res_model in self.env and not line.is_unlinked:
                try:
                    self.env[line.res_model].browse(line.res_id).check_access("read")
                    line.resource_ref = "%s,%s" % (line.res_model, line.res_id or 0)
                except AccessError, MissingError, KeyError:
                    line.resource_ref = None
            else:
                line.resource_ref = None

    @api.depends("res_model_id")
    def _compute_has_active(self) -> None:
        for line in self:
            if not line.res_model_id:
                line.has_active = False
                continue
            line.has_active = "active" in self.env[line.res_model]

    @api.depends("res_model", "res_id")
    def _compute_res_name(self) -> None:
        for line in self:
            if not line.res_id or not line.res_model:
                continue
            record = self.env[line.res_model].sudo().browse(line.res_id)
            if not record.exists():
                continue
            name = record.display_name
            line.res_name = name or f"{line.res_model_id.name}/{line.res_id}"

    def _inverse_resource_ref(self) -> None:
        for line in self:
            if line.resource_ref:
                line.res_id = line.resource_ref.id

    @api.onchange("is_active")
    def _onchange_is_active(self) -> None:
        for line in self:
            if not line.res_model_id or not line.res_id:
                continue
            action = (
                self.env._("Unarchived") if line.is_active else self.env._("Archived")
            )
            line.execution_details = "%s %s #%s" % (
                action,
                line.res_model_id.name,
                line.res_id,
            )
            self.env[line.res_model].sudo().browse(line.res_id).write(
                {"active": line.is_active}
            )

    def action_unlink(self):
        self.check_singleton()
        if self.is_unlinked:
            raise UserError(self.env._("The record is already unlinked."))
        self.env[self.res_model].sudo().browse(self.res_id).unlink()
        self.execution_details = "%s %s #%s" % (
            self.env._("Deleted"),
            self.res_model_id.name,
            self.res_id,
        )
        self.is_unlinked = True

    def action_archive_all(self) -> None:
        for line in self:
            if not line.has_active or not line.is_active:
                continue
            line.is_active = False
            line._onchange_is_active()

    def action_unlink_all(self) -> None:
        for line in self:
            if line.is_unlinked:
                continue
            line.action_unlink()

    def action_view_record(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_id": self.res_id,
            "res_model": self.res_model,
        }
