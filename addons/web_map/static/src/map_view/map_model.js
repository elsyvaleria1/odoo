/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import {
    deserializeDateTime,
    formatValue,
    parseDate,
    parseDateTime,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { KeepLast } from "@web/core/utils/concurrency";
import { orderByToString } from "@web/core/utils/order_by";
import { Model } from "@web/model/model";
import { resequenceRecords } from "@web/model/relational_model";
import { session } from "@web/session";

const DATE_GROUP_FORMATS = {
    hour: "HH:00 dd MMM yyyy",
    day: "dd MMM yyyy",
    week: "'W'WW yyyy",
    month: "MMMM yyyy",
    quarter: "'Q'q yyyy",
    year: "yyyy",
};

const SERVER_DATETIME_FORMAT = "yyyy-MM-dd HH:mm:ss";

const MAP_BOX_MAX_ROUTE_POINTS = 25;

/**
 * @param {Object} [partner]
 * @returns {boolean}
 */
export function hasCoordinates(partner) {
    if (!partner) {
        return false;
    }
    const latitude = partner.partner_latitude;
    const longitude = partner.partner_longitude;
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
        return false;
    }
    if (latitude === 0 && longitude === 0) {
        return false;
    }
    return Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180;
}

let nextRevision = 1;

function makeMapData(metaData = {}) {
    const groupBy = metaData.groupBy || [];
    return proxy({
        revision: nextRevision++,
        count: 0,
        fetchingCoordinates: false,
        groupByKey: groupBy.length ? groupBy[0] : false,
        isGrouped: groupBy.length > 0,
        partners: {},
        partnersToSave: [],
        recordGroups: {},
        records: [],
        routes: [],
        routingError: null,
        shouldUpdatePosition: true,
        useMapBoxAPI: !!metaData.mapBoxToken,
    });
}

const log = makeLogger("map.model");

export class MapModel extends Model {
    setup(params, { notification }) {
        this.notification = notification;

        this.metaData = {
            ...params,
            mapBoxToken: session.map_box_token || "",
        };
        this.data = makeMapData(this.metaData);

        this.coordinateFetchingTimeoutHandle = undefined;
        this.shouldFetchCoordinates = false;
        this.keepLast = new KeepLast();
        this.keepLastGeocoding = new KeepLast();
    }
    /**
     * @param {any} params
     * @returns {Promise<void>}
     */
    async load(params) {
        if (this.coordinateFetchingTimeoutHandle !== undefined) {
            this.stopFetchingCoordinates();
        }
        const metaData = {
            ...this.metaData,
            ...params,
        };

        metaData.groupBy = (metaData.groupBy || []).filter((groupBy) => {
            const [fieldName] = groupBy.split(".");
            const field = metaData.fields[fieldName];
            return field?.type !== "properties";
        });

        log.pipeline("load", () => ({
            resModel: metaData.resModel,
            groupBy: metaData.groupBy,
            domain: metaData.domain,
            limit: metaData.limit,
            offset: metaData.offset,
            routing: metaData.routing,
        }));
        const endLoad = log.perf(`load ${metaData.resModel}`);
        this.data = await this._fetchData(metaData);
        endLoad({
            records: this.data.records?.length,
            partners: Object.keys(this.data.partners || {}).length,
            count: this.data.count,
        });
        this.metaData = metaData;

        this.notify();
    }
    stopFetchingCoordinates() {
        browser.clearTimeout(this.coordinateFetchingTimeoutHandle);
        this.coordinateFetchingTimeoutHandle = undefined;
        this.shouldFetchCoordinates = false;
    }

    get canResequence() {
        const [defaultOrder] = this.metaData.defaultOrder || [];
        const field = defaultOrder && this.metaData.fields[defaultOrder.name];
        return Boolean(
            field &&
            !field.readonly &&
            field.type === "integer" &&
            this.metaData.allowResequence &&
            !this.metaData.groupBy?.length,
        );
    }

    /** @returns {boolean} */
    hasData() {
        return this.data.count > 0;
    }

