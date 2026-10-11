/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class StatusBubble extends Component {
    static template = "hr_payroll.StatusBubble";
    static props = {
        record: t.object(),
        removeStates: t.array().optional([]),
        fieldName: t.string().optional("state"),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.selection = this.props.record.fields[
            this.props.fieldName
        ].selection.filter((o) => !this.props?.removeStates.includes(o[0]));
    }

    get hasError() {
        return this.props.record.data.has_error ?? false;
    }

    get issueCount() {
        return this.props.record.data.payslips_with_issues ?? 0;
    }

    get activeIndex() {
        return this.selection.findIndex(
            ([key]) => key === this.props.record.data[this.props.fieldName],
        );
    }

    get payslipCount() {
        return this.props.record.data.payslip_count ?? 0;
    }

    isReached(optionIndex) {
        return (
            optionIndex < this.activeIndex ||
            (optionIndex === this.activeIndex && this.payslipCount > 0)
        );
    }
}

export class StatusBubbleField extends StatusBubble {
    static props = { ...standardFieldProps, ...StatusBubble.props };
}

export const statusBubbleField = {
    component: StatusBubbleField,
    displayName: _t("Status Bubble"),
    supportedOptions: [
        {
            label: _t("Issue Count"),
            name: "issue_count_field",
            type: "integer",
        },
        {
            label: _t("Has Error"),
            name: "has_error_field",
            type: "boolean",
        },
        {
            label: _t("Remove State"),
            name: "remove_states",
            type: "string",
        },
    ],
    fieldDependencies: [
        { name: "payslips_with_issues", type: "integer" },
        { name: "has_error", type: "boolean" },
        { name: "payslip_count", type: "integer" },
    ],
    supportedTypes: ["many2one", "selection"],
    extractProps({ name, options }) {
        return {
            fieldName: name,
            removeStates: options.remove_states,
        };
    },
};

registry.category("fields").add("hr_payroll_status_bubble", statusBubbleField);
