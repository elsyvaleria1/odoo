/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { SearchModel } from "@web/search/search_model";

export class MrpMpsSearchModel extends SearchModel {
    /** @override */
    _getFieldDomain(field, autocompleteValues) {
        if (field.fieldName === "bom_id") {
            const domains = autocompleteValues.map(({ value, operator }) => {
                const domain = [
                    "|",
                    ["product_id.bom_line_ids.bom_id", operator, value],
                    "|",
                    ["product_id.variant_bom_ids", operator, value],
                    "&",
                    ["product_tmpl_id.bom_ids.product_id", "=", false],
                    ["product_tmpl_id.bom_ids", operator, value],
                ];
                return new Domain(domain);
            });
            return Domain.or(domains);
        } else {
            return super._getFieldDomain(...arguments);
        }
    }
}
