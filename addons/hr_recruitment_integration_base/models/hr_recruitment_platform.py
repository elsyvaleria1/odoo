from odoo import fields, models


class HrRecruitmentPlatform(models.Model):
    _name = "hr.recruitment.platform"
    _description = "Recruitment Platform"
    _inherit = ["mixin.avatar"]

    name = fields.Char(required=True)
    website = fields.Char()

    # crud pricing
    price_to_publish = fields.Float(string="Price to Publish")
    price_to_get = fields.Float(string="Price to Get")
    price_to_update = fields.Float(string="Price to Update")
    price_to_delete = fields.Float(string="Price to Delete")

    def _post_api_call(self, data) -> dict:
        # To be overridden by the specific platform
        return {
            "data": {},
            "status": self.env._("failure"),
            "message": self.env._(
                "No API call defined for this platform please contact the administrator"
            ),
        }
