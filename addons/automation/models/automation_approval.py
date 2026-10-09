from odoo import fields, models
from odoo.tools import frozendict


class AutomationApproval(models.Model):
    _name = "automation.approval"
    _description = "Workflow Approval Decision"
    _rec_name = "user_id"
    _access_anchors = frozendict(
        {"company": models.Anchor("line_id.runtime_id.company_ids", shared=False)}
    )

    line_id = fields.Many2one(
        comodel_name="automation.runtime.line",
        index=True,
        required=True,
        ondelete="cascade",
    )
    round = fields.Integer(required=True)
    user_id = fields.Many2one(
        comodel_name="res.users",
        required=True,
        ondelete="restrict",
    )
    activity_id = fields.Many2one(
        comodel_name="mail.activity",
        index="btree_not_null",
        ondelete="set null",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("withdrawn", "Withdrawn"),
        ],
        default="pending",
        readonly=True,
        required=True,
    )
    needs_settlement = fields.Boolean(
        default=False,
        readonly=True,
    )
    decided_at = fields.Datetime(readonly=True)
    decided_by_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
        ondelete="restrict",
    )

    _line_id_needs_settlement_idx = models.Index(
        "(line_id) WHERE needs_settlement IS TRUE "
        "OR (state = 'pending' AND activity_id IS NULL)"
    )

    _line_id_round_user_id_uniq = models.Constraint(
        "UNIQUE(line_id, round, user_id)",
        "An approver can have only one decision in an approval round.",
    )
    _activity_id_uniq = models.Constraint(
        "UNIQUE(activity_id)",
        "An activity can carry only one approval decision.",
    )
