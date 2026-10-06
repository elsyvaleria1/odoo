from odoo import fields, models


class ResourceTest(models.Model):
    _name = "resource.test"
    _description = "Test Resource Model"
    _inherit = ["mixin.resource"]

    name = fields.Char()


class ResourceOtherOwner(models.Model):
    _name = "resource.test.other.owner"
    _inherit = "resource.test"
    _description = "Another Resource Owner for Tests"


class ResourceReference(models.Model):
    _name = "resource.test.reference"
    _inherit = "resource.test"
    _description = "Non-owning Resource Reference for Tests"
    _resource_owns = False
