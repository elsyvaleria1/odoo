/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useDateTimePicker } from "@web/components/datetime";
import { now } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class DocumentsDatetimeBtnField extends Component {
    static template = "document.DocumentsDatetimeBtnField";
    static props = {
        ...standardFieldProps,
        label: t.string().optional(),
        btnClasses: t.string().optional(),
        icon: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        const pickerProps = {
            minDate: now(),
            type: "datetime",
            value: this.props.record.data[this.props.name] || now().startOfDay(),
        };
        this.endDateRef = elementRef();
        this.startDateRef = elementRef();
        this.datetimeBtnRef = elementRef();
        this.dateTimePicker = useDateTimePicker({
            endDateRef: this.endDateRef,
            startDateRef: this.startDateRef,
            target: this.datetimeBtnRef,
            onApply: (date) => {
                this.props.record.update({ [this.props.name]: date });
            },
            get pickerProps() {
                return pickerProps;
            },
        });
    }
}

export const documentsDatetimeBtnField = {
    component: DocumentsDatetimeBtnField,
    supportedTypes: ["datetime"],
    extractProps: ({ string, options }) => ({
        btnClasses: options.btn_classes,
        label: string,
        icon: options.icon,
    }),
};

registry.category("fields").add("documents_datetime_btn", documentsDatetimeBtnField);
