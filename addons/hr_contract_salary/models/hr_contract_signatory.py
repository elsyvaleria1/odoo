from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError


class HrContractSignatory(models.Model):
    _name = "hr.contract.signatory"
    _description = "Contract Signatories"

    sign_role_id = fields.Many2one(
        comodel_name="sign.item.role",
        string="Contract Role",
    )
    signatory = fields.Selection(
        selection=[
            ("employee", "Employee"),
            ("hr", "HR Responsible"),
            ("partner", "Specific Partner"),
        ]
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        copy=True,
    )
    contract_template_id = fields.Many2one(
        comodel_name="hr.version",
        index="btree_not_null",
    )
    update_contract_template_id = fields.Many2one(
        comodel_name="hr.version",
        index="btree_not_null",
    )
    offer_id = fields.Many2one(
        comodel_name="hr.contract.salary.offer",
        index="btree_not_null",
    )
    order = fields.Integer(
        string="Sign Order",
        default=1,
        required=True,
        help="Signatories sharing an order are asked to sign at the same time; "
        "a higher order is only asked once every lower one has signed.",
    )

    @api.model
    def create_empty_signatories(self, sign_template):
        roles = list(dict.fromkeys(sign_template.sign_item_ids.responsible_id.ids))

        role_dict = {
            self.env.ref("hr_sign.sign_item_role_employee_signatory").id: "employee",
            self.env.ref("hr_sign.sign_item_role_job_responsible").id: "hr",
        }

        return [Command.clear()] + [
            Command.create(
                {
                    "sign_role_id": role,
                    "signatory": role_dict.get(role, "hr"),
                    "order": 1,
                }
            )
            for role in roles
        ]

    @api.constrains("signatory", "partner_id")
    def _check_partner(self) -> None:
        for signatory in self:
            if not signatory.signatory or (
                signatory.signatory == "partner" and not signatory.partner_id
            ):
                raise ValidationError(
                    self.env._(
                        "A signatory role is unassigned. Please ensure there is a valid group or person assigned to each role."
                    )
                )
