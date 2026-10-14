from typing import Self

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import get_diff

_debug = DebugLog(__name__)


class WizardIrActionsServerRestoreRevision(models.TransientModel):
    _name = "wizard.ir.actions.server.restore.revision"
    _description = "Server Action History Wizard"

    @api.model
    def _default_revision(self) -> Self:
        action_id = self.env["ir.actions.server"].browse(
            self.env.context.get("default_action_id", False)
        )
        return self.env["ir.actions.server.history"].search(
            [
                ("action_id", "=", action_id.id),
                ("code", "!=", action_id.code),
            ],
            limit=1,
        )

    action_id = fields.Many2one(comodel_name="ir.actions.server")
    code_diff = fields.Html(
        sanitize_tags=False,
        compute="_compute_code_diff",
    )
    current_code = fields.Text(
        related="action_id.code",
        readonly=True,
    )
    revision = fields.Many2one(
        comodel_name="ir.actions.server.history",
        default=lambda self: self._default_revision(),
        required=True,
        domain="[('action_id', '=', action_id), ('code', '!=', current_code)]",
    )

    @api.constrains("action_id", "revision")
    def _check_revision_action(self) -> None:
        for wizard in self:
            if wizard.revision.action_id != wizard.action_id:
                _debug.logic(
                    "revision_refused",
                    action=wizard.action_id.id,
                    revision=wizard.revision.id,
                    revision_action=wizard.revision.action_id.id,
                )
                raise ValidationError(
                    self.env._(
                        "The revision belongs to the server action "
                        "'%(revision_action)s', not to '%(action)s'.",
                        revision_action=wizard.revision.action_id.display_name,
                        action=wizard.action_id.display_name,
                    )
                )

    @api.depends("action_id.code", "revision.code")
    def _compute_code_diff(self) -> None:
        for wizard in self:
            rev_code = wizard.revision.code
            actual_code = wizard.action_id.code
            has_diff = actual_code != rev_code
            wizard.code_diff = (
                get_diff(
                    (actual_code or "", self.env._("Actual Code")),
                    (rev_code or "", self.env._("Revision Code")),
                    dark_color_scheme=request
                    and request.cookies.get("color_scheme") == "dark",
                )
                if has_diff
                else False
            )

    def restore_revision(self) -> None:
        self.check_singleton()
        _debug.lifecycle(
            "wizard_restore_revision",
            action=self.action_id.id,
            revision=self.revision.id,
        )
        self.action_id.code = self.revision.code
