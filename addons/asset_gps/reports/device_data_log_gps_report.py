from odoo import fields, models


class DeviceGpsLogReport(models.Model):
    _inherit = "device.data.log.gps.report"

    asset_id = fields.Many2one(
        comodel_name="resource.asset",
        readonly=True,
    )
    asset_name = fields.Char(readonly=True)
    license_plate = fields.Char(readonly=True)

    def _get_fields_select(self) -> dict:
        res = super()._get_fields_select()
        res.update(
            {
                "asset_id": "asset.id",
                "asset_name": "asset.name",
                "license_plate": "plate.value",
            },
        )
        return res

    def _get_from_tables(self) -> list:
        # Resource identity owns the attachment across all business models.
        res = super()._get_from_tables()
        res.append(
            (
                "resource_resource",
                "tracked_resource",
                "LEFT JOIN",
                "tracked_resource.id = log.resource_id",
            ),
        )
        res.append(
            (
                "resource_asset",
                "asset",
                "LEFT JOIN",
                "asset.resource_id = tracked_resource.id",
            ),
        )
        # The plate is an identifier row of the resource, whatever its kind.
        res.append(
            (
                (
                    "(SELECT identifier.resource_id, identifier.value"
                    "   FROM resource_identifier identifier"
                    "   JOIN resource_identifier_type identifier_type"
                    "     ON identifier_type.id = identifier.type_id"
                    "  WHERE identifier_type.code = 'plate')"
                ),
                "plate",
                "LEFT JOIN",
                "plate.resource_id = asset.resource_id",
            ),
        )
        return res

    def _get_fields_group_by(self) -> list:
        res = super()._get_fields_group_by()
        res.extend(
            [
                "asset.id",
                "asset.name",
                "plate.value",
            ],
        )
        return res
