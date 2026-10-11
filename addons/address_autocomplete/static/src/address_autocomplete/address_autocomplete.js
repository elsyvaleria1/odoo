/** @odoo-module native */
import { t } from "@odoo/owl";
import { AutoComplete } from "@web/components/autocomplete";
import { colorScheme } from "@web/core/color_scheme";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useChildRef } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/fields/basic/char/char_field";
import { useInputField } from "@web/fields/input_field_hook";
import { session } from "@web/session";

import { addressSession } from "../address_session.js";

const standardAddressFields = {
    street: {
        label: _t("Street field"),
        type: ["char"],
    },
    street2: {
        label: _t("Additional street field"),
        type: ["char"],
    },
    city: {
        label: _t("City field"),
        type: ["char"],
    },
    state_id: {
        label: _t("State field"),
        type: ["char", "many2one"],
    },
    zip: {
        label: _t("Zip field"),
        type: ["char"],
    },
    country_id: {
        label: _t("Country field"),
        type: ["char", "many2one"],
    },
};

export class AddressAutoComplete extends CharField {
    static template = "address_autocomplete.AddressAutoCompleteTemplate";
    static components = { AutoComplete, ...CharField.components };

    static props = { ...CharField.props, addressFieldMap: t.object().optional({}) };

    setup() {
        super.setup();
        this.input = useChildRef();
        useInputField({
            ref: this.input,
            getValue: () => this.props.record.data[this.props.name] || "",
            parse: (v) => this.parse(v),
        });
        this.colorScheme = colorScheme;
    }

    get sources() {
        return [
            {
                options: async (request) => {
                    if (!session.address_autocomplete || request.length <= 5) {
                        return [];
                    }
                    const { results, credit } =
                        await addressSession.getAddressPropositions({
                            partial_address: request,
                            use_employees_key: true,
                        });
                    const options = results.map((result) => ({
                        label: result.label,
                        onSelect: () => this.selectAddressProposition(result),
                    }));
                    if (options.length && credit) {
                        options.push({ label: credit.label, data: { credit } });
                    }
                    return options;
                },
                optionSlot: "option",
                placeholder: _t("Searching for addresses..."),
            },
        ];
    }

    async selectAddressProposition(option) {
        const address = await addressSession.getAddressDetails({
            address: option.label,
            ref: option.ref,
            use_employees_key: true,
        });
        if (!address) {
            return;
        }

        const fieldToDetail = {
            street: "formatted_street_number",
            country_id: "country",
            state_id: "state",
        };
        const fieldsToUpdate = Object.keys(standardAddressFields);

        const activeFields = this.props.record.activeFields;
        const fields = this.props.record.fields;
        const addressFieldMap = this.props.addressFieldMap;

        const valuesToUpdate = {};
        const rest = [];
        fieldsToUpdate.forEach((fieldName) => {
            const addressField = fieldToDetail[fieldName] || fieldName;
            let value = address[addressField];

            const recordFieldName = addressFieldMap[fieldName] || fieldName;
            if (recordFieldName in activeFields) {
                if (fields[recordFieldName].type === "many2one") {
                    value = value && { id: value[0], display_name: value[1] };
                } else if (Array.isArray(value)) {
                    value = value[1];
                }
                valuesToUpdate[recordFieldName] = value || false;
            } else if (!(recordFieldName in fields)) {
                value = Array.isArray(value) ? value[1] : value;
                rest.push(value);
            }
        });
        if (!(this.props.name in valuesToUpdate) && rest.length) {
            valuesToUpdate[this.props.name] = rest.join(" ");
        }
        this.props.record.update(valuesToUpdate);
    }
}

export const addressAutoComplete = {
    ...charField,
    component: AddressAutoComplete,
    displayName: _t("Address AutoComplete"),
    supportedTypes: ["char"],
    supportedOptions: [
        ...charField.supportedOptions,
        ...Object.entries(standardAddressFields).map(([fname, data]) => ({
            label: data.label,
            placeholder: fname,
            type: "field",
            name: fname,
            availableTypes: data.type,
        })),
    ],
    extractProps: (fieldInfo, dynamicInfo) => {
        const { options } = fieldInfo;
        const props = charField.extractProps(fieldInfo, dynamicInfo);
        const addressFieldMap = {};
        Object.keys(standardAddressFields).forEach((fname) => {
            const optionValue = options[fname];
            if (optionValue) {
                addressFieldMap[fname] = optionValue;
            }
        });
        props.addressFieldMap = addressFieldMap;
        return props;
    },
};
registry.category("fields").add("address_autocomplete", addressAutoComplete);
