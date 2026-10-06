from odoo import api, fields, models


class TestAiFieldsParent(models.Model):
    _description = "Test AI Fields"
    _name = "test.ai.fields.parent"

    properties_definition = fields.PropertiesDefinition(string="Properties Definition")


class TestAiFields(models.Model):
    _description = "Test AI Fields"
    _name = "test.ai.fields.model"

    name = fields.Char()

    parent_id = fields.Many2one(comodel_name="test.ai.fields.parent")

    properties = fields.Properties(
        definition="parent_id.properties_definition",
        string="Properties",
    )

    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Partner",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Partners",
    )

    @api.model
    def mail_allowed_qweb_expressions(self):
        return ("object.test_ai_fields", *super().mail_allowed_qweb_expressions())


class TestAiFieldsDefinition(models.Model):
    # Model with a Properties definition that's not used for some reason
    _description = "Test AI Fields"
    _name = "test.ai.fields.definition"

    properties_definition = fields.PropertiesDefinition(string="Properties Definition")


class TestAiFieldsModelNoAi(models.Model):
    _description = "Test AI Fields"
    _name = "test.ai.fields.no.ai"

    name = fields.Char()


class TestAiReadModel(models.Model):
    _description = "Test AI Read"
    _name = "test.ai.read.model"
    _inherit = ["mixin.mail.thread"]

    currency_id = fields.Many2one(comodel_name="res.currency")
    price = fields.Monetary(currency_field="currency_id")
    new_binary_field = fields.Binary(attachment=True)
