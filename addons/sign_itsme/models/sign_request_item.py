from odoo import fields, models
from odoo.exceptions import ValidationError


class SignRequestItem(models.Model):
    _inherit = "sign.request.item"

    itsme_validation_hash = fields.Char(
        string="itsme® Validation Token",
        copy=False,
        readonly=True,
    )
    itsme_signer_name = fields.Char(
        string="itsme® Signer's Name",
        copy=False,
        readonly=True,
    )
    itsme_signer_birthdate = fields.Date(
        string="itsme® Signer's Birthdate",
        copy=False,
        readonly=True,
    )

    def _post_fill_request_item(self):
        for sri in self:
            if (
                sri.role_id.auth_method == "itsme"
                and not sri.itsme_validation_hash
                and not sri.signed_without_extra_auth
            ):
                raise ValidationError(
                    self.env._("Sign request item is not validated yet.")
                )
        return super()._post_fill_request_item()

    def sign(self, signature, **kwargs):
        if self.role_id.auth_method == "itsme":
            return self._sign(
                signature,
                validation_required=not self.signed_without_extra_auth,
                **kwargs,
            )
        return super().sign(signature, **kwargs)
