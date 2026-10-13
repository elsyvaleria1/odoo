/** @odoo-module native */
import { rpc } from "@web/core/network";

export default class LazyBarcodeCache {
    constructor(cacheData, productsWithAllQuants = []) {
        this.dbIdCache = {};
        this.dbBarcodeCache = {};
        this.dbQuantCache = {};
        this.productsWithAllQuants = new Set();
        this.completesQuants = false;
        this.missingBarcodesCache = new Set();
        this.missingBarcodeKeyCache = new Set();
        this.barcodeFieldByModel = {
            "stock.location": "barcode",
            "product.product": "barcode",
            "product.uom": "barcode",
            "stock.package.type": "barcode",
            "stock.picking": "name",
            "stock.package": "name",
            "product.trace": "name",
        };
        this.gs1LengthsByModel = {
            "product.product": 14,
            "product.uom": 14,
            "stock.location": 13,
            "stock.package": 18,
        };
        if (cacheData["barcode.nomenclature"].length === 1) {
            this.nomenclature = cacheData["barcode.nomenclature"][0];
        }
        this.setCache(cacheData);
        this._markProductsWithAllQuants(productsWithAllQuants);
        this.waitingFetch = [];
    }

    /** @param {Object} cacheData */
    setCache(cacheData) {
        for (const model in cacheData) {
            const records = cacheData[model];
            if (this.dbIdCache[model] === undefined) {
                this.dbIdCache[model] = {};
            }
            if (this.dbBarcodeCache[model] === undefined) {
                this.dbBarcodeCache[model] = {};
            }
            const barcodeField = this._getBarcodeField(model);
            for (const record of records) {
                this.dbIdCache[model][record.id] = record;
                if (model === "stock.quant") {
                    const { product_id, location_id } = record;
                    if (!this.dbQuantCache[product_id]) {
                        this.dbQuantCache[product_id] = {};
                    }
                    if (!this.dbQuantCache[product_id][location_id]) {
                        this.dbQuantCache[product_id][location_id] = [];
                    }
                    const matchIndex = this.dbQuantCache[product_id][
                        location_id
                    ].findIndex((rec) => rec.id === record.id);
                    if (matchIndex !== -1) {
                        this.dbQuantCache[product_id][location_id][matchIndex] = record;
                    } else {
                        this.dbQuantCache[product_id][location_id].push(record);
                    }
                }
                if (barcodeField) {
                    const barcode = record[barcodeField];
                    if (!this.dbBarcodeCache[model][barcode]) {
                        this.dbBarcodeCache[model][barcode] = [];
                    }
                    if (!this.dbBarcodeCache[model][barcode].includes(record.id)) {
                        this.dbBarcodeCache[model][barcode].push(record.id);
                        if (
                            this.nomenclature &&
                            this.nomenclature.is_gs1_nomenclature &&
                            this.gs1LengthsByModel[model]
                        ) {
                            this._setBarcodeInCacheForGS1(barcode, model, record);
                        }
                    }
                }
            }
        }
    }

    /**
     * @param {string} model
     * @param {int} id
     * @param {boolean} [raiseErrorIfMissing=true]
     * @returns
     */
    getRecord(model, id, raiseErrorIfMissing = true) {
        if (this.dbIdCache[model] === undefined) {
            if (raiseErrorIfMissing) {
                throw new Error(`Model ${model} doesn't exist in the cache`);
            }
            return null;
        }
        if (this.dbIdCache[model][id] === undefined) {
            if (raiseErrorIfMissing) {
                throw new Error(
                    `Record ${model} with id=${id} doesn't exist in the cache, it should return by the server`,
                );
            }
            return null;
        }
        const record = this.dbIdCache[model][id];
        return JSON.parse(JSON.stringify(record));
    }

    setBarcodeData({ records, products_with_all_quants: productIds = [] }) {
        this.setCache(records);
        this._markProductsWithAllQuants(productIds);
        return records;
    }

    _markProductsWithAllQuants(productIds) {
        for (const productId of productIds) {
            this.productsWithAllQuants.add(productId);
        }
    }

