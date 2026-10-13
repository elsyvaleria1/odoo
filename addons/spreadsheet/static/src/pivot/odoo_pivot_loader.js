/** @odoo-module native */
//@ts-check

import { getFields, LoadableDataSource } from "@spreadsheet/data_sources/data_source";

/**
 * @typedef {import("@spreadsheet").OdooFields} OdooFields
 * @typedef {import("@spreadsheet/data_sources/odoo_data_provider").OdooDataProvider} OdooDataProvider
 */

export class OdooPivotLoader extends LoadableDataSource {
    /**
     * @param {OdooDataProvider} odooDataProvider
     * @param {Function} load
     */
    constructor(odooDataProvider, load) {
        super({ odooDataProvider });
        /** @protected */
        this.loadFn = load;
    }

    /**
     * @protected
     */
    async _load() {
        return this.loadFn();
    }

    /**
     * @param {string} model
     * @returns {Promise<OdooFields>}
     */
    async getFields(model) {
        return getFields(this.odooDataProvider.fieldService, model);
    }
    /**
     * @param {string} model
     * @returns {Promise<string>}
     */
    async getModelLabel(model) {
        const result = await this.odooDataProvider.orm
            .cache({ type: "disk" })
            .call("ir.model", "display_name_for", [[model]]);
        return result[0]?.display_name || "";
    }

    hasEverBeenLoaded() {
        return this._loadPromise !== undefined;
    }
}
