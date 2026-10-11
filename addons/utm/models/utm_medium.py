import re

from psycopg import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import UserError


class UtmMedium(models.Model):
    _name = "utm.medium"
    _inherit = "mixin.utm.unique.name"
    _description = "UTM Medium"
    _order = "name"

    name = fields.Char(
        string="Medium Name",
        translate=False,
        required=True,
    )
    active = fields.Boolean(default=True)

    _unique_name = models.Constraint(
        "UNIQUE(name)",
        "The name must be unique",
    )

    @property
    def SELF_REQUIRED_UTM_MEDIUMS_REF(self):
        return {
            "utm.utm_medium_email": "Email",
            "utm.utm_medium_direct": "Direct",
            "utm.utm_medium_website": "Website",
            "utm.utm_medium_twitter": "X",
            "utm.utm_medium_facebook": "Facebook",
            "utm.utm_medium_linkedin": "LinkedIn",
        }

    @api.ondelete(at_uninstall=False)
    def _unlink_except_utm_medium_record(self) -> None:
        for medium in self.SELF_REQUIRED_UTM_MEDIUMS_REF:
            utm_medium = self.env.ref(medium, raise_if_not_found=False)
            if utm_medium and utm_medium in self:
                raise UserError(
                    self.env._(
                        "Oops, you can't delete the Medium '%s'.\n"
                        "Doing so would be like tearing down a load-bearing wall \u2014 not the best idea.",
                        utm_medium.name,
                    )
                )

    def _get_or_create_utm_medium(self, name, module="utm"):
        name_normalized = re.sub(r"[\s|.]", "_", name.lower())
        try:
            return self.env.ref(f"{module}.utm_medium_{name_normalized}")
        except ValueError:
            try:
                with self.env.cr.savepoint():
                    utm_medium = (
                        self.sudo()
                        .env["utm.medium"]
                        .create(
                            {
                                "name": self.SELF_REQUIRED_UTM_MEDIUMS_REF.get(
                                    f"{module}.utm_medium_{name_normalized}", name
                                )
                            }
                        )
                    )
                    self.sudo().env["ir.model.data"].create(
                        {
                            "name": f"utm_medium_{name_normalized}",
                            "module": module,
                            "res_id": utm_medium.id,
                            "model": "utm.medium",
                        }
                    )
            except IntegrityError:
                return self.env.ref(f"{module}.utm_medium_{name_normalized}")
            return utm_medium
