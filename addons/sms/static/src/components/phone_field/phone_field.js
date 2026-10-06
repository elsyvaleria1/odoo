/** @odoo-module native */
import { t } from "@odoo/owl";
import { SendSMSButton } from "@sms/components/sms_button/sms_button";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import {
    formPhoneField,
    PhoneField,
    phoneField,
    phoneFieldProps,
} from "@web/fields/basic/phone/phone_field";

patch(PhoneField, {
    components: {
        ...PhoneField.components,
        SendSMSButton,
    },
});
Object.assign(phoneFieldProps, {
    enableButton: t.boolean().optional(true),
});

const patchDescr = () => ({
    extractProps({ options }) {
        const props = super.extractProps(...arguments);
        props.enableButton = options.enable_sms;
        return props;
    },
    supportedOptions: [
        {
            label: _t("Enable SMS"),
            name: "enable_sms",
            type: "boolean",
            default: true,
        },
    ],
});

patch(phoneField, patchDescr());
patch(formPhoneField, patchDescr());
