from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UtmSource(models.Model):
    _name = "utm.source"
    _inherit = "mixin.utm.unique.name"
    _description = "UTM Source"

    name = fields.Char(
        string="Source Name",
        required=True,
    )

    _unique_name = models.Constraint(
        "UNIQUE(name)",
        "The name must be unique",
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_referral(self) -> None:
        utm_source_referral = self.env.ref(
            "utm.utm_source_referral", raise_if_not_found=False
        )
        for record in self:
            if record == utm_source_referral:
                raise ValidationError(
                    self.env._("You cannot delete the 'Referral' UTM source record.")
                )

    def _generate_name(self, record, content) -> str | None:
        """Generate the UTM source name based on the content of the source."""
        if not content:
            return None

        content = content.replace("\n", " ")
        if len(content) >= 24:
            content = f"{content[:20]}..."

        create_date = record.create_date or fields.Datetime.today()
        model_description = self.env["ir.model"]._get(record._name).name
        return self.env._(
            "%(content)s (%(model_description)s created on %(create_date)s)",
            content=content,
            model_description=model_description,
            create_date=fields.Date.to_string(create_date),
        )
