import { GeoengineRecord } from "@geoengine/geoengine/geoengine_record";
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

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
