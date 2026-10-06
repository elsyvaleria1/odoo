/** @odoo-module native */
import { rpc } from "@web/core/network";

export default class LazyBarcodeCache {
    constructor(cacheData, productsWithAllQuants = []) {
        this.dbIdCache = {}; // Cache by model + id
        this.dbBarcodeCache = {}; // Cache by model + barcode
        this.dbQuantCache = {}; // Cache by model + quant_id
        // Products whose internal quants were all fetched: a payload carrying some of a
        // product's quants (a package's, a location's) does not make its cache complete.
        this.productsWithAllQuants = new Set();
        // Set by a model that counts (inventory): every fetch then asks the server to complete
        // the quants of the products it answers with, whichever path fetches.
        this.completesQuants = false;
        this.missingBarcodesCache = new Set();
        this.missingBarcodeKeyCache = new Set(); // Used as a cache by `_getMissingRecord`
        this.barcodeFieldByModel = {
            "stock.location": "barcode",
            "product.product": "barcode",
            "product.uom": "barcode",
            "stock.package.type": "barcode",
            "stock.picking": "name",
            "stock.package": "name",
            "product.trace": "name", // Also ref, should take in account multiple fields ?
        };
        this.gs1LengthsByModel = {
            "product.product": 14,
            "product.uom": 14,
            "stock.location": 13,
            "stock.package": 18,
        };
        // If there is only one active barcode nomenclature, set the cache to be compliant with it.
        if (cacheData["barcode.nomenclature"].length === 1) {
            this.nomenclature = cacheData["barcode.nomenclature"][0];
        }
        this.setCache(cacheData);
        this._markProductsWithAllQuants(productsWithAllQuants);
        this.waitingFetch = [];
    }

