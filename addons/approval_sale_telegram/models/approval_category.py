from odoo import fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    telegram_confirm_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="approval_category_telegram_confirm_user_rel",
        column1="category_id",
        column2="user_id",
        string="Confirm by Telegram",
        domain=[("share", "=", False)],
        help="Users who confirm the sale order once this category approves it. "
        "Each receives a Telegram message with the order summary and a "
        "Confirm button, provided they have a chat linked to a bot with "
        "'Notify Approval Requests' enabled. Nothing is sent when the company "
        "confirms approved orders automatically.",
    )
