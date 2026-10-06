from odoo import api, fields, models
from odoo.exceptions import UserError


class SignItemRole(models.Model):
    _name = "sign.item.role"
    _description = "Signature Item Role"
    _rec_name = "name"
    _order = "sequence, id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    default = fields.Boolean(
        default=False,
        required=True,
    )
    sequence = fields.Integer(
        string="Default order",
        default=10,
    )

    auth_method = fields.Selection(
        selection=[("sms", "Unique Code via SMS")],
        string="Extra Authentication Step",
        default=False,
        help="Force the signatory to identify using a second authentication method",
    )

    change_authorized = fields.Boolean(
        help="If checked, recipient of a document with this role can be changed after having sent the request. Useful to replace a signatory who is out of office, etc."
    )
    assign_to = fields.Many2one(
        comodel_name="res.partner",
        string="Assign to",
        help="assign the current user or the customer as a signer by default",
    )

    def write(self, vals):
        vals.pop("default", None)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_role(self) -> None:
        for role in self:
            if role.default:
                raise UserError(
                    self.env._(
                        "The role %s is required by the Sign application and cannot be deleted.",
                        role.name,
                    )
                )
