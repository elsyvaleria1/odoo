/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { SearchModel } from "@web/search/search_model";

/**
 * The agent names field searches as "field=text" strings.
 *
 * @param {{ filters?: string[], groupBys?: string[], fieldSearches?: string[], customDomain?: string }} aiSearch
 */
export function aiSearchSpec({ filters, groupBys, fieldSearches, customDomain }) {
    const searches = [];
    for (const searchString of fieldSearches || []) {
        const separatorIndex = searchString.indexOf("=");
        if (separatorIndex === -1) {
            console.warn(
                `Invalid search format: "${searchString}". Expected format: "field=text"`,
            );
            continue;
        }
        searches.push({
            fieldName: searchString.substring(0, separatorIndex),
            value: searchString.substring(separatorIndex + 1),
        });
    }
    return {
        filters: filters || [],
        groupBys: groupBys || [],
        fieldSearches: searches,
        customDomain,
    };
}

patch(SearchModel.prototype, {
    async load(config) {
        const result = await super.load(config);
        if (config.ai) {
            await this.applySearchSpec(
                aiSearchSpec({
                    filters: config.ai.selectedFilters,
                    groupBys: config.ai.selectedGroupBys,
                    fieldSearches: config.ai.search,
                    customDomain: config.ai.customDomain,
                }),
            );
        }
        return result;
    },
});