    /** @returns {Record<string, Record<string, any>>} */
    getSampleRelatedModels() {
        return {
            "res.partner": {
                contact_address_complete: { type: "char" },
                partner_latitude: { type: "float" },
                partner_longitude: { type: "float" },
            },
        };
    }

    get locatedRecordCount() {
        return this._getLocatedRecordCount(this.data);
    }

    /**
     * @param {Number} movedId
     * @param {Number} targetId
     */
    async resequence(movedId, targetId) {
        log.logic("resequence", () => ({ movedId, targetId }));
        const fieldName = this.metaData.defaultOrder[0].name;
        const asc = this.metaData.defaultOrder[0].asc;
        const resequenceProm = resequenceRecords({
            records: this.data.records,
            resModel: this.metaData.resModel,
            movedId,
            targetId,
            fieldName,
            asc,
            context: this.metaData.context,
            orm: this.orm,
        });
        this.notify();
        const resequencedRecords = await resequenceProm;
        if (resequencedRecords.length) {
            for (const resequencedRecord of resequencedRecords) {
                const record = this.data.records.find(
                    (r) => r.id === resequencedRecord.id,
                );
                record[fieldName] = resequencedRecord[fieldName];
            }
            await this._loadRoute(this.metaData, this.data);
            this.notify();
        }
    }

    /** @protected */
    _addPartnerToRecord(metaData, data) {
        for (const record of data.records) {
            const partnerId =
                metaData.resModel === "res.partner" && metaData.resPartnerField === "id"
                    ? record.id
                    : record[metaData.resPartnerField]?.id;
            record.partner = partnerId ? data.partners[partnerId] : undefined;
        }
    }

    /**
     * @protected
     * @param {any} metaData
     * @return {Promise<any>}
     */
    async _fetchData(metaData) {
        const data = makeMapData(metaData);

        if (!metaData.resPartnerField) {
            return this.keepLast.add(Promise.resolve(data));
        }
        const results = await this.keepLast.add(this._fetchRecordData(metaData, data));

        const datetimeFields = metaData.fieldNames.filter(
            (name) => metaData.fields[name].type === "datetime",
        );
        for (const record of results.records) {
            for (const field of datetimeFields) {
                if (record[field]) {
                    record[field] = formatValue(
                        deserializeDateTime(record[field]),
                        SERVER_DATETIME_FORMAT,
                    );
                }
            }
        }

        data.records = results.records;
        data.count = results.length;
        if (data.isGrouped) {
            data.recordGroups = await this._getRecordGroups(metaData, data);
        }

        if (metaData.resModel === "res.partner" && metaData.resPartnerField === "id") {
            for (const record of data.records) {
                if (!data.partners[record.id]) {
                    data.partners[record.id] = { ...record };
                }
            }
        } else {
            for (const record of data.records) {
                const partner = record[metaData.resPartnerField];
                if (partner && !data.partners[partner.id]) {
                    data.partners[partner.id] = partner;
                }
            }
        }
        this._addPartnerToRecord(metaData, data);
        await this._updatePartnerCoordinate(metaData, data);
        return data;
    }

    _getRecordSpecification(metaData, data) {
        const fieldNames = data.groupByKey
            ? metaData.fieldNames.concat(data.groupByKey.split(":")[0])
            : metaData.fieldNames;
        const specification = {};
        const fieldsToAdd = {
            contact_address_complete: {},
            partner_latitude: {},
            partner_longitude: {},
        };
        for (const fieldName of fieldNames) {
            specification[fieldName] = {};
            if (fieldName === "id" && metaData.resPartnerField === "id") {
                Object.assign(specification, fieldsToAdd);
            } else if (
                ["many2one", "one2many", "many2many"].includes(
                    metaData.fields[fieldName].type,
                )
            ) {
                specification[fieldName].fields = { display_name: {} };
                if (fieldName === metaData.resPartnerField) {
                    Object.assign(specification[fieldName].fields, fieldsToAdd);
                }
            }
        }
        return specification;
    }