    async getQuants(product, location_id, params = {}) {
        const trace_id = params.trace_id?.id || params.trace_id || false;
        const package_id = params.package_id?.id || params.package_id || false;
        const owner_id = params.owner_id?.id || params.owner_id || false;
        const { lot_name } = params;
        if (!this.productsWithAllQuants.has(product.id)) {
            this.setBarcodeData(
                await rpc("/stock_barcode/get_quants", { product_ids: [product.id] }),
            );
        }
        this.dbQuantCache[product.id] ||= {};
        const quantsByProduct = this.dbQuantCache[product.id];
        let quants = [];
        if (location_id) {
            const quantsByLocation = quantsByProduct[location_id];
            if (quantsByLocation) {
                quants.push(...quantsByLocation);
            } else {
                this.dbQuantCache[product.id][location_id] = [];
            }
        } else {
            for (const quantsByLocation of Object.values(quantsByProduct)) {
                quants.push(...quantsByLocation);
            }
        }
        if (!trace_id && !lot_name && !package_id && !owner_id) {
            return quants;
        }
        if (trace_id) {
            quants = quants.filter((quant) => quant.trace_id === trace_id);
        } else if (lot_name) {
            const filters = { "product.trace": { product_id: product.id } };
            const lot = await this.getRecordByBarcode(lot_name, "product.trace", {
                filters,
            });
            if (!lot) {
                return [];
            }
            quants = quants.filter((quant) => quant.trace_id === lot.id);
        }
        if (owner_id) {
            quants = quants.filter((quant) => quant.owner_id === owner_id);
        }
        if (package_id) {
            quants = quants.filter((quant) => quant.package_id === package_id);
        }
        return quants;
    }

    /**
     * @param {string} barcode
     * @param {string} [model]
     * @param {Object} [options]
     * @param {boolean} [options.onlyInCache]
     * @param {Object} [options.filters]
     * @param {boolean} [options.fetchLater]
     * @returns
     */
    async getRecordByBarcode(barcode, model = false, options = {}) {
        const onlyInCache = Boolean(options.onlyInCache);
        const filters = options.filters || {};
        const fetchLater = Boolean(options.fetchLater);
        if (model) {
            if (this.dbBarcodeCache[model] === undefined) {
                if (fetchLater) {
                    this.waitingFetch.push({ barcode, model, options });
                    if (model === "product.product") {
                        this.waitingFetch.push({
                            barcode,
                            model: "product.uom",
                            options,
                        });
                    }
                    return null;
                }
                if (onlyInCache) {
                    return null;
                }
                throw new Error(`Model ${model} doesn't exist in the cache`);
            }
            if (this.dbBarcodeCache[model][barcode] === undefined) {
                if (fetchLater) {
                    this.waitingFetch.push({ barcode, model, options });
                    if (model === "product.product") {
                        this.waitingFetch.push({
                            barcode,
                            model: "product.uom",
                            options,
                        });
                    }
                    return null;
                }
                if (onlyInCache) {
                    return null;
                }
                await this._getMissingRecord(barcode, model, filters);
                return await this.getRecordByBarcode(barcode, model, {
                    onlyInCache: true,
                    filters,
                });
            }
            const ids = this.dbBarcodeCache[model][barcode];
            for (const id of ids) {
                const record = this.getRecord(model, id);
                let pass = true;
                if (filters[model]) {
                    const fields = Object.keys(filters[model]);
                    for (const field of fields) {
                        if (record[field] !== filters[model][field]) {
                            pass = false;
                            break;
                        }
                    }
                }
                if (pass) {
                    return record;
                }
            }
            if (!onlyInCache && Object.keys(filters).length) {
                await this._getMissingRecord(barcode, model, filters);
                return this.getRecordByBarcode(barcode, model, {
                    onlyInCache: true,
                    filters,
                });
            }
        } else {
            const result = new Map();
            const models = Object.keys(this.dbBarcodeCache);
            for (const model of models) {
                if (this.dbBarcodeCache[model][barcode]) {
                    const ids = this.dbBarcodeCache[model][barcode];
                    for (const id of ids) {
                        const record = this.dbIdCache[model][id];
                        let pass = true;
                        if (filters[model]) {
                            const fields = Object.keys(filters[model]);
                            for (const field of fields) {
                                if (record[field] !== filters[model][field]) {
                                    pass = false;
                                    break;
                                }
                            }
                        }
                        if (pass) {
                            result.set(model, JSON.parse(JSON.stringify(record)));
                            break;
                        }
                    }
                }
            }
            if (result.size < 1) {
                if (onlyInCache) {
                    return result;
                }
                await this._getMissingRecord(barcode, model, filters);
                return await this.getRecordByBarcode(barcode, model, {
                    onlyInCache: true,
                    filters,
                });
            }
            return result;
        }
    }

    forgetMissingBarcodes() {
        this.missingBarcodeKeyCache.clear();
        this.missingBarcodesCache.clear();
    }

    _getBarcodeField(model) {
        if (this.barcodeFieldByModel[model] === undefined) {
            return null;
        }
        return this.barcodeFieldByModel[model];
    }

