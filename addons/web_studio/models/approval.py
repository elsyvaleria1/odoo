from odoo import models


class ApprovalBinding(models.Model):
    _name = "approval.binding"
    _inherit = ["approval.binding", "mixin.studio"]


class ApprovalCategory(models.Model):
    _name = "approval.category"
    _inherit = ["approval.category", "mixin.studio"]


class ApprovalCategoryStep(models.Model):
    _name = "approval.category.step"
    _inherit = ["approval.category.step", "mixin.studio"]


class ApprovalCategoryStepMember(models.Model):
    _name = "approval.category.step.member"
    _inherit = ["approval.category.step.member", "mixin.studio"]
