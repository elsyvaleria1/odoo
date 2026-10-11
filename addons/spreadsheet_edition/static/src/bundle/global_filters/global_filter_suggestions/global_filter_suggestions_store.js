/** @odoo-module native */
import { stores } from "@odoo/o-spreadsheet";
import { globalFieldMatchingRegistry } from "@spreadsheet/global_filters/helpers";
import { SearchArchParser } from "@web/search/search_arch_parser";

const { SpreadsheetStore } = stores;

export class GlobalFilterSuggestionsStore extends SpreadsheetStore {
    _suggestionsPromise = undefined;

    constructor(get) {
        super(get);
        this.searchFilters = get(SearchFiltersStore);
        this.env = this.model.config.custom.env;
    }

    get suggestionsPromise() {
        if (!this._suggestionsPromise) {
            this._suggestionsPromise = this._getGlobalFilterSuggestions();
        }
        return this._suggestionsPromise;
    }

    /**
     * @private
     */
    async _getGlobalFilterSuggestions() {
        const [searchFiltersPerModels] = await Promise.all([
            this.searchFilters.searchFiltersPromise,
            this._loadAllMetaData(),
        ]);
        const dataSourceModels = new Set();
        for (const matcher of globalFieldMatchingRegistry.getAll()) {
            for (const dataSourceId of matcher.getIds(this.getters)) {
                const model = matcher.getModel(this.getters, dataSourceId);
                dataSourceModels.add(model);
            }
        }
        if (dataSourceModels.size !== Object.keys(searchFiltersPerModels).length) {
            return [];
        }
        const suggestedRelations =
            await this._getSuggestedRelations(searchFiltersPerModels);
        if (suggestedRelations.length === 0) {
            return [];
        }

        const modelDisplayNames = await this._getModelDisplayNames(
            suggestedRelations.map(({ relation }) => relation),
        );

        const suggestions = [];
        for (const { relation, matchingFields } of suggestedRelations) {
            const fieldMatching = {};
            let filterLabel = "";
            for (const matcher of globalFieldMatchingRegistry.getAll()) {
                for (const dataSourceId of matcher.getIds(this.getters)) {
                    const model = matcher.getModel(this.getters, dataSourceId);
                    const fields = matcher.getFields(this.getters, dataSourceId);
                    const matchingField = matchingFields[model]?.values().next().value;
                    fieldMatching[model] = {
                        chain: matchingField,
                        type: fields[matchingField]?.type,
                    };
                    filterLabel =
                        searchFiltersPerModels[model][matchingField].description;
                }
            }
            suggestions.push({
                modelName: relation,
                modelDisplayName: modelDisplayNames[relation],
                label: filterLabel,
                fieldMatching,
            });
        }
        return suggestions;
    }

    async _loadAllMetaData() {
        const promises = globalFieldMatchingRegistry
            .getAll()
            .flatMap((matcher) =>
                matcher
                    .getIds(this.getters)
                    .map((dataSourceId) =>
                        matcher.waitForReady(this.getters, dataSourceId),
                    ),
            );
        return Promise.all(promises);
    }

    /**
     * @private
     * @param {string[]} models
     * @returns {Promise<Record<string, string>>}
     */
    async _getModelDisplayNames(models) {
        const result = await this.env.services.orm
            .cache({ type: "disk" })
            .call("ir.model", "display_name_for", [models]);
        return Object.fromEntries(
            result.map(({ model, display_name }) => [model, display_name]),
        );
    }

    /**
     * @private
     */
    async _getSuggestedRelations(searchFiltersPerModels) {
        const relationsToDataSources = {};
        for (const dataSourceModel in searchFiltersPerModels) {
            const fields = await this.env.services.field.loadFields(dataSourceModel);
            for (const fieldName in searchFiltersPerModels[dataSourceModel]) {
                const relation = fields[fieldName]?.relation;
                if (!relationsToDataSources[relation]) {
                    relationsToDataSources[relation] = {};
                }
                if (!relationsToDataSources[relation][dataSourceModel]) {
                    relationsToDataSources[relation][dataSourceModel] = new Set();
                }
                relationsToDataSources[relation][dataSourceModel].add(fieldName);
            }
        }

        const existingFilters = new Set(
            this.getters
                .getGlobalFilters()
                .filter((filter) => filter.type === "relation")
                .map((filter) => filter.modelName),
        );
        const numberOfDataSourceModels = Object.keys(searchFiltersPerModels).length;
        const validRelations = [];
        for (const relation in relationsToDataSources) {
            const matchingDataSourceModels = Object.keys(
                relationsToDataSources[relation],
            );
            const numberOfMatchingFields = Object.values(
                relationsToDataSources[relation],
            )
                .map((fields) => fields.size)
                .reduce((acc, val) => acc + val, 0);
            if (
                matchingDataSourceModels.length === numberOfDataSourceModels &&
                numberOfMatchingFields === numberOfDataSourceModels &&
                !existingFilters.has(relation)
            ) {
                const matchingFields = relationsToDataSources[relation];
                validRelations.push({ relation, matchingFields });
            }
        }
        return validRelations;
    }
}

class SearchFiltersStore extends SpreadsheetStore {
    constructor(get) {
        super(get);
        this.env = this.model.config.custom.env;
    }

    get searchFiltersPromise() {
        if (!this._searchFiltersPromise) {
            this._searchFiltersPromise = this._getSearchFiltersPerModels();
        }
        return this._searchFiltersPromise;
    }

    /**
     * @private
     * @returns {string[]}
     */
    _getAllActionXmlIds() {
        const xmlIds = new Set();
        for (const matcher of globalFieldMatchingRegistry.getAll()) {
            for (const dataSourceId of matcher.getIds(this.getters)) {
                const actionXmlId = matcher.getActionXmlId(this.getters, dataSourceId);
                if (actionXmlId) {
                    xmlIds.add(actionXmlId);
                }
            }
        }
        return Array.from(xmlIds);
    }

    /**
     * @private
     * @param {string} model
     * @param {string} arch
     * @returns {Promise<Record<string, object>>}
     */
    async _getRelationalFiltersFromArch(model, arch) {
        const blackList = ["activity_user_id", "activity_type_id"];
        const fields = await this.env.services.field.loadFields(model);
        const parsedArch = new SearchArchParser({ arch }, fields, {}).parse();
        const relationalFilters = parsedArch.preSearchItems
            .flat()
            .filter(
                (item) =>
                    !blackList.includes(item.fieldName) &&
                    item.type === "field" &&
                    ["many2one", "many2many", "one2many"].includes(item.fieldType) &&
                    (!item.filterDomain ||
                        item.filterDomain.includes(`'${item.fieldName}'`) ||
                        item.filterDomain.includes(`"${item.fieldName}"`)),
            );
        const result = {};
        for (const filter of relationalFilters) {
            result[filter.fieldName] = filter;
        }
        return result;
    }

    /**
     * @private
     */
    async _getSearchFiltersPerModels() {
        const xmlIds = this._getAllActionXmlIds();
        if (xmlIds.length === 0) {
            return {};
        }
        const views = await this.env.services.orm.call(
            "mixin.spreadsheet",
            "get_search_view_archs",
            [xmlIds],
        );
        const searchFiltersPerModels = {};
        for (const model in views) {
            const archs = views[model];
            for (const arch of archs) {
                searchFiltersPerModels[model] = {
                    ...searchFiltersPerModels[model],
                    ...(await this._getRelationalFiltersFromArch(model, arch)),
                };
            }
        }
        return searchFiltersPerModels;
    }
}
