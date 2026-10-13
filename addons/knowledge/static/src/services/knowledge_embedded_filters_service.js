/** @odoo-module native */
import { registry } from "@web/core/registry";

/**
 * @function
 * @function
 */
export const knowledgeEmbedViewsFilters = {
    start() {
        const embeddedFilters = {};
        const commands = {
            /**
             * @param {*} currentController
             * @param {String} filterKey
             * @param {Object} searchModel
             */
            saveFilters: (currentController, filterKey, searchModel) => {
                if (!embeddedFilters[filterKey]) {
                    embeddedFilters[filterKey] = {};
                }
                embeddedFilters[filterKey][currentController.jsId] = searchModel;
            },
            /**
             * @param {*} currentController
             * @param {String} filterKey
             * @param {*} ViewProps
             */
            applyFilter: (currentController, filterKey, ViewProps) => {
                const currentJsId = currentController.jsId;
                const embedSearchFilters = embeddedFilters[filterKey];

                if (embedSearchFilters && embedSearchFilters[currentJsId]) {
                    ViewProps.globalState.searchModel =
                        embeddedFilters[filterKey][currentJsId];
                    delete embeddedFilters[filterKey][currentJsId];
                }

                if (currentController.config.breadcrumbs.length === 1) {
                    delete embeddedFilters[filterKey];
                }
            },
        };
        return commands;
    },
};

registry
    .category("services")
    .add("knowledgeEmbedViewsFilters", knowledgeEmbedViewsFilters);
