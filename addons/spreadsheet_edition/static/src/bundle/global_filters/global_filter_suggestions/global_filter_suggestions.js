/** @odoo-module native */
import { components, stores } from "@odoo/o-spreadsheet";
import { Component, onWillStart, useProps } from "@odoo/owl";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";

import { GlobalFilterSuggestionsStore } from "./global_filter_suggestions_store.js";

const { Section } = components;
const { useLocalStore } = stores;

export class GlobalFilterSuggestions extends Component {
    static template = "spreadsheet_edition.GlobalFilterSuggestions";
    static components = { Section };
    static props = {};
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    setup() {
        const store = useLocalStore(GlobalFilterSuggestionsStore);
        onWillStart(async () => {
            this.suggestions = await store.suggestionsPromise;
        });
    }

    onSuggestionClick(suggestion) {
        this.env.openSidePanel("RELATION_FILTER_SIDE_PANEL", {
            label: suggestion.label,
            modelName: suggestion.modelName,
            modelDisplayName: suggestion.modelDisplayName,
            fieldMatching: suggestion.fieldMatching,
        });
    }
}
