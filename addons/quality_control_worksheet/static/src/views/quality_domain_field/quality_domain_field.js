/** @odoo-module native */
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { DomainField, domainField } from "@web/fields/specialized/domain/domain_field";

export class QualityDomainField extends DomainField {
    static template = "quality_control_worksheet.QualityDomainField";

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }
}

export const qualityDomainField = {
    ...domainField,
    component: QualityDomainField,
};

registry.category("fields").add("quality_domain_field", qualityDomainField);
