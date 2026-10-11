from odoo import api, fields, models

MIN_VERSION_FOR_KIOSK = 24.08


class IotBox(models.Model):
    _inherit = "iot.box"

    screen_orientation = fields.Selection(
        selection=[
            ("normal", "Normal"),
            ("right", "Right"),
            ("left", "Left"),
            ("inverted", "Inverted"),
        ],
        default="normal",
        help="Select the orientation of the screen for the Kiosk mode",
    )
    can_be_kiosk = fields.Boolean(
        compute="_compute_can_be_kiosk",
        store=True,
    )
    pos_id = fields.Many2one(
        comodel_name="pos.config",
        string="Linked To Point of Sale",
        index="btree_not_null",
    )

    def get_computed_img_version(self) -> float:
        try:
            version_str = self.version.split("-")[0]
            return float(version_str[1:8])
        except IndexError:
            return float(self.version)
        except ValueError:
            return 0.0

    @api.depends("device_ids.type", "version")
    def _compute_can_be_kiosk(self) -> None:
        for record in self:
            device_types = {device.type for device in record.device_ids}
            record.can_be_kiosk = (
                "display" in device_types
                and "keyboard" in device_types
                and record.get_computed_img_version() >= MIN_VERSION_FOR_KIOSK
            )

    @api.onchange("device_ids")
    def _onchange_device_ids(self) -> None:
        self._compute_can_be_kiosk()
