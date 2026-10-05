from odoo import models

ROOM_KIND = "room"


class ResourceAssetRoom(models.Model):
    _name = "resource.asset.room"
    _description = "Room"
    _inherit = ["mixin.resource.kind"]
    _table = "resource_asset_room"
    _resource_kind_code = ROOM_KIND

    def action_view_room_booking_view(self):
        self.check_singleton()
        return self.resource_id.action_view_booking_view()

    def action_view_room_bookings(self):
        self.check_singleton()
        return self.resource_id.action_view_bookings()
