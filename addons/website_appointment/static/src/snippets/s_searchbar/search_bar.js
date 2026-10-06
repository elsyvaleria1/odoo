/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { SearchBar } from "@website/snippets/s_searchbar/search_bar";

patch(SearchBar.prototype, {
    /**
     * @override
     */
    render(res) {
        if (res && this.searchType === "appointments" && res.parts.website_url) {
            res.results.forEach((result) => {
                result.website_url = `${result.website_url}${location.search}`;
            });
        }
        super.render(...arguments);
    },
});
