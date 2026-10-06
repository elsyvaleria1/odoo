import { GeoengineRecord } from "@geoengine/geoengine/geoengine_record";
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

/**
 * A device popup says where the vehicle is now, as a street address. The
 * address is looked up when the popup opens, not when the map loads: the map
 * reads every device at once and the geocoder answers one request a second.
 * The popup is remounted on every click, so each opening asks again and the
 * server's cache decides whether that costs a lookup.
 */
patch(GeoengineRecord.prototype, {
    setup() {
        super.setup(...arguments);
        const record = this.props.record;
        const deviceId = record?.resModel === "device.device" && record.resId;
        if (!deviceId) {
            return;
        }
        const orm = useService("orm");
        this.dataState.record.current_address_live = { value: null, loading: true };
        onWillStart(() => {
            // Not awaited: the popup opens at once with its placeholder.
            orm.call("device.device", "get_current_address", [[deviceId]])
                .then((address) => {
                    this.dataState.record.current_address_live = {
                        value: address || false,
                        loading: false,
                    };
                })
                .catch(() => {
                    this.dataState.record.current_address_live = {
                        value: false,
                        loading: false,
                    };
                });
        });
    },
});
