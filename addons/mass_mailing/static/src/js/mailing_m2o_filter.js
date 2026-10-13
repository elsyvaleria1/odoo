/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dropdown } from "@web/components/dropdown";
import { Domain } from "@web/core/domain";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import {
    buildM2OFieldDescription,
    computeM2OProps,
    extractM2OFieldProps,
    m2oSupportedOptions,
    Many2One,
    Many2OneField,
} from "@web/fields/relational/many2one";
import { useViewModel } from "@web/model/model";

export class MailingFilterDropdown extends Dropdown {
    setup() {
        super.setup();
        useLayoutEffect(
            (inputFilterEl) => {
                if (inputFilterEl) {
                    inputFilterEl.focus();
                }
            },
            () => [document.querySelector(".o_mass_mailing_filter_name")],
        );
    }
}

export class FieldMany2OneMailingFilter extends Component {
    static template = "mass_mailing.MailingFilter";
    static components = {
        Many2One,
        MailingFilterDropdown,
    };
    static props = {
        ...Many2OneField.props,
        domain_field: t.string().optional("mailing_domain"),
        model_field: t.string().optional("mailing_model_id"),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.model = useViewModel();
        this.notification = useService("notification");
        this.orm = useService("orm");
        useLayoutEffect(
            (filterCount, readonly) => {
                const dropdown = document.querySelector(
                    ".o_field_mailing_filter .o_field_many2one_selection > .o_input_dropdown",
                );
                if (dropdown && !readonly) {
                    dropdown.classList.toggle("d-none", !filterCount);
                }
            },
            () => [this.props.record.data.mailing_filter_count, this.props.readonly],
        );
    }

    get m2oProps() {
        return computeM2OProps(this.props);
    }

    get filter() {
        const data = this.props.record.data;
        let recordDomain;
        let filterDomain;
        try {
            recordDomain = new Domain(data[this.props.domain_field] || []).toString();
            filterDomain = new Domain(data.mailing_filter_domain || []).toString();
        } catch {
            return {
                canSaveFilter: false,
                canRemoveFilter: false,
                isDomainEmpty: false,
            };
        }
        const canSaveFilter = !data.mailing_filter_id || filterDomain !== recordDomain;
        return {
            canSaveFilter,
            canRemoveFilter: !canSaveFilter,
            isDomainEmpty: recordDomain === "[]",
        };
    }

    /** @param {event} ev */
    onFilterNameInputKeydown(ev) {
        const btnSave = document.querySelector(".o_mass_mailing_btn_save_filter");
        if (ev.key === "Tab") {
            ev.preventDefault();
            btnSave.focus();
        } else if (ev.key === "Enter") {
            btnSave.click();
        }
    }

    /** @param {event} ev */
    async onRemoveFilter(ev) {
        const filterId = this.props.record.data.mailing_filter_id.id;
        const mailingDomain = this.props.record.data[this.props.domain_field];
        ev.target.disabled = true;

        await this.orm.unlink("mailing.filter", [filterId]);
        this.props.record.update({
            [this.props.name]: false,
            [this.props.domain_field]: mailingDomain,
        });
    }

    /** @param {event} ev */
    async onSaveFilter(ev) {
        const filterInput = document.querySelector("input.o_mass_mailing_filter_name");
        const filterName = filterInput.value.trim();
        if (filterName.length === 0) {
            this.notification.add(_t("Please provide a name for the filter"), {
                type: "danger",
            });
            ev.stopPropagation();
            filterInput.focus();
        } else {
            const [newFilterId] = await this.model.orm.create("mailing.filter", [
                {
                    name: filterName,
                    mailing_domain: this.props.record.data[this.props.domain_field],
                    mailing_model_id: this.props.record.data[this.props.model_field].id,
                },
            ]);
            this.props.record.update({
                [this.props.name]: { id: newFilterId, display_name: filterName },
            });
        }
    }
}

registry.category("fields").add("mailing_filter", {
    ...buildM2OFieldDescription(FieldMany2OneMailingFilter),
    supportedOptions: [
        ...m2oSupportedOptions,
        {
            label: _t("Domain field"),
            name: "domain_field",
            type: "field",
            availableTypes: ["char"],
        },
        {
            label: _t("Model field"),
            name: "model_field",
            type: "field",
            availableTypes: ["char"],
        },
    ],
    extractProps({ options }) {
        const props = extractM2OFieldProps(...arguments);
        props.domain_field = options.domain_field;
        props.model_field = options.model_field;
        return props;
    },
});
