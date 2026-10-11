/** @odoo-module native */

import { onWillStart } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { KeepLast } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { renderToMarkup } from "@web/core/utils/render";

/** @type {typeof import("jsvat") | undefined} loaded once, on first use */
let jsvat;

const INTERNAL_KEYS = [
    "error",
    "error_message",
    "query",
    "description",
    "logo",
    "entity_type",
    "unspsc_codes",
];

export function usePartnerAutocomplete() {
    const keepLastOdoo = new KeepLast();

    const notification = useService("notification");
    const orm = useService("orm");

    let lastNoResults = null;

    onWillStart(async () => {
        jsvat ??= await import("jsvat");
    });

    function sanitizeVAT(value) {
        return value ? value.replace(/[^A-Za-z0-9]/g, "") : "";
    }

    function isVATNumber(value) {
        return jsvat.checkVATNumber(sanitizeVAT(value));
    }

    function isGSTNumber(value) {
        let isGST = false;
        if (value && value.length === 15) {
            const allGSTinRe = [
                /\d{2}[a-zA-Z]{5}\d{4}[a-zA-Z][1-9A-Za-z][Zz1-9A-Ja-j][0-9a-zA-Z]/,
                /\d{4}[A-Z]{3}\d{5}[UO]N[A-Z0-9]/,
                /\d{4}[a-zA-Z]{3}\d{5}NR[0-9a-zA-Z]/,
                /\d{2}[a-zA-Z]{4}[a-zA-Z0-9]\d{4}[a-zA-Z][1-9A-Za-z][DK][0-9a-zA-Z]/,
                /\d{2}[a-zA-Z]{5}\d{4}[a-zA-Z][1-9A-Za-z]C[0-9a-zA-Z]/,
            ];

            isGST = allGSTinRe.some((re) => re.test(value));
        }

        return isGST;
    }

    function validateSearchTerm(request) {
        return Boolean(request) && request.length > 2;
    }

    async function autocomplete(value, queryCountryId) {
        value = value.trim();
        const isVAT = isVATNumber(value);
        if (isVAT) {
            value = sanitizeVAT(value);
        }
        const isGST = isGSTNumber(value);
        return getSuggestions(value, isVAT || isGST, queryCountryId);
    }

    /**
     * Build an AutoComplete source that queries the IAP autocomplete API and,
     * unless already searching worldwide, appends a "Search Worldwide" action
     * option (handled by PartnerAutoComplete.selectOption).
     *
     * @param {Object} params
     * @param {string} params.cssClass          css class for company option rows
     * @param {() => (number|false)} params.getCountryId  country scope for the query
     * @param {(suggestion: Object) => any} params.onSelectOption  company-select handler
     * @returns {Object} an AutoComplete source spec
     */
    function makeAutocompleteSource({ cssClass, getCountryId, onSelectOption }) {
        return {
            options: async (request, shouldSearchWorldwide) => {
                if (!validateSearchTerm(request)) {
                    return [];
                }
                const queryCountryId = shouldSearchWorldwide ? 0 : getCountryId();
                const suggestions = await autocomplete(request, queryCountryId);
                const options = suggestions.map((suggestion) => ({
                    cssClass,
                    data: suggestion,
                    label: suggestion.name,
                    onSelect: () => onSelectOption(suggestion),
                }));
                if (!shouldSearchWorldwide) {
                    options.push(worldwideOption());
                }
                return options;
            },
            optionSlot: "partnerOption",
            placeholder: _t("Searching Autocomplete..."),
        };
    }

    function worldwideOption() {
        return {
            cssClass: "partner_autocomplete_dropdown_worldwide",
            data: { isWorldwideAction: true },
            label: _t("Search Worldwide"),
        };
    }

    /**
     * Get enrichment data.
     *
     * @param {Object} company
     * @returns {Promise}
     */
    function enrichCompany(company) {
        if (isGSTNumber(company.query)) {
            return orm.call("res.partner", "enrich_by_gst", [company.query]);
        }
        return orm.call("res.partner", "enrich_by_duns", [company.duns]);
    }

    function removeUselessFields(company, fieldsToKeep) {
        const keep = new Set(fieldsToKeep);
        for (const field in company) {
            if (!keep.has(field)) {
                delete company[field];
            }
        }
        return company;
    }

    function stripInternalKeys(company) {
        const result = {};
        for (const [key, value] of Object.entries(company)) {
            if (!INTERNAL_KEYS.includes(key)) {
                result[key] = value;
            }
        }
        return result;
    }

    /**
     * Get enriched data + logo before populating partner form.
     *
     * @param {Object} company
     * @returns {Promise}
     */
    async function getCreateData(company) {
        let companyData = await enrichCompany(company);

        let isEnrichAccessible = false;
        if (companyData.error) {
            if (companyData.error_message === "Insufficient Credit") {
                notifyNoCredits();
            } else if (companyData.error_message === "No account token") {
                notifyAccountToken();
            } else {
                notification.add(companyData.error_message);
            }
            companyData = {
                ...company,
                ...companyData,
            };
        } else {
            isEnrichAccessible = true;
        }

        return {
            company: companyData,
            logo: companyData.logo || false,
            isEnrichAccessible,
        };
    }

    /**
     * Use Odoo Autocomplete API to return suggestions.
     *
     * @param {string} value
     * @param {boolean} isVAT
     * @param {number|false} queryCountryId
     * @returns {Promise}
     */
    async function getSuggestions(value, isVAT, queryCountryId) {
        const method = isVAT ? "autocomplete_by_vat" : "autocomplete_by_name";

        if (
            !isVAT &&
            lastNoResults &&
            lastNoResults.countryId === queryCountryId &&
            value.startsWith(lastNoResults.query)
        ) {
            return [];
        }

        const prom = orm.silent.call("res.partner", method, [value, queryCountryId]);

        const suggestions = await keepLastOdoo.add(prom);

        if (!isVAT && suggestions.length === 0) {
            lastNoResults = { query: value, countryId: queryCountryId };
        }

        for (const suggestion of suggestions) {
            suggestion.query = value;
            const parts = [];
            if (suggestion.city) {
                parts.push(suggestion.city);
            }
            if (queryCountryId === 0 && suggestion.country_id?.display_name) {
                parts.push(suggestion.country_id.display_name);
            }
            suggestion.description = parts.join(", ");
        }
        return suggestions;
    }

    /**
     * @returns {Promise}
     */
    async function notifyNoCredits() {
        const url = await orm.call("iap.account", "get_credits_url", [
            "partner_autocomplete",
        ]);
        const title = _t("Not enough credits for Partner Autocomplete");
        const content = renderToMarkup(
            "partner_autocomplete.InsufficientCreditNotification",
            {
                credits_url: url,
            },
        );
        notification.add(content, {
            title,
        });
    }

    async function notifyAccountToken() {
        const url = await orm.call("iap.account", "get_config_account_url", []);
        const title = _t("IAP Account Token missing");
        if (url) {
            const content = renderToMarkup(
                "partner_autocomplete.AccountTokenMissingNotification",
                {
                    account_url: url,
                },
            );
            notification.add(content, {
                title,
            });
        } else {
            notification.add(title);
        }
    }

    return {
        autocomplete,
        makeAutocompleteSource,
        getCreateData,
        removeUselessFields,
        stripInternalKeys,
    };
}