    async _getMissingRecord(barcode, model, filters = {}) {
        const keyCache = JSON.stringify([...arguments]);
        const missCache = this.missingBarcodeKeyCache;
        const keyCacheWithoutModel = JSON.stringify([barcode, false, {}]);
        if (Object.keys(filters).length) {
            const keyCacheWithoutFilters = JSON.stringify([barcode, model, {}]);
            if (missCache.has(keyCacheWithoutFilters)) {
                return false;
            }
        }
        if (missCache.has(keyCache) || missCache.has(keyCacheWithoutModel)) {
            return false;
        }
        const params = { fetch_quants: this.completesQuants };
        if (model) {
            params.barcodes_by_model = { [model]: [barcode] };
        } else {
            params.barcode = barcode;
        }
        const domainsByModel = {};
        for (const filter of Object.entries(filters)) {
            const modelName = filter[0];
            const filtersByField = filter[1];
            domainsByModel[modelName] = [];
            for (const filterByField of Object.entries(filtersByField)) {
                if (filterByField[1] instanceof Array) {
                    domainsByModel[modelName].push([
                        filterByField[0],
                        "in",
                        filterByField[1],
                    ]);
                } else {
                    domainsByModel[modelName].push([
                        filterByField[0],
                        "=",
                        filterByField[1],
                    ]);
                }
            }
        }
        params.domains_by_model = domainsByModel;
        this.setBarcodeData(
            await rpc("/stock_barcode/get_specific_barcode_data", params),
        );
        missCache.add(keyCache);
    }

    async getMissingRecords(params = {}) {
        if (!this.waitingFetch.length) {
            return;
        }
        params.barcodes_by_model = {};
        params.fetch_quants = this.completesQuants;
        for (const data of this.waitingFetch) {
            const { barcode, model } = data;
            const keyCache = JSON.stringify([barcode, model, {}]);
            if (this.missingBarcodeKeyCache.has(keyCache)) {
                continue;
            }
            this.missingBarcodeKeyCache.add(keyCache);
            if (!params.barcodes_by_model[model]) {
                params.barcodes_by_model[model] = [];
            }
            params.barcodes_by_model[model].push(barcode);
        }
        if (Object.keys(params.barcodes_by_model).length) {
            const result = this.setBarcodeData(
                await rpc("/stock_barcode/get_specific_barcode_data", params),
            );
            if (params.forceUnrestrictedSearch) {
                const foundBarcodes = [];
                const missingBarcodes = new Set();
                for (const model of Object.keys(result)) {
                    for (const record of result[model]) {
                        foundBarcodes.push(record[this.barcodeFieldByModel[model]]);
                    }
                }
                for (const model of Object.keys(params.barcodes_by_model)) {
                    for (const barcode of params.barcodes_by_model[model]) {
                        if (
                            !foundBarcodes.includes(barcode) &&
                            !this.missingBarcodesCache.has(barcode)
                        ) {
                            missingBarcodes.add(barcode);
                            this.missingBarcodesCache.add(barcode);
                        }
                    }
                }
                if (missingBarcodes.size) {
                    const barcodes = [...missingBarcodes];
                    for (const bc of barcodes) {
                        this.missingBarcodeKeyCache.add(
                            JSON.stringify([bc, false, {}]),
                        );
                    }
                    const updatedParams = { ...params, barcodes };
                    delete updatedParams.barcodes_by_model;
                    this.setBarcodeData(
                        await rpc(
                            "/stock_barcode/get_specific_barcode_data",
                            updatedParams,
                        ),
                    );
                }
            }
        }
        this.waitingFetch = [];
    }

    /**
     * @param {string} barcode
     * @param {string} model
     * @param {Object} record
     */
    _setBarcodeInCacheForGS1(barcode, model, record) {
        const length = this.gs1LengthsByModel[model];
        if (!barcode || barcode.length >= length || isNaN(Number(barcode))) {
            return;
        }
        const paddedBarcode = barcode.padStart(length, "0");
        if (!this.dbBarcodeCache[model][paddedBarcode]) {
            this.dbBarcodeCache[model][paddedBarcode] = [record.id];
        } else if (!this.dbBarcodeCache[model][paddedBarcode].includes(record.id)) {
            const previousRecordId = this.dbBarcodeCache[model][paddedBarcode][0];
            const previousRecord = this.getRecord(model, previousRecordId);
            console.warn(
                `Conflict for barcode %c${paddedBarcode}%c:`,
                "font-weight: bold",
                "",
                `it could refer for both ${record.display_name} and ${previousRecord.display_name}.`,
                `\nThe first one is used; consider editing those barcodes to remove the ambiguity.`,
            );
        }
    }
}
