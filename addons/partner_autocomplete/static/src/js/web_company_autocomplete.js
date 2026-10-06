/** @odoo-module native */
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { session } from "@web/session";

export const companyAutocompleteService = {
    dependencies: ["orm"],

    start(env, { orm }) {
        if (session.iap_company_enrich) {
            orm.silent.call(
                "res.company",
                "iap_enrich_auto",
                [user.activeCompany.id],
                {},
            );
        }
    },
};

registry
    .category("services")
    .add("partner_autocomplete.companyAutocomplete", companyAutocompleteService);
