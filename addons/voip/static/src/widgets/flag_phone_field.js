/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class FlagPhoneField extends Component {
    static template = "voip.FlagPhoneField";
    static props = {
        ...standardFieldProps,
        height: t.number().optional(),
        width: t.number().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.regionNames = new Intl.DisplayNames(user.lang, { type: "region" });
    }

    get imgAlt() {
        if (this.props.record.data.country_id) {
            return _t("%(country)s flag", {
                country: this.props.record.data.country_id.display_name,
            });
        }
        return "";
    }

    get height() {
        return this.props.height;
    }

    get width() {
        return this.props.width;
    }
}

export const flagPhoneField = {
    component: FlagPhoneField,
    displayName: "Flag Phone",
    supportedTypes: ["char", "text"],
    extractProps: () => ({
        height: 20,
        width: 20,
    }),
};

registry.category("fields").add("voip_flag_phone", flagPhoneField);
