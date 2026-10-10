from odoo import api, fields, models
from odoo.tools import frozendict


class AccountReturnSubmissionLine(models.Model):
    _name = "account.return.submission.line"
    _access_anchors = frozendict(
        {
            "company": models.Anchor(
                "submission_id.return_id.company_ids", shared=False
            ),
        }
    )
    _description = "Amount of a Tax Return Submission"
    _order = "sequence, id"

    submission_id = fields.Many2one(
        comodel_name="account.return.submission",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    code = fields.Char(
        help="The authority's own code for the concept, when it has one."
    )
    name = fields.Char(required=True)
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="submission_id.return_id.amount_to_pay_currency_id",
    )
    amount = fields.Monetary(currency_field="currency_id")

    def write(self, vals):
        self.submission_id._check_writable_fields({"line_ids": vals})
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        submissions = self.env["account.return.submission"].browse(
            [vals["submission_id"] for vals in vals_list if vals.get("submission_id")]
        )
        submissions._check_writable_fields({"line_ids": vals_list})
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_accepted_submission(self) -> None:
        self.submission_id._check_writable_fields({"line_ids": self.ids})
