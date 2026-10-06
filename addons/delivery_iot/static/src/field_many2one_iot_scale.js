/** @odoo-module native */
import { useIotDevice } from "@iot/iot_device_hook";
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    extractM2OFieldProps,
    Many2One,
    Many2OneField,
} from "@web/fields/relational/many2one";
import { useViewModel } from "@web/model/model";

export class FieldMany2OneIoTScale extends Component {
    static template = "delivery_iot.FieldMany2OneIoTScale";
    static components = { Many2One };
    static props = {
        ...Many2OneField.props,
        manual_measurement_field: t.string(),
        ip_field: t.string(),
        identifier_field: t.string(),
        value_field: t.string(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.model = useViewModel();
        this.getIotDevice = useIotDevice({
            getIotIp: () => this.props.record.data[this.props.ip_field],
            getIdentifier: () => this.props.record.data[this.props.identifier_field],
            onValueChange: (data) =>
                this.props.record.update({ [this.props.value_field]: data.value }),
            onStartListening: () => {
                if (this.getIotDevice() && !this.manualMeasurement) {
                    this.getIotDevice().action({ action: "start_reading" });
                }
            },
            onStopListening: () => {
                if (this.getIotDevice() && !this.manualMeasurement) {
                    this.getIotDevice().action({ action: "stop_reading" });
                }
            },
        });
    }

    get m2oProps() {
        return computeM2OProps(this.props);
    }
    get showManualReadButton() {
        return (
            this.getIotDevice() && this.manualMeasurement && this.model.root.isInEdition
        );
    }
    get manualMeasurement() {
        return this.props.record.data[this.props.manual_measurement_field];
    }
    onClickReadWeight() {
        return this.getIotDevice().action({ action: "read_once" });
    }
}

registry.category("fields").add("field_many2one_iot_scale", {
    ...buildM2OFieldDescription(FieldMany2OneIoTScale),
    extractProps({ options }) {
        const props = extractM2OFieldProps(...arguments);
        props.manual_measurement_field = options.manual_measurement_field;
        props.ip_field = options.ip_field;
        props.identifier_field = options.identifier;
        props.value_field = options.value_field;
        return props;
    },
});
