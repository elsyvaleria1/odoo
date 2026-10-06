import { GeoengineRenderer } from "@geoengine/geoengine/geoengine_renderer";
import { ol } from "@geoengine/lib/geo_libs";
import { onWillDestroy } from "@odoo/owl";
import { useOptionalService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

const GPS_NOTIFICATION_TYPE = "device_device/gps_position";

patch(GeoengineRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.busService = useOptionalService("bus_service");
        this._gpsLivePending = new Map();
        this._gpsLiveRafId = null;
        this._gpsLiveCallback = (payload) => this._onGpsPosition(payload);
        this.busService?.subscribe(GPS_NOTIFICATION_TYPE, this._gpsLiveCallback);

        onWillDestroy(() => {
            this.busService?.unsubscribe(GPS_NOTIFICATION_TYPE, this._gpsLiveCallback);
            if (this._gpsLiveRafId) {
                cancelAnimationFrame(this._gpsLiveRafId);
                this._gpsLiveRafId = null;
            }
        });
    },

    _onGpsPosition(payload) {
        if (this.props.model?.root?.resModel !== "device.device") {
            return;
        }
        const { device_id, latitude, longitude } = payload;
        if (!device_id || latitude == null || longitude == null) {
            return;
        }
        this._gpsLivePending.set(device_id, payload);
        if (!this._gpsLiveRafId) {
            this._gpsLiveRafId = requestAnimationFrame(() => this._applyGpsUpdates());
        }
    },

    _applyGpsUpdates() {
        this._gpsLiveRafId = null;
        const pending = new Map(this._gpsLivePending);
        this._gpsLivePending.clear();

        for (const [deviceId, { latitude, longitude }] of pending) {
            const feature = this.interactions.findFeatureById(deviceId);
            if (!feature) {
                continue;
            }
            const coords = ol.proj.fromLonLat(
                [longitude, latitude],
                this.map.getView().getProjection(),
            );
            const geom = feature.getGeometry();
            if (geom && geom.setCoordinates) {
                geom.setCoordinates(coords);
            }

            this.trails?.addPosition("device.device", deviceId, {
                type: "Point",
                coordinates: [longitude, latitude],
            });
        }
    },
});
