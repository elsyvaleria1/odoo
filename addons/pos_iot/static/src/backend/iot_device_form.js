/** @odoo-module native */
import { iotDeviceFormView } from "@iot/backend/iot_device_form";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

patch(iotDeviceFormView.Controller.prototype, {
    setup() {
        super.setup(...arguments);
        this.iotLongpolling = useService("iot_longpolling");
    },

    async onClickButtonTest(params) {
        if (params.clickParams.name === "test_device") {
            odoo.use_lna = (
                await this.orm.call("pos.printer", "use_local_network_access")
            ).use_lna;
            this.iotLongpolling.setLna(odoo.use_lna);
        }
        return super.onClickButtonTest(params);
    },
});
