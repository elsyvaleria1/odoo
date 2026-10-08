from odoo import fields, models


class DeviceTokenShow(models.AbstractModel):
    # abstract like res.users.apikeys.show: the token travels in the dialog's
    # context and is never written to a table
    _name = "device.token.show"
    _description = "Show Device Token"

    id = fields.Id()
    identifier = fields.Char(readonly=True)
    token = fields.Char(readonly=True)
