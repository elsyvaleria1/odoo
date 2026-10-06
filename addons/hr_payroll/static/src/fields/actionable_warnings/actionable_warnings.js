/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";
import { useViewModel } from "@web/model/model";

const WARNING_TYPE_ORDER = ["danger", "warning", "info"];

export class ActionableWarningsField extends Component {
    static template = "hr_payroll.ActionableWarnings";
    static props = { ...standardFieldProps, firstOnly: t.boolean().optional(false) };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.model = useViewModel();
        this.actionService = useService("action");
    }

    get errorData() {
        return this.props.record.data[this.props.name];
    }

    async handleOnClick(errorData) {
        return this.actionService.doAction(errorData.action, {
            onClose: (onCloseInfo) => {
                if (!onCloseInfo?.noReload) {
                    this.model.load();
                }
            },
        });
    }

    get sortedActionableWarnings() {
        return (
            this.errorData &&
            Object.fromEntries(
                Object.entries(this.errorData).sort(
                    (a, b) =>
                        WARNING_TYPE_ORDER.indexOf(b[1]["level"] || "warning") -
                        WARNING_TYPE_ORDER.indexOf(a[1]["level"] || "warning"),
                ),
            )
        );
    }

    get warningsByLevel() {
        const result = { info: [], warning: [], danger: [] };
        Object.entries(this.errorData).forEach((entry) => {
            const [index, warning] = entry;
            warning.id = index;
            result[warning["level"] || "warning"].push(warning);
        });
        return result;
    }

    get firstWarning() {
        const entries = Object.entries(this.errorData || {});
        return entries.length ? entries[0][1] : undefined;
    }
}

export const actionableWarningsField = {
    component: ActionableWarningsField,
    supportedOptions: [
        {
            label: _t("Display first warning only"),
            name: "first_only",
            type: "boolean",
        },
    ],
    extractProps({ options }) {
        return {
            firstOnly: options.first_only,
        };
    },
};
registry.category("fields").add("actionable_warnings", actionableWarningsField);
