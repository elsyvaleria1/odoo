import { GeoengineRenderer } from "@geoengine/geoengine/geoengine_renderer";
import { ol } from "@geoengine/lib/geo_libs";
import { onWillDestroy } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useOptionalService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

const GPS_NOTIFICATION_TYPE = "device_device/gps_position";
const GEOFENCE_ALERT_TYPE = "device_device/geofence_alert";

patch(GeoengineRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.busService = useOptionalService("bus_service");
        this.notification = useOptionalService("notification");
        this._gpsLivePending = new Map();
        this._gpsLiveRafId = null;
        this._gpsLiveCallback = (payload) => this._onGpsPosition(payload);
        this.busService?.subscribe(GPS_NOTIFICATION_TYPE, this._gpsLiveCallback);
        this._geofenceAlertCallback = (payload) => this._onGeofenceAlert(payload);
        this.busService?.subscribe(GEOFENCE_ALERT_TYPE, this._geofenceAlertCallback);

        onWillDestroy(() => {
            this.busService?.unsubscribe(GPS_NOTIFICATION_TYPE, this._gpsLiveCallback);
            this.busService?.unsubscribe(
                GEOFENCE_ALERT_TYPE,
                this._geofenceAlertCallback,
            );
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

    _onGeofenceAlert({ type, device_name, geofence_name }) {
        if (this.props.model?.root?.resModel !== "device.device") {
            return;
        }
        const names = { device: device_name, geofence: geofence_name };
        this.notification?.add(
            type === "geofence_enter"
                ? _t("%(device)s entered %(geofence)s", names)
                : _t("%(device)s left %(geofence)s", names),
            { type: "info" },
        );
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
