/** @odoo-module native */
import { PartnerAutoComplete } from "@partner_autocomplete/js/partner_autocomplete_component";
import { usePartnerAutocomplete } from "@partner_autocomplete/js/partner_autocomplete_core";
import { registry } from "@web/core/registry";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { CharField, charField } from "@web/fields/basic/char/char_field";
import { useInputField } from "@web/fields/input_field_hook";

export class PartnerAutoCompleteCharField extends CharField {
    static template = "partner_autocomplete.PartnerAutoCompleteCharField";
    static components = {
        ...CharField.components,
        PartnerAutoComplete,
    };
    setup() {
        super.setup();

        this.orm = useService("orm");
        this.partnerAutocomplete = usePartnerAutocomplete();

        this.inputRef = useChildRef();
        useInputField({
            getValue: () => this.props.record.data[this.props.name] || "",
            parse: (v) => this.parse(v),
            ref: this.inputRef,
        });
    }

    get sources() {
        return [
            this.partnerAutocomplete.makeAutocompleteSource({
                cssClass: "partner_autocomplete_dropdown_char",
                getCountryId: () => this.props.record.data?.country_id?.id || false,
                onSelectOption: (suggestion) =>
                    this.onSelectPartnerAutocompleteOption(suggestion),
            }),
        ];
    }

    async onSelectPartnerAutocompleteOption(option) {
        const data = await this.partnerAutocomplete.getCreateData(option);
        if (!data?.company) {
            return;
        }

        if (data.logo) {
            data.company.image_1920 = data.logo;
        }

        const additionalData = {
            entity_type: data.company.entity_type,
            unspsc_codes: data.company.unspsc_codes,
        };
        data.company = this.partnerAutocomplete.removeUselessFields(
            data.company,
            Object.keys(this.props.record.fields),
        );

        if (data.company.name) {
            await this.props.record.update({ name: data.company.name });
        }
        await this.props.record.update(data.company);

        if (this.props.record.resModel === "res.partner") {
            const saved = await this.props.record.save();
            if (saved && data.isEnrichAccessible) {
                await this.orm.call("res.partner", "enrich_company_message_post", [
                    this.props.record.resId,
                    additionalData,
                ]);
                this.props.record.load();
            }
        }
        if (this.props.setDirty) {
            this.props.setDirty(false);
        }
    }
}

export const partnerAutoCompleteCharField = {
    ...charField,
    component: PartnerAutoCompleteCharField,
};

registry
    .category("fields")
    .add("field_partner_autocomplete", partnerAutoCompleteCharField);
