/** @odoo-module native */
import { MapRenderer } from "@web_map/map_view/map_renderer";

export class StockMapRenderer extends MapRenderer {
    static markerPopupTemplate = "stock_enterprise.markerPopup";

    /**
     * Transfers leaving one warehouse make a round trip: the warehouse is both
     * ends of the route and every delivery address is a stop along it.
     */
    get googleMapParams() {
        const records = this.model.data.records;
        const warehouseAddress = records[0]?.warehouse_address_id;
        if (!warehouseAddress?.contact_address_complete) {
            return super.googleMapParams;
        }
        const isSingleWarehouse = records.every(
            (record) => record.warehouse_address_id.id === warehouseAddress.id,
        );
        if (!isSingleWarehouse) {
            return super.googleMapParams;
        }
        const params = {
            origin: warehouseAddress.contact_address_complete,
            destination: warehouseAddress.contact_address_complete,
        };
        const stops = this.getRouteAddresses();
        if (stops.length) {
            params.waypoints = this.joinWaypoints(stops);
        }
        return params;
    }

    getMarkerPopupData(markerInfo) {
        return markerInfo.records.map((record) => ({
            fields: this.getMarkerPopupRecordData(record),
            id: record.id,
        }));
    }
}
