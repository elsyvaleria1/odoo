/** @odoo-module native */
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import {
    formPhoneField,
    PhoneField,
    phoneField,
    phoneFieldProps,
} from "@web/fields/basic/phone/phone_field";

import { SendWhatsAppButton } from "../whatsapp_button/whatsapp_button.js";

patch(PhoneField, {
    components: {
        ...PhoneField.components,
        SendWhatsAppButton,
    },
});
Object.assign(phoneFieldProps, {
    enableWhatsAppButton: t.boolean().optional(true),
});

const patchDescr = () => ({
    extractProps({ options }) {
        const props = super.extractProps(...arguments);
        props.enableWhatsAppButton = options.enable_whatsapp;
        return props;
    },
    supportedOptions: [
        ...(phoneField.supportedOptions ? phoneField.supportedOptions : []),
        {
            label: _t("Enable WhatsApp"),
            name: "enable_whatsapp",
            type: "boolean",
            default: true,
        },
    ],
});

patch(phoneField, patchDescr());
patch(formPhoneField, patchDescr());