    /**
     * @protected
     * @returns {Promise}
     */
    _fetchRecordData(metaData, data) {
        const specification = this._getRecordSpecification(metaData, data);
        return this.orm.webSearchRead(metaData.resModel, metaData.domain, {
            specification,
            limit: metaData.limit,
            offset: metaData.offset,
            order: orderByToString(metaData.defaultOrder || []),
            context: metaData.context,
        });
    }

    /**
     * @protected
     * @param {string} url
     * @returns {Promise<Object>}
     */
    async _getJson(url) {
        const endGet = log.perf("geocode fetch");
        const response = await browser.fetch(url, { method: "GET" });
        endGet({
            status: response.status,
            host: new URL(url, browser.location.origin).host,
        });
        let payload;
        try {
            payload = await response.json();
        } catch {
            payload = {};
        }
        if (!response.ok) {
            const error = new Error(
                payload.message || `HTTP ${response.status} at "${url}"`,
            );
            error.status = response.status;
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    /**
     * @protected
     * @param {Object} record
     * @returns {Promise}
     */
    _fetchCoordinatesFromAddressMB(metaData, data, record) {
        const address = encodeURIComponent(record.contact_address_complete);
        const token = metaData.mapBoxToken;
        const encodedUrl = `https://api.mapbox.com/geocoding/v5/mapbox.places/${address}.json?access_token=${token}&cachebuster=${Date.now()}&autocomplete=true`;
        return this._fetchMapBox(encodedUrl);
    }

    /**
     * @protected
     * @param {string} url
     * @returns {Promise}
     */
    async _fetchMapBox(url) {
        const response = await browser.fetch(url);
        if (!response.ok) {
            const error = new Error(`HTTP ${response.status} response at "${url}"`);
            error.status = response.status;
            try {
                error.responseJSON = await response.json();
            } catch {
                error.responseJSON = null;
            }
            throw error;
        }
        return response.json();
    }

    /**
     * @protected
     * @param {Object} record
     * @returns {Promise}
     */
    _fetchCoordinatesFromAddressOSM(metaData, data, record) {
        const address = encodeURIComponent(
            record.contact_address_complete.replaceAll("/", " "),
        );
        const encodedUrl = `https://nominatim.openstreetmap.org/search?q=${address}&format=jsonv2`;
        return this._getJson(encodedUrl);
    }

    /**
     * @protected
     * @returns {Promise}
     */
    _fetchRoute(metaData, data) {
        const address = encodeURIComponent(this._getRouteCoordinates(data).join(";"));
        const token = metaData.mapBoxToken;
        const encodedUrl = `https://api.mapbox.com/directions/v5/mapbox/driving/${address}?access_token=${token}&steps=true&geometries=geojson`;
        return this._getJson(encodedUrl);
    }

    /**
     * @protected
     * @param {Object} data
     * @returns {string[]}
     */
    _getRouteCoordinates(data) {
        return data.records
            .filter((record) => hasCoordinates(record.partner))
            .map(
                ({ partner }) =>
                    `${partner.partner_longitude},${partner.partner_latitude}`,
            );
    }

    /**
     * @protected
     * @param {string} message
     * @returns {string}
     */
    _getErrorMessage(message) {
        const ERROR_MESSAGES = {
            "Too many coordinates; maximum number of coordinates is 25": _t(
                "Too many routing points (maximum 25)",
            ),
            "Route exceeds maximum distance limitation": _t(
                "Some routing points are too far apart",
            ),
            "Too Many Requests": _t("Too many requests, try again in a few minutes"),
        };
        return ERROR_MESSAGES[message] || message;
    }

    /**
     * @protected
     * @returns {Object}
     */
    async _getRecordGroups(metaData, data) {
        const [fieldName, subGroup] = data.groupByKey.split(":");
        const fieldType = metaData.fields[fieldName].type;
        const unsetName = metaData.fields[fieldName].falsy_value_label || _t("None");
        const groups = {};
        function addToGroup(id, name, record) {
            if (!groups[id]) {
                groups[id] = {
                    name,
                    records: [],
                };
            }
            groups[id].records.push(record);
        }
        for (const record of data.records) {
            const value = record[fieldName];
            let id, name;
            if (["one2many", "many2many"].includes(fieldType)) {
                if (value.length) {
                    for (const r of value) {
                        addToGroup(r.id, r.display_name, record);
                    }
                } else {
                    id = name = unsetName;
                    addToGroup(id, name, record);
                }
            } else {
                if (["date", "datetime"].includes(fieldType) && value) {
                    const date =
                        fieldType === "date" ? parseDate(value) : parseDateTime(value);
                    const format = DATE_GROUP_FORMATS[subGroup || "month"];
                    id = name = format ? formatValue(date, format) : value;
                } else if (fieldType === "boolean") {
                    id = name = value ? _t("Yes") : _t("No");
                } else if (fieldType === "integer") {
                    id = name = value || "0";
                } else if (fieldType === "selection") {
                    const selected = metaData.fields[fieldName].selection.find(
                        (o) => o[0] === value,
                    );
                    id = name = selected ? selected[1] : value;
                } else if (fieldType === "many2one" && value) {
                    id = value.id;
                    name = value.display_name;
                } else {
                    id = value;
                    name = value;
                }
                if (!id && !name) {
                    id = name = unsetName;
                }
                addToGroup(id, name, record);
            }
        }
        return groups;
    }

    /**
     * @protected
     * @returns {Object[]}
     */
    _getPartnersToGeocode(data) {
        const toGeocode = [];
        for (const partner of Object.values(data.partners)) {
            if (hasCoordinates(partner)) {
                continue;
            }
            partner.partner_latitude = undefined;
            partner.partner_longitude = undefined;
            if (partner.contact_address_complete) {
                toGeocode.push(partner);
            }
        }
        return toGeocode;
    }

    /** @protected */
    _setPartnerPosition(data, partner, latitude, longitude) {
        partner.partner_latitude = parseFloat(latitude);
        partner.partner_longitude = parseFloat(longitude);
        data.partnersToSave.push(partner);
    }

    /**
     * @protected
     * @return {Promise}
     */
    async _geocodeWithMapBox(metaData, data) {
        await Promise.all(
            this._getPartnersToGeocode(data).map(async (partner) => {
                const coordinates = await this._fetchCoordinatesFromAddressMB(
                    metaData,
                    data,
                    partner,
                );
                if (coordinates.features.length) {
                    const [longitude, latitude] =
                        coordinates.features[0].geometry.coordinates;
                    this._setPartnerPosition(data, partner, latitude, longitude);
                }
            }),
        );
        await this._loadRoute(metaData, data);
    }

    /**
     * @protected
     * @returns {Promise}
     */
    async _loadRoute(metaData, data) {
        data.routes = [];
        if (!data.useMapBoxAPI || !metaData.routing || data.groupByKey) {
            return;
        }
        const points = this._getRouteCoordinates(data);
        if (points.length < 2) {
            return;
        }
        if (points.length > MAP_BOX_MAX_ROUTE_POINTS) {
            data.routingError = _t("Too many routing points (maximum 25)");
            return;
        }
        const routeResult = await this._fetchRoute(metaData, data);
        if (routeResult.routes) {
            data.routes = routeResult.routes;
        } else {
            data.routingError = this._getErrorMessage(routeResult.message);
        }
    }

    /** @protected */
    _getLocatedRecordCount(data) {
        return data.records.filter((record) => hasCoordinates(record.partner)).length;
    }

    /**
     * @protected
     * @param {Object} err
     * @param {number} err.status
     */
    _mapBoxErrorHandling(metaData, data, err) {
        switch (err.status) {
            case 401:
                this._notifyMapBoxFallback(_t("Token invalid"));
                break;
            case 403:
                this._notifyMapBoxFallback(_t("Unauthorized connection"));
                break;
            case 422:
            case 429:
                data.routingError = this._getErrorMessage(err.message);
                break;
            default:
                this._notifyMapBoxFallback(_t("MapBox servers unreachable"));
        }
    }

    /** @protected */
    _notifyMapBoxFallback(title) {
        this.notification.add(
            _t(
                "The view has switched to another provider but functionalities will be limited",
            ),
            { title, type: "danger" },
        );
    }

    /** @protected */
    _notifyFetchedCoordinate(metaData, data) {
        this._savePartnerCoordinates(metaData, data);
        data.shouldUpdatePosition = false;
        this.notify();
    }

    /**
     * @protected
     * @return {Promise}
     */
    _startGeocodingWithOpenStreetMap(metaData, data) {
        this._geocodeWithOpenStreetMap(metaData, data);
        return Promise.resolve();
    }
    /**
     * @protected
     * @returns {Promise}
     */
    async _geocodeWithOpenStreetMap(metaData, data) {
        const partnersByAddress = new Map();
        for (const partner of this._getPartnersToGeocode(data)) {
            const address = partner.contact_address_complete;
            if (!partnersByAddress.has(address)) {
                partnersByAddress.set(address, []);
            }
            partnersByAddress.get(address).push(partner);
        }

        data.fetchingCoordinates = partnersByAddress.size > 0;
        this.shouldFetchCoordinates = true;
        const partnersList = [...partnersByAddress.values()];
        for (let i = 0; i < partnersList.length; i++) {
            if (i > 0) {
                await new Promise((resolve) => {
                    this.coordinateFetchingTimeoutHandle = browser.setTimeout(
                        resolve,
                        this.constructor.COORDINATE_FETCH_DELAY,
                    );
                });
            }
            if (!this.shouldFetchCoordinates) {
                return;
            }
            const partners = partnersList[i];
            try {
                const coordinates = await this._fetchCoordinatesFromAddressOSM(
                    metaData,
                    data,
                    partners[0],
                );
                if (!this.shouldFetchCoordinates) {
                    return;
                }
                if (coordinates.length) {
                    for (const partner of partners) {
                        this._setPartnerPosition(
                            data,
                            partner,
                            coordinates[0].lat,
                            coordinates[0].lon,
                        );
                    }
                }
                data.fetchingCoordinates = i < partnersList.length - 1;
                this._notifyFetchedCoordinate(metaData, data);
            } catch (error) {
                data.fetchingCoordinates = false;
                this.shouldFetchCoordinates = false;
                this.notification.add(this._getOpenStreetMapErrorMessage(error), {
                    type: "danger",
                });
                this.notify();
                return;
            }
        }
    }

    /**
     * @protected
     * @param {Object} error
     * @returns {string}
     */
    _getOpenStreetMapErrorMessage(error) {
        if (error.status === 429) {
            return _t("OpenStreetMap's request limit exceeded, try again later.");
        }
        return _t("OpenStreetMap could not locate the remaining addresses.");
    }

    /**
     * @protected
     * @returns {Promise}
     */
    async _updatePartnerCoordinate(metaData, data) {
        if (data.useMapBoxAPI) {
            try {
                await this.keepLastGeocoding.add(
                    this._geocodeWithMapBox(metaData, data),
                );
            } catch (error) {
                this._mapBoxErrorHandling(metaData, data, error);
                data.useMapBoxAPI = false;
                return this._startGeocodingWithOpenStreetMap(metaData, data);
            }
            return this._savePartnerCoordinates(metaData, data);
        }
        await this._startGeocodingWithOpenStreetMap(metaData, data);
        return this._savePartnerCoordinates(metaData, data);
    }
    /**
     * @protected
     * @return {Promise}
     */
    async _savePartnerCoordinates(metaData, data) {
        const partners = data.partnersToSave;
        data.partnersToSave = [];
        if (!partners.length) {
            return;
        }
        try {
            await this._writePartnerCoordinates(metaData, partners);
        } catch {
            this.notification.add(
                _t("The geocoded addresses could not be saved for next time."),
                { type: "warning" },
            );
        }
    }
    /**
     * @protected
     * @return {Promise}
     */
    async _writePartnerCoordinates(metaData, partners) {
        await this.orm.call(
            "res.partner",
            "update_latitude_longitude",
            [
                partners.map(({ id, partner_latitude, partner_longitude }) => ({
                    id,
                    partner_latitude,
                    partner_longitude,
                })),
            ],
            { context: metaData.context },
        );
    }
}

MapModel.services = ["notification"];
MapModel.COORDINATE_FETCH_DELAY = 1000;