    /**
     * Adds records to the barcode application's cache.
     *
     * @param {Object} cacheData each key is a model's name and contains an array of records.
     */
    setCache(cacheData) {
        for (const model in cacheData) {
            const records = cacheData[model];
            // Adds the model's key in the cache's DB.
            if (this.dbIdCache[model] === undefined) {
                this.dbIdCache[model] = {};
            }
            if (this.dbBarcodeCache[model] === undefined) {
                this.dbBarcodeCache[model] = {};
            }
            // Adds the record in the cache.
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
     * Get record from the cache, throw a error if we don't find in the cache
     * (the server should have return this information).
     *
     * @param {string} model model_name of the record
     * @param {int} id id of the record
     * @param {boolean} [raiseErrorIfMissing=true] throw if the record isn't cached instead of returning null
     * @returns copy of the record send by the server (fields limited to _get_fields_stock_barcode)
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

    /**
     * Caches a server answer. The server names the products whose every internal quant the
     * answer carries (`products_with_all_quants`): `getQuants` needs no RPC for those, and
     * nothing else marks a product so.
     */
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
        // `owner_id` was destructured raw while its two siblings were normalised, so callers
        // passing a record (barcode_quant_model does) compared an object against the cached id
        // and the filter below never matched anything.
        const owner_id = params.owner_id?.id || params.owner_id || false;
        const { lot_name } = params;
        if (!this.productsWithAllQuants.has(product.id)) {
            this.setBarcodeData(
                await rpc("/stock_barcode/get_quants", { product_ids: [product.id] }),
            );
        }
        // Keep an (empty) map, not an array: every other write to this cache keys it by
        // location id.
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
            // Return all product's quants in the given location.
            return quants;
        }
        // Return only the quant with the right lot, package, and/or owner, or no quant at all.
        if (trace_id) {
            quants = quants.filter((quant) => quant.trace_id === trace_id);
        } else if (lot_name) {
            // `filters` is a key of the options object, not the options object: passing it
            // directly left `options.filters` undefined, so the product constraint was dropped
            // and the lookup could return another product's lot of the same name.
            const filters = { "product.trace": { product_id: product.id } };
            const lot = await this.getRecordByBarcode(lot_name, "product.trace", {
                filters,
            });
            if (!lot) {
                // If there is no existing lot, there is no existing quant.
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
     * @param {string} barcode barcode to match with a record
     * @param {string} [model] model name of the record to match (if empty search on all models)
     * @param {Object} [options]
     * @param {boolean} [options.onlyInCache] search only in the cache
     * @param {Object} [options.filters]
     * @param {boolean} [options.fetchLater]
     * @returns copy of the record send by the server (fields limited to _get_fields_stock_barcode)
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
                        // If the model is a product, we can also try to fetch it as a packaging.
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
                        // If the model is a product, we can also try to fetch it as a packaging.
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
            // Cached, but for another product or company: the filtered record may still exist.
            if (!onlyInCache && Object.keys(filters).length) {
                await this._getMissingRecord(barcode, model, filters);
                return this.getRecordByBarcode(barcode, model, {
                    onlyInCache: true,
                    filters,
                });
            }
        } else {
            const result = new Map();
            // Returns object {model: record} of possible record.
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

    /**
     * Forget which barcodes were searched for and not found.
     *
     * Misses are remembered so that a mistyped or unknown barcode is not re-queried on every
     * scan, but the memory has no expiry: a record created after the page loaded — by a
     * colleague, or by this same user in another tab — stayed invisible for the rest of the
     * session, and the barcode app would keep sending its name as a new lot to create. Call
     * this whenever the client re-reads its data from the server, which is the point at which
     * the server's answer is known to be fresh.
     */
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
            // If we already tried to find the same model's record for the given barcode but
            // without the filters, there is no need to try again with the filter.
            const keyCacheWithoutFilters = JSON.stringify([barcode, model, {}]);
            if (missCache.has(keyCacheWithoutFilters)) {
                return false;
            }
        }
        // Check if we already try to fetch this missing record.
        if (missCache.has(keyCache) || missCache.has(keyCacheWithoutModel)) {
            return false;
        }
        const params = { fetch_quants: this.completesQuants };
        if (model) {
            params.barcodes_by_model = { [model]: [barcode] };
        } else {
            params.barcode = barcode;
        }
        // Creates and passes a domain if some filters are provided.
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
            return; // Nothing to fetch.
        }
        params.barcodes_by_model = {};
        params.fetch_quants = this.completesQuants;
        for (const data of this.waitingFetch) {
            const { barcode, model } = data;
            const keyCache = JSON.stringify([barcode, model, {}]);
            if (this.missingBarcodeKeyCache.has(keyCache)) {
                continue; // Avoid already fetched records.
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
                // Create a list of every found records' barcode.
                const foundBarcodes = [];
                const missingBarcodes = new Set();
                for (const model of Object.keys(result)) {
                    for (const record of result[model]) {
                        foundBarcodes.push(record[this.barcodeFieldByModel[model]]);
                    }
                }
                // Put every searched barcodes with no matching records into a set.
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
                // If there are barcodes with no match, make a second RPC but this
                // time, search for those barcodes with no assigned model.
                if (missingBarcodes.size) {
                    const barcodes = [...missingBarcodes];
                    // Keep in cache the fact those barcodes were search so they won't be in the future.
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
     * Sets in the cache an entry for the given record with its formatted barcode as key.
     * The barcode will be formatted (if needed) at the length corresponding to its data part in a
     * GS1 barcode (e.g.: 14 digits for a product's barcode) by padding with 0 the original barcode.
     * That makes it easier to find when a GS1 barcode is scanned.
     * If the formatted barcode is similar to an another barcode for the same model, it will show a
     * warning in the console (as a clue to find where issue could come from, not to alert the user)
     *
     * @param {string} barcode
     * @param {string} model
     * @param {Object} record
     */
    _setBarcodeInCacheForGS1(barcode, model, record) {
        const length = this.gs1LengthsByModel[model];
        if (!barcode || barcode.length >= length || isNaN(Number(barcode))) {
            // Barcode already has the good length, or is too long or isn't
            // fully numerical (and so, it doesn't make sense to adapt it).
            return;
        }
        const paddedBarcode = barcode.padStart(length, "0");
        // Avoids to override or mix records if there is already a key for this
        // barcode (which means there is a conflict somewhere).
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
