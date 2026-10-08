/** @odoo-module native */
import { effect, markRaw, proxy, toRaw, untrack } from "@odoo/owl";
import { createRelatedModels } from "@point_of_sale/app/models/related_models";
import { getOnNotified, uuidv4 } from "@point_of_sale/utils";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import {
    compareDates,
    isDateTimeValue,
    now,
    parseSQL,
    toISO,
} from "@web/core/l10n/dates";
import { ConnectionLostError, rpc, RPCError } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Mutex } from "@web/core/utils/concurrency";
import { SignalStore } from "@web/core/utils/reactive";
import { debounce } from "@web/core/utils/timing";

import { DataServiceOptions } from "../models/data_service_options.js";
import IndexedDB from "../models/utils/indexed_db.js";
import DeviceIdentifierSequence from "../utils/devices_identifier_sequence.js";
import { compareQueueEntries, UNSYNC_QUEUE_STORE } from "../utils/offline_queue.js";
import { OptimisticUpdates } from "../utils/optimistic_updates.js";
import { logPosMessage } from "../utils/pretty_console_log.js";
const CONSOLE_COLOR = "#28ffeb";
const MAX_SYNC_ATTEMPTS = 5;
const log = makeLogger("pos.data");
const UNQUEUEABLE_TYPES = new Set(["read", "search_read"]);

function readPlainState(value, seen = new Set()) {
    if (!value || typeof value !== "object" || seen.has(toRaw(value))) {
        return;
    }
    seen.add(toRaw(value));
    if (value instanceof Set || value instanceof Map) {
        for (const item of value.values()) {
            readPlainState(item, seen);
        }
        return;
    }
    const prototype = Object.getPrototypeOf(toRaw(value));
    if (prototype !== Object.prototype && prototype !== null && !Array.isArray(value)) {
        return;
    }
    for (const item of Object.values(value)) {
        readPlainState(item, seen);
    }
}

export class QueuedOperation {
    constructor(uuid) {
        this.uuid = uuid;
    }
}

export const isQueued = (result) => result instanceof QueuedOperation;

export class PosData extends SignalStore {
    static modelToLoad = [];
    static serviceDependencies = ["orm", "bus_service", "dialog"];

    constructor() {
        super();
        this.ready = this.setup(...arguments).then(() => this);
    }

    async setup(env, { orm, bus_service, dialog }) {
        this.dialog = dialog;
        this.orm = orm;
        this.bus = bus_service;
        this.relations = [];
        this.custom = {};
        this.mutex = markRaw(new Mutex());
        this.indexedDBMutex = markRaw(new Mutex());
        this.optimisticUpdates = markRaw(new Map());
        this.records = {};
        this.opts = new DataServiceOptions();
        this.channels = [];
        this.dirtyLocalRecords = new Map();
        this.localStateWatchers = markRaw(new Map());
        this.referenceFieldsByModel = markRaw(new Map());
        this.debouncedSynchronizeLocalDataInIndexedDB = debounce(
            () => this.syncLocalDataInIndexedDB({ onlyDirty: true }),
            300,
        );

        this.network = {
            warningTriggered: false,
            offline: false,
            loading: true,
            unsyncData: [],
            deadSyncData: [],
        };

        this.localUnsyncedPaidOrderUuids = new Set();

        const endSetup = log.perf("setup");
        log.lifecycle("setup", () => ({
            config: odoo.pos_config_id,
            db: this.databaseName,
        }));
        await this.checkConnectivity();

        this.initializeWebsocket();
        await this.initializeDeviceIdentifier();
        await this.intializeDataRelation();

        browser.addEventListener("online", () => this.checkConnectivity());
        browser.addEventListener("offline", () => this.checkConnectivity());
        this.bus.addEventListener("BUS:CONNECT", this.reconnectWebSocket.bind(this));
        endSetup({
            offline: this.network.offline,
            device: this.device?.identifier,
            models: Object.keys(this.models || {}).length,
        });
    }

    async initializeDeviceIdentifier() {
        const endInit = log.perf("initializeDeviceIdentifier");
        this.device = new DeviceIdentifierSequence({ orm: this.orm });
        await this.device.initialize();
        endInit({ identifier: this.device.identifier });
    }

    async checkConnectivity() {
        try {
            clearTimeout(this.checkConnectivityTimeout);
            this.checkConnectivityTimeout = null;
            this.network.offline = false;
            this.network.warningTriggered = false;

            await rpc("/pos/ping");
            log.lifecycle("checkConnectivity: online", () => ({
                unsynced: this.network.unsyncData.length,
            }));
            await this.syncData();
            window.dispatchEvent(new CustomEvent("pos-network-online"));
        } catch (error) {
            log.logic("checkConnectivity: failed", () => ({
                connectionLost: error instanceof ConnectionLostError,
                navigatorOnLine: navigator.onLine,
                error: error?.message,
            }));
            if (error instanceof ConnectionLostError) {
                this.network.offline = true;
                if (navigator.onLine) {
                    this.checkConnectivityTimeout = setTimeout(
                        () => this.checkConnectivity(),
                        2000,
                    );
                }
            }
        }
    }

    initializeWebsocket() {
        this.onNotified = getOnNotified(this.bus, odoo.access_token);
    }

    reconnectWebSocket() {
        log.lifecycle("[bus] reconnectWebSocket", () => ({
            channels: this.channels.map((c) => c.channel),
        }));
        this.initializeWebsocket();
        const channels = [...this.channels];
        this.channels = [];
        while (channels.length) {
            const channel = channels.pop();
            this.connectWebSocket(channel.channel, channel.method);

            logPosMessage(
                "DataService",
                "reconnectWebSocket",
                `Reconnecting to channe ${channel.channel}`,
                CONSOLE_COLOR,
            );
        }
    }

    connectWebSocket(channel, method) {
        log.lifecycle("[bus] connectWebSocket", () => ({ channel }));
        this.channels.push({
            channel,
            method,
        });

        this.onNotified(channel, method);
    }

    get databaseName() {
        return `point-of-sale-${odoo.pos_config_id}-${odoo.info?.db}`;
    }

    async resetIndexedDB() {
        log.lifecycle("[idb] reset", () => ({ db: this.databaseName }));
        await this.indexedDB.reset();
    }

    get serverCacheStores() {
        // orders, their children and the offline queue are local work, not cache
        const local = new Set([
            ...Object.keys(this.opts.databaseTable),
            UNSYNC_QUEUE_STORE,
        ]);
        return this.indexedDB.dbStores
            .map(([, storeName]) => storeName)
            .filter((storeName) => !local.has(storeName));
    }

    async clearServerCacheInIndexedDB() {
        const stores = this.serverCacheStores;
        log.lifecycle("[idb] clear server cache", () => ({
            db: this.databaseName,
            stores: stores.length,
        }));
        return await this.indexedDB.clear(stores);
    }

    async deleteRecordsInIndexedDB(model, ids) {
        log.lifecycle("[idb] delete", () => ({ model, ids: ids.length }));
        // after any write in flight, which would otherwise put the row back
        return await this.indexedDBMutex.exec(() => this.indexedDB.delete(model, ids));
    }

    async initIndexedDB(relations) {
        const allModelNames = Array.from(
            new Set([
                ...Object.keys(relations),
                ...Object.keys(this.opts.databaseTable),
            ]),
        );
        const models = allModelNames.map((model) => {
            const key = this.opts.databaseTable[model]?.key || "id";
            return [key, model];
        });
        models.push(["uuid", UNSYNC_QUEUE_STORE]);
        const endInit = log.perf("[idb] initIndexedDB");
        log.pipeline("[idb] initIndexedDB", () => ({
            db: this.databaseName,
            stores: models.length,
        }));

        const db = await new Promise((resolve) => {
            this.indexedDB = new IndexedDB(
                this.databaseName,
                false,
                models,
                resolve,
                this.dialog,
            );
        });
        endInit();
        return db;
    }

    async syncLocalDataInIndexedDB(opts = {}) {
        return this.indexedDBMutex.exec(() =>
            this._synchronizeLocalDataInIndexedDB(opts),
        );
    }

    markLocalRecordsDirty(model, ids) {
        const tracked = this.opts.databaseTable;
        const visited = new Set();
        const mark = (record) => {
            if (visited.has(record)) {
                return;
            }
            visited.add(record);
            const modelName = record.model.name;
            if (tracked[modelName]) {
                if (!this.dirtyLocalRecords.has(modelName)) {
                    this.dirtyLocalRecords.set(modelName, new Set());
                }
                this.dirtyLocalRecords.get(modelName).add(record);
            }
            // a child marks its parents _dirty, which their rows carry
            for (const field of record.model.getParentFields()) {
                const parent = record[field.name];
                if (parent?.model) {
                    mark(parent);
                }
            }
            // a referenced row is kept or purged by what references it
            for (const fieldName of this.trackedReferenceFields(modelName, tracked)) {
                const referenced = record[fieldName];
                if (referenced?.model) {
                    mark(referenced);
                }
            }
        };
        for (const id of ids) {
            const record = this.models[model].get(id);
            if (record) {
                mark(record);
            }
        }
    }

    trackedReferenceFields(model, tracked) {
        let fieldNames = this.referenceFieldsByModel.get(model);
        if (!fieldNames) {
            const dynamicModels = new Set(this.opts.dynamicModels);
            fieldNames = Object.values(this.relations[model] || {})
                .filter(
                    (field) =>
                        field.type === "many2one" &&
                        tracked[field.relation] &&
                        !dynamicModels.has(field.relation),
                )
                .map((field) => field.name);
            this.referenceFieldsByModel.set(model, fieldNames);
        }
        return fieldNames;
    }

    takeDirtyLocalRecords(model) {
        const dirty = this.dirtyLocalRecords.get(model);
        this.dirtyLocalRecords.delete(model);
        const live = [...(dirty || [])].filter(
            (record) => this.models[model].get(record.id) === record,
        );
        if (model === "pos.order") {
            for (const uuid of this.localUnsyncedPaidOrderUuids) {
                const order = this.models[model].getBy("uuid", uuid);
                if (order && !dirty?.has(order)) {
                    live.push(order);
                }
            }
        }
        return live;
    }

    async _synchronizeLocalDataInIndexedDB({ onlyDirty = false } = {}) {
        const endSync = log.perf("synchronizeLocalDataInIndexedDB");
        const modelsParams = Object.entries(this.opts.databaseTable);
        const data = {};
        let written = 0;
        for (const [model, params] of modelsParams) {
            const put = [];
            const remove = [];
            const dirty = this.takeDirtyLocalRecords(model);
            const modelData = onlyDirty ? dirty : this.models[model].getAll();

            for (const record of modelData) {
                const isToRemove = params.condition(record);

                if (isToRemove === undefined || isToRemove === true) {
                    if (record[params.key]) {
                        remove.push(record[params.key]);
                    }
                } else {
                    put.push(record.serializeForIndexedDB());
                }
            }

            data[model] = put;
            written += put.length;
            log.pipeline("[idb] synchronizeLocalData: model", () => ({
                model,
                onlyDirty,
                put: put.length,
                remove: remove.length,
            }));

            if (remove.length) {
                await this.indexedDB.delete(model, remove);
            }

            let writeResults;
            if (put.length) {
                writeResults = await this.indexedDB.create(model, put);
            }

            if (model === "pos.order") {
                const writeSucceeded =
                    !put.length ||
                    (Array.isArray(writeResults) &&
                        writeResults.every((r) => r?.status === "fulfilled"));
                const writtenByUuid = new Map(put.map((r) => [r.uuid, r]));
                for (const trackedUuid of [...this.localUnsyncedPaidOrderUuids]) {
                    const written = writtenByUuid.get(trackedUuid);
                    const localRecord = this.models[model].getBy("uuid", trackedUuid);
                    log.logic("[idb] unsynced paid guard", () => ({
                        order: trackedUuid,
                        stillUnsyncedPaid: Boolean(localRecord?.isUnsyncedPaid),
                        written: Boolean(written),
                        writeSucceeded,
                    }));
                    if (!localRecord?.isUnsyncedPaid) {
                        this.localUnsyncedPaidOrderUuids.delete(trackedUuid);
                    } else if (written?.state === "paid" && writeSucceeded) {
                        this.localUnsyncedPaidOrderUuids.delete(trackedUuid);
                    } else {
                        logPosMessage(
                            "DataService",
                            "syncLocalDataInIndexedDB",
                            `Paid order ${trackedUuid} is flagged unsynced but not confirmed durable (written=${!!written}, writeOk=${writeSucceeded}) — keeping data-loss guard`,
                            CONSOLE_COLOR,
                        );
                    }
                }
            }
        }
        endSync({ models: Object.keys(data).length, onlyDirty, written });

        return data;
    }

    async syncServerDataInIndexedDB(serverData = {}) {
        const endSync = log.perf("[idb] syncServerDataInIndexedDB");
        try {
            const clone = JSON.parse(JSON.stringify(serverData));
            log.pipeline("[idb] syncServerDataInIndexedDB", () => ({
                models: Object.fromEntries(
                    Object.entries(clone).map(([model, rows]) => [model, rows.length]),
                ),
            }));
            for (const [model, data] of Object.entries(clone)) {
                try {
                    await this.indexedDB.create(model, data);
                } catch {
                    logPosMessage(
                        "DataService",
                        "syncServerDataInIndexedDB",
                        `Error while updating ${model} in indexedDB.`,
                        CONSOLE_COLOR,
                    );
                }
            }
        } catch {
            logPosMessage(
                "DataService",
                "syncServerDataInIndexedDB",
                "Error while synchronizing server data in indexedDB.",
                CONSOLE_COLOR,
            );
        }
        endSync({ models: Object.keys(serverData).length });
    }

    async getLocalDataFromIndexedDB(data = false) {
        const models = Object.keys(this.opts.databaseTable);
        const endLoad = log.perf("[idb] getLocalDataFromIndexedDB");

        if (!data) {
            data = await this.indexedDB.readAll(models);
        }

        log.pipeline("[idb] getLocalDataFromIndexedDB", () => ({
            models: data
                ? Object.fromEntries(
                      Object.entries(data).map(([model, rows]) => [model, rows.length]),
                  )
                : null,
        }));
        if (!data) {
            endLoad({ empty: true });
            return;
        }

        const preLoadData = await this.preLoadData(data);
        const missing = await this.missingRecursive(preLoadData);

        const serverProductIds = this.models["product.product"].map((p) => p.id);
        const databaseProductIds = missing["product.product"]?.map((p) => p.id) ?? [];
        const loadedProductIds = new Set([...databaseProductIds, ...serverProductIds]);
        const restoredLines = missing["pos.order.line"] ?? [];
        missing["pos.order.line"] = restoredLines.filter((line) =>
            loadedProductIds.has(line.product_id),
        );
        const droppedLines = restoredLines.length - missing["pos.order.line"].length;
        log.logic("[idb] getLocalDataFromIndexedDB: restored lines", () => ({
            restored: restoredLines.length,
            dropped: droppedLines,
            loadedProducts: loadedProductIds.size,
        }));
        if (droppedLines) {
            logPosMessage(
                "DataService",
                "getLocalDataFromIndexedDB",
                `Dropped ${droppedLines} restored order line(s) whose product is not loaded; the owning orders will show an incomplete total`,
                CONSOLE_COLOR,
            );
        }

        const results = this.models.loadConnectedData(missing, []);

        this.purgeRestoredOrders(results);
        await this.checkAndDeleteMissingOrders(results);
        endLoad({ orders: results["pos.order"]?.length });

        return results;
    }

    // before checkAndDeleteMissingOrders: loadServerOrders stamps the current
    // session on every order it reads, after which none is ever purgeable
    purgeRestoredOrders(results) {
        const isPurgeable = this.opts.databaseTable["pos.order"]?.condition;
        const restored = results?.["pos.order"];
        if (!isPurgeable || !restored?.length) {
            return;
        }
        const purged = restored.filter((order) => isPurgeable(order) === true);
        log.logic("[idb] purgeRestoredOrders", () => ({
            restored: restored.length,
            purged: purged.map((order) => order.uuid),
        }));
        for (const order of purged) {
            this.localDeleteCascade(order);
        }
        if (purged.length) {
            const gone = new Set(purged);
            results["pos.order"] = restored.filter((order) => !gone.has(order));
        }
    }

    async getCachedServerDataFromIndexedDB() {
        const endRead = log.perf("[idb] getCachedServerDataFromIndexedDB");
        const stores = this.serverCacheStores;
        // readAll([]) would read every store, orders included
        const results = stores.length
            ? (await this.indexedDB.readAll(stores)) || {}
            : {};
        endRead({ models: Object.keys(results).length });

        return results;
    }

    async loadInitialData() {
        const endLoad = log.perf("loadInitialData");
        let localData = await this.getCachedServerDataFromIndexedDB();
        const session = localData?.["pos.session"]?.[0];
        log.pipeline("loadInitialData", () => ({
            cachedModels: Object.keys(localData || {}).length,
            session: session?.id,
            state: session?.state,
            offline: this.network.offline,
            fromBackend: Boolean(odoo.from_backend),
        }));

        const loadFromServer =
            (!this.network.offline && session?.state !== "opened") ||
            session?.id !== odoo.pos_session_id ||
            odoo.from_backend;
        log.logic("loadInitialData: source", () => ({
            loadFromServer,
            cachedSession: session?.id,
            currentSession: odoo.pos_session_id,
        }));
        if (loadFromServer) {
            try {
                const limitedLoading = this.isLimitedLoading();
                const serverDate = localData["pos.config"]?.[0]?._data_server_date;
                const lastConfigChange = parseSQL(odoo.last_data_change);
                const serverDateTime = parseSQL(serverDate);
                const cacheOrder =
                    serverDateTime && lastConfigChange
                        ? compareDates(serverDateTime, lastConfigChange)
                        : NaN;

                log.logic("loadInitialData: cache validity", () => ({
                    limitedLoading,
                    serverDate,
                    lastConfigChange: odoo.last_data_change,
                    resetCache: cacheOrder < 0,
                }));
                if (cacheOrder < 0) {
                    await this.clearServerCacheInIndexedDB();
                    localData = {};
                }

                const endServerLoad = log.perf("loadInitialData: load_data");
                const data = await this.orm.call(
                    "pos.session",
                    "load_data",
                    [odoo.pos_session_id, PosData.modelToLoad],
                    {
                        context: {
                            pos_last_server_date: cacheOrder > 0 && serverDate,
                            pos_limited_loading: limitedLoading,
                        },
                    },
                );
                endServerLoad({
                    models: Object.fromEntries(
                        Object.entries(data).map(([model, rows]) => [
                            model,
                            rows.length,
                        ]),
                    ),
                });

                const local_records_to_filter = {};
                for (const model of this.opts.cleanupModels) {
                    const local = localData[model] || [];
                    if (local.length > 0) {
                        local_records_to_filter[model] = local.map((r) => r.id);
                    }
                }

                const endFilter = log.perf("loadInitialData: filter_local_data");
                const data_to_remove = await this.orm.call(
                    "pos.session",
                    "filter_local_data",
                    [odoo.pos_session_id, local_records_to_filter],
                );
                endFilter({
                    sent: Object.fromEntries(
                        Object.entries(local_records_to_filter).map(([model, ids]) => [
                            model,
                            ids.length,
                        ]),
                    ),
                    toRemove: Object.fromEntries(
                        Object.entries(data_to_remove).map(([model, ids]) => [
                            model,
                            ids.length,
                        ]),
                    ),
                });

                for (const [model, values] of Object.entries(data)) {
                    let local = localData[model] || [];

                    log.logic("loadInitialData: merge", () => ({
                        model,
                        local: local.length,
                        server: values.length,
                        unique: this.opts.uniqueModels.includes(model),
                        removed: data_to_remove[model]?.length ?? 0,
                    }));
                    if (this.opts.uniqueModels.includes(model) && values.length > 0) {
                        this.indexedDB.delete(
                            model,
                            local.map((r) => r.id),
                        );
                        localData[model] = values;
                    } else {
                        if (data_to_remove[model] && data_to_remove[model].length > 0) {
                            const remove_ids = data_to_remove[model];
                            local = local.filter((r) => !remove_ids.includes(r.id));
                            this.indexedDB.delete(model, remove_ids);
                        }
                        localData[model] = local.concat(values);
                    }
                }

                this.syncServerDataInIndexedDB(localData);
            } catch (error) {
                let message = _t(
                    "An error occurred while loading the Point of Sale: \n",
                );
                if (error instanceof RPCError) {
                    message += error.data.message;
                } else {
                    message += error.message;
                }
                window.alert(message);
                endLoad({ alerted: true });
                return localData;
            }
        }
        endLoad({ models: Object.keys(localData || {}).length });

        return localData;
    }

    async initData() {
        const data = await this.loadInitialData();
        const order = data["pos.order"] || [];
        const orderlines = data["pos.order.line"] || [];
        const endInit = log.perf("initData");

        delete data["pos.order"];
        delete data["pos.order.line"];

        this.models.loadConnectedData(data, this.modelToLoad);
        this.models.loadConnectedData(
            { "pos.order": order, "pos.order.line": orderlines },
            [],
        );
        endInit({ orders: order.length, orderlines: orderlines.length });
        this.sanitizeData();
    }

    async sanitizeData() {
        const order_to_delete = this.models["pos.order"].filter((order) =>
            order.lines.some(
                (line) => line.is_reward_line && !line.coupon_id && !line.reward_id,
            ),
        );
        log.logic("sanitizeData", () => ({
            ordersWithOrphanRewards: order_to_delete.map((o) => o.uuid),
        }));
        for (const order of order_to_delete) {
            for (let i = order.lines.length - 1; i >= 0; i--) {
                order.lines[i].delete();
            }
        }
    }

    async loadFieldsAndRelations() {
        const key = `pos_data_params_${odoo.pos_config_id}`;
        if (this.network.offline) {
            log.logic("loadFieldsAndRelations: offline, localStorage", () => ({ key }));
            return JSON.parse(localStorage.getItem(key));
        }

        const endLoad = log.perf("loadFieldsAndRelations");
        try {
            const params = await this.orm.call("pos.session", "load_data_params", [
                odoo.pos_session_id,
            ]);
            localStorage.setItem(key, JSON.stringify(params));
            endLoad({ models: Object.keys(params).length });
            return params;
        } catch {
            endLoad({ fallback: "localStorage" });
            return JSON.parse(localStorage.getItem(key));
        }
    }

    async intializeDataRelation() {
        const modelClasses = {};
        const fields = {};
        const relations = {};
        const endInit = log.perf("intializeDataRelation");
        const dataParams = await this.loadFieldsAndRelations();
        await this.initIndexedDB(dataParams);
        await this.restoreUnsyncQueue();

        for (const [model, values] of Object.entries(dataParams)) {
            relations[model] = values.relations;
            fields[model] = values.fields;
        }

        for (const posModel of registry.category("pos_available_models").getAll()) {
            const pythonModel = posModel.pythonModel;
            const extraFields = posModel.extraFields || {};

            modelClasses[pythonModel] = posModel;
            relations[pythonModel] = {
                ...relations[pythonModel],
                ...extraFields,
            };
        }

        const endModels = log.perf("createRelatedModels");
        const { models } = createRelatedModels(relations, modelClasses, this.opts);
        endModels({
            models: Object.keys(relations).length,
            classes: Object.keys(modelClasses).length,
        });

        this.fields = fields;
        this.relations = relations;
        this.models = models;

        if (odoo.debug === "assets") {
            window.performance.mark("pos_data_service_init");
        }

        await this.initData();
        await this.getLocalDataFromIndexedDB();
        this.initListeners();
        // the incremental flush only re-checks what changes: one full pass
        // drops the rows whose purge condition turned true before this boot
        Promise.resolve(this.syncLocalDataInIndexedDB()).catch((error) =>
            logPosMessage(
                "DataService",
                "intializeDataRelation",
                "The boot pass over the local rows failed; they are re-checked when they change",
                CONSOLE_COLOR,
                [error],
            ),
        );
        this.drainRestoredQueue();

        if (odoo.debug === "assets") {
            window.performance.mark("pos_data_service_init_end");
            this.debugInfos();
        }

        this.network.loading = false;
        endInit({
            models: Object.keys(models).length,
            unsynced: this.network.unsyncData.length,
        });
    }

    debugInfos() {
        const measure = window.performance.measure(
            "pos_loading",
            "pos_data_service_init",
            "pos_data_service_init_end",
        );

        logPosMessage(
            "DataService",
            "debugInfos",
            `PosDataService initialized in ${measure.duration.toFixed(2)}ms`,
            CONSOLE_COLOR,
        );
    }

    initListeners() {
        this.listenToLocalChanges();

        const ignore = new Set(Object.keys(this.opts.databaseTable));
        for (const model of Object.keys(this.relations)) {
            if (ignore.has(model)) {
                continue;
            }

            this.models[model].addEventListener("delete", (params) => {
                this.indexedDB.delete(model, [params.key]);
            });

            this.models[model].addEventListener("update", (params) => {
                const record = this.models[model].get(params.id)?.raw;
                log.lifecycle("[event] static model update", () => ({
                    model,
                    id: params.id,
                    found: Boolean(record),
                }));
                if (!record) {
                    return;
                }
                this.syncServerDataInIndexedDB({ [model]: [record] });
            });
        }
    }

    listenToLocalChanges() {
        const databaseTable = this.opts.databaseTable;
        const localModels = new Set([
            ...this.opts.dynamicModels,
            ...Object.keys(databaseTable),
        ]);
        for (const localModel of localModels) {
            if (!this.models[localModel]) {
                continue;
            }

            const persist = (ids) => {
                this.markLocalRecordsDirty(localModel, ids);
                this.debouncedSynchronizeLocalDataInIndexedDB();
            };
            this.models[localModel].addEventListener("update", (params) =>
                persist([params.id]),
            );
            this.models[localModel].addEventListener("create", (params) => {
                persist(params.ids);
                for (const id of params.ids) {
                    this.watchLocalState(localModel, this.models[localModel].get(id));
                }
            });

            if (databaseTable[localModel]) {
                for (const record of this.models[localModel].getAll()) {
                    this.watchLocalState(localModel, record);
                }
                this.models[localModel].addEventListener("delete", (params) => {
                    this.unwatchLocalState(localModel, params.key);
                    if (params.key !== undefined) {
                        this.deleteRecordsInIndexedDB(localModel, [params.key]);
                    }
                });
            }
        }
    }

    // uiState is persisted with its row but fires no update event
    watchLocalState(model, record) {
        const key = this.opts.databaseTable[model]?.key;
        if (!key || !record || typeof record.uiState !== "object") {
            return;
        }
        const watchKey = `${model}:${record[key]}`;
        if (this.localStateWatchers.has(watchKey)) {
            return;
        }
        const observed = proxy(record);
        let initialRun = true;
        const stop = effect(
            () => {
                readPlainState(observed.uiState);
                if (initialRun) {
                    initialRun = false;
                    return;
                }
                untrack(() => {
                    if (this.models[model].get(record.id) !== record) {
                        return;
                    }
                    this.markLocalRecordsDirty(model, [record.id]);
                    this.debouncedSynchronizeLocalDataInIndexedDB();
                });
            },
            { detached: true, name: "pos.data local state" },
        );
        this.localStateWatchers.set(watchKey, stop);
    }

    unwatchLocalState(model, key) {
        const watchKey = `${model}:${key}`;
        this.localStateWatchers.get(watchKey)?.();
        this.localStateWatchers.delete(watchKey);
    }

    async execute({
        type,
        model,
        ids,
        values,
        method,
        queue,
        args = [],
        kwargs = {},
        fields = [],
        options = [],
        uuid = "",
        optimistic = false,
    }) {
        const queueable =
            queue && method !== "sync_from_ui" && !UNQUEUEABLE_TYPES.has(type);
        const queuedArgs = queueable
            ? JSON.parse(JSON.stringify(arguments[0]))
            : undefined;
        // sent on the first attempt too: it may commit before the connection drops
        const operationUuid = uuid || (queueable ? uuidv4() : "");
        const withOperation = (kw = {}) =>
            operationUuid
                ? {
                      ...kw,
                      context: { ...kw.context, pos_operation_uuid: operationUuid },
                  }
                : kw;
        this._inFlight = (this._inFlight ?? 0) + 1;
        this.network.loading = true;
        const endExecute = log.perf(
            `execute ${type} ${model}${method ? "." + method : ""}`,
        );
        log.pipeline("execute", () => ({
            type,
            model,
            method,
            ids,
            queue,
            uuid,
            optimistic,
            offline: this.network.offline,
        }));

        try {
            if (this.network.offline) {
                throw new ConnectionLostError();
            }

            let result = true;
            if (fields.length === 0) {
                fields = this.fields[model] || [];
            }

            switch (type) {
                case "write":
                    result = await this.orm.write(model, ids, values, withOperation());
                    break;
                case "delete":
                    result = await this.orm.unlink(model, ids, withOperation());
                    break;
                case "call":
                    result = await this.orm.call(
                        model,
                        method,
                        args,
                        withOperation(kwargs),
                    );
                    break;
                case "read":
                    result = await this.orm.read(model, ids, fields, {
                        ...options,
                        load: false,
                    });
                    break;
                case "search_read":
                    result = await this.orm.searchRead(model, args, fields, {
                        ...options,
                        load: false,
                    });
            }

            if (type === "create") {
                const response = await this.orm.create(model, values, withOperation());
                result = values.map((value, index) => ({
                    ...value,
                    id: response[index],
                }));
            }

            if (this.models[model] && this.opts.autoLoadedOrmMethods.includes(type)) {
                const modelFields = this.fields[model] || [];
                const limitedFields = modelFields.some(
                    (field) => !fields.includes(field),
                );
                log.logic("execute: auto-load", () => ({
                    type,
                    model,
                    rows: Array.isArray(result) ? result.length : null,
                    limitedFields,
                }));
                if (limitedFields && type !== "create") {
                    const missingIds = result
                        .filter((row) => !this.models[model].get(row.id))
                        .map((row) => row.id);
                    log.logic("execute: complete limited rows", () => ({
                        model,
                        missing: missingIds.length,
                    }));
                    if (missingIds.length) {
                        const complete = await this.orm.read(
                            model,
                            missingIds,
                            modelFields,
                            { load: false },
                        );
                        const byId = new Map(complete.map((row) => [row.id, row]));
                        result = result.map((row) => byId.get(row.id) || row);
                    }
                }
                result = await this.loadServerRecords(model, result);
            } else if (type === "write" && this.models[model]) {
                const records = ids
                    .map((id) => this.models[model].get(id))
                    .filter(Boolean);
                log.logic("execute: local write apply", () => ({
                    model,
                    ids,
                    local: records.length,
                    optimistic,
                    keys: Object.keys(values || {}),
                }));
                if (!optimistic) {
                    for (const record of records) {
                        record.update(values, { omitUnknownField: true });
                    }
                }
                this.syncServerDataInIndexedDB({
                    [model]: records.map((record) => record.raw),
                });
            }

            endExecute({ inFlight: this._inFlight });
            if (result === null || result === undefined) {
                return true;
            }
            return result;
        } catch (error) {
            endExecute({ inFlight: this._inFlight, error: error?.constructor?.name });
            const alreadyQueued = this.network.unsyncData.some(
                (d) => d.uuid === operationUuid,
            );
            log.logic("execute: error", () => ({
                type,
                model,
                method,
                queueable,
                alreadyQueued,
                connectionLost: error instanceof ConnectionLostError,
                error: error?.constructor?.name,
            }));
            if (
                !queueable ||
                alreadyQueued ||
                !(error instanceof ConnectionLostError)
            ) {
                throw error;
            }
            const entry = {
                args: [queuedArgs],
                appliedLocally: optimistic,
                date: toISO(now()),
                try: 1,
                uuid: operationUuid,
            };
            await this.mutex.exec(async () => {
                await this._persistQueueEntry(entry);
                this.network.unsyncData.push(entry);
            });
            log.logic("queued offline", () => ({
                type,
                model,
                method,
                uuid: entry.uuid,
                queue: this.network.unsyncData.length,
            }));
            return new QueuedOperation(entry.uuid);
        } finally {
            this._inFlight -= 1;
            this.network.loading = this._inFlight > 0;
        }
    }

    async loadServerRecords(model, rows) {
        log.pipeline("loadServerRecords", () => ({ model, rows: rows.length }));
        const endLoad = log.perf(`loadServerRecords ${model}`);
        const key = this.opts.databaseTable[model]?.key || "id";
        const identified = rows.map((row) => {
            const local = this.models[model].get(row.id);
            return local && !row[key] ? { ...row, [key]: local[key] } : row;
        });
        const data = await this.missingRecursive({ [model]: identified });
        const results = this.models.connectNewData(data);
        endLoad({
            models: Object.fromEntries(
                Object.entries(results).map(([name, records]) => [
                    name,
                    records.length,
                ]),
            ),
        });
        this.syncServerDataInIndexedDB(
            Object.fromEntries(
                Object.entries(results).map(([name, records]) => [
                    name,
                    records.map((record) => record.raw),
                ]),
            ),
        );
        return results[model];
    }

    async missingRecursive(recordMap, idsMap = {}, acc = {}) {
        for (const [model, records] of Object.entries(recordMap)) {
            if (!acc[model]) {
                acc[model] = records;
            } else {
                acc[model] = acc[model].concat(records);
            }
        }

        if (this.network.offline) {
            log.logic("missingRecursive: offline, skip", () => ({
                models: Object.keys(recordMap),
            }));
            return acc;
        }

        const missingRecords = {};
        const recordInMapByModelIds = Object.entries(recordMap).reduce(
            (acc, [model, records]) => {
                acc[model] = new Set(records.map((r) => r.id));
                return acc;
            },
            {},
        );

        for (const [model, records] of Object.entries(recordMap)) {
            if (!this.relations[model]) {
                continue;
            }

            const relations = Object.entries(this.relations[model]).filter(
                ([, rel]) => rel.relation && rel.type && this.models[rel.relation],
            );

            for (const [, rel] of relations) {
                if (this.opts.prohibitedAutoLoadedModels.includes(rel.relation)) {
                    continue;
                }

                if (
                    this.opts.prohibitedAutoLoadedFields[rel.model]?.includes(rel.name)
                ) {
                    continue;
                }

                const values = records.map((record) => record[rel.name]).flat();
                const missing = values.filter((value) => {
                    if (
                        !value ||
                        typeof value !== "number" ||
                        idsMap[rel.relation]?.has(value)
                    ) {
                        return false;
                    }

                    const record = this.models[rel.relation].get(value);
                    return (
                        (!record || !record.id) &&
                        !recordInMapByModelIds[rel.relation]?.has(value)
                    );
                });

                if (missing.length > 0) {
                    if (!missingRecords[rel.relation]) {
                        missingRecords[rel.relation] = new Set(missing);
                    } else {
                        missingRecords[rel.relation] = new Set([
                            ...missingRecords[rel.relation],
                            ...missing,
                        ]);
                    }
                }
            }
        }

        const newRecordMap = {};
        log.pipeline("missingRecursive", () => ({
            from: Object.fromEntries(
                Object.entries(recordMap).map(([model, rows]) => [model, rows.length]),
            ),
            missing: Object.fromEntries(
                Object.entries(missingRecords).map(([model, ids]) => [model, ids.size]),
            ),
        }));
        for (const [model, ids] of Object.entries(missingRecords)) {
            if (!idsMap[model]) {
                idsMap[model] = new Set(ids);
            } else {
                idsMap[model] = idsMap[model] = new Set([...idsMap[model], ...ids]);
            }

            const endFetch = log.perf(`missingRecursive: fetch ${model}`);
            try {
                if (["product.product", "product.template"].includes(model)) {
                    const domain =
                        model === "product.product" ? "product_variant_ids.id" : "id";
                    // never queued: a replay holds this.mutex, which queueing takes
                    await this.callRelated(
                        "product.template",
                        "load_product_from_pos",
                        [odoo.pos_config_id, [[domain, "in", Array.from(ids)]], 0, 0],
                        {
                            context: {
                                load_archived: true,
                            },
                        },
                        false,
                    );
                    endFetch({ ids: ids.size, via: "load_product_from_pos" });
                    continue;
                }

                const data = await this.orm.read(
                    model,
                    Array.from(ids),
                    this.fields[model],
                    {
                        load: false,
                    },
                );
                newRecordMap[model] = data;
                endFetch({ ids: ids.size, rows: data.length });
            } catch {
                newRecordMap[model] = [];
                endFetch({ ids: ids.size, failed: true });
            }
        }

        if (Object.keys(newRecordMap).length > 0) {
            return await this.missingRecursive(newRecordMap, idsMap, acc);
        } else {
            return acc;
        }
    }

    async _persistQueueEntry(entry) {
        log.lifecycle("[queue] persist", () => ({ uuid: entry.uuid, try: entry.try }));
        const saved = await this.indexedDB.createOrdered(UNSYNC_QUEUE_STORE, {
            uuid: entry.uuid,
            sequence: entry.sequence,
            date: isDateTimeValue(entry.date)
                ? toISO(entry.date)
                : String(entry.date ?? ""),
            try: entry.try ?? 1,
            args: entry.args,
            appliedLocally: entry.appliedLocally === true,
        });
        entry.sequence = saved.sequence;
    }

    _unpersistQueueEntry(uuid) {
        log.lifecycle("[queue] unpersist", () => ({ uuid }));
        this.indexedDB?.delete(UNSYNC_QUEUE_STORE, [uuid])?.catch?.(() => {});
    }

    async restoreUnsyncQueue() {
        try {
            const data = await this.indexedDB.readAll([UNSYNC_QUEUE_STORE]);
            const rows = data?.[UNSYNC_QUEUE_STORE] || [];
            for (const row of rows) {
                if (!this.network.unsyncData.some((d) => d.uuid === row.uuid)) {
                    this.network.unsyncData.push({
                        args: row.args,
                        appliedLocally: row.appliedLocally,
                        date: row.date,
                        restored: true,
                        try: row.try ?? 1,
                        uuid: row.uuid,
                        sequence: row.sequence,
                    });
                }
            }
            this.network.unsyncData.sort(compareQueueEntries);
            log.lifecycle("[queue] restored", () => ({
                rows: rows.length,
                pending: this.network.unsyncData.length,
            }));
        } catch {
            logPosMessage(
                "DataService",
                "restoreUnsyncQueue",
                "Could not restore the offline retry queue from IndexedDB",
                CONSOLE_COLOR,
            );
        }
    }

    drainRestoredQueue() {
        log.logic("[queue] drainRestoredQueue", () => ({
            pending: this.network.unsyncData.length,
            offline: this.network.offline,
        }));
        if (!this.network.unsyncData.length || this.network.offline) {
            return;
        }
        this.syncData().catch((error) => {
            logPosMessage(
                "DataService",
                "drainRestoredQueue",
                "Could not replay the restored offline queue; entries stay queued",
                CONSOLE_COLOR,
                [error],
            );
        });
    }

    async syncData() {
        log.pipeline("syncData", () => ({ pending: this.network.unsyncData.length }));
        const endSync = log.perf("[queue] syncData");
        let replayed = 0;
        await this.mutex.exec(async () => {
            while (this.network.unsyncData.length > 0) {
                const data = this.network.unsyncData[0];
                try {
                    log.pipeline("[queue] replay", () => ({
                        uuid: data.uuid,
                        try: data.try,
                        type: data.args[0]?.type,
                        model: data.args[0]?.model,
                        method: data.args[0]?.method,
                    }));
                    await this.execute({
                        ...data.args[0],
                        uuid: data.uuid,
                        optimistic: data.appliedLocally === true,
                    });
                    replayed++;
                    this.network.unsyncData.shift();
                    this._unpersistQueueEntry(data.uuid);
                    const params = data.args[0];
                    if (data.restored && params?.type === "write") {
                        await this.readBackReplayedWrite(params);
                    }
                    if (params?.type === "write" && this.deviceSync?.dispatch) {
                        Promise.resolve(
                            this.deviceSync.dispatch({
                                [params.model]: params.ids.map((id) => ({ id })),
                            }),
                        ).catch(() => {});
                    }
                } catch (error) {
                    log.logic("[queue] replay failed", () => ({
                        uuid: data.uuid,
                        try: data.try,
                        connectionLost: error instanceof ConnectionLostError,
                        rpcError: error instanceof RPCError,
                        error: error?.message,
                    }));
                    if (error instanceof ConnectionLostError) {
                        endSync({ replayed, connectionLost: true });
                        throw error;
                    }
                    if (!(error instanceof RPCError)) {
                        data.try = (data.try ?? 1) + 1;
                        if (data.try <= MAX_SYNC_ATTEMPTS) {
                            await this._persistQueueEntry(data);
                            throw error;
                        }
                        logPosMessage(
                            "DataService",
                            "syncData",
                            `A queued offline operation failed ${MAX_SYNC_ATTEMPTS} times client-side and will not be retried`,
                            CONSOLE_COLOR,
                            [error, data],
                        );
                    }
                    this.network.unsyncData.shift();
                    this._unpersistQueueEntry(data.uuid);
                    this.network.deadSyncData.push({ ...data, error });
                    log.lifecycle("[queue] dead", () => ({
                        uuid: data.uuid,
                        dead: this.network.deadSyncData.length,
                    }));
                    logPosMessage(
                        "DataService",
                        "syncData",
                        "A queued offline operation was rejected by the server and will not be retried",
                        CONSOLE_COLOR,
                        [error, data],
                    );
                }
            }
        });
        endSync({ replayed, pending: this.network.unsyncData.length });
    }

    // a restored write may have committed before the reload and been overwritten
    // since (its replay is then answered without being applied), or not: only the
    // server knows. databaseTable rows are the till's own and are left alone
    async readBackReplayedWrite({ model, ids }) {
        if (!this.models[model] || this.opts.databaseTable[model] || !ids?.length) {
            return;
        }
        try {
            await this.read(model, ids);
        } catch (error) {
            logPosMessage(
                "DataService",
                "readBackReplayedWrite",
                `Could not re-read ${model} after replaying a restored write`,
                CONSOLE_COLOR,
                [error],
            );
        }
    }

    async loadServerOrders(domain) {
        const endLoad = log.perf("loadServerOrders");
        log.pipeline("loadServerOrders", () => ({ domain }));
        const result = await this.callRelated(
            "pos.order",
            "read_pos_orders",
            [domain],
            {},
            false,
            true,
        );
        const config = this.models["pos.config"].get(odoo.pos_config_id);
        const session = this.models["pos.session"].get(odoo.pos_session_id);
        const orders = result["pos.order"] || [];
        for (const order of orders) {
            if (!order.isDirty()) {
                order.serializeForORM();
            }
            order.config_id = config;
            order.session_id = session;
        }
        endLoad({ orders: orders.length, lines: result["pos.order.line"]?.length });
        return orders;
    }

    async checkAndDeleteMissingOrders(results) {
        if (results && results["pos.order"]) {
            const ids = new Set(
                results["pos.order"].filter((o) => o.isSynced).map((o) => o.id),
            );
            if (ids.size) {
                const orders = await this.loadServerOrders([["id", "in", [...ids]]]);
                const serverIds = orders.map((r) => r.id);
                const missing = [...ids].filter((id) => !serverIds.includes(id));
                log.logic("checkAndDeleteMissingOrders", () => ({
                    local: ids.size,
                    server: serverIds.length,
                    missing,
                }));
                for (const id of missing) {
                    this.localDeleteCascade(this.models["pos.order"].get(id));
                }
            }
        }
    }

    async write(model, ids, vals) {
        const values = { ...vals };
        delete values.id;
        const records = [...new Set(ids)]
            .map((id) => this.models[model].get(id))
            .filter(Boolean);
        if (!this.optimisticUpdates.has(model)) {
            this.optimisticUpdates.set(
                model,
                new OptimisticUpdates(this.models[model]),
            );
        }
        const update = this.optimisticUpdates.get(model).apply(records, values);
        const serverIds = records
            .filter((record) => typeof record.id === "number")
            .map((record) => record.id);
        log.lifecycle("write", () => ({
            model,
            ids,
            local: records.length,
            server: serverIds.length,
            keys: Object.keys(values),
        }));
        try {
            if (serverIds.length) {
                await this.ormWrite(model, serverIds, values, true, true);
            }
        } catch (error) {
            log.logic("write: rollback optimistic", () => ({ model, ids }));
            update.rollback();
            throw error;
        }
        update.commit();
        return records;
    }

    async delete(model, ids) {
        const records = [...new Set(ids)]
            .map((id) => this.models[model].get(id))
            .filter(Boolean);
        const serverIds = records
            .filter((record) => typeof record.id === "number")
            .map((record) => record.id);
        log.lifecycle("delete", () => ({
            model,
            ids,
            local: records.length,
            server: serverIds.length,
        }));
        if (serverIds.length) {
            await this.ormDelete(model, serverIds);
        }
        for (const record of records) {
            record.delete();
        }
        return records.map((record) => record.id);
    }

    async searchRead(model, domain = [], fields = [], options = {}, queue = false) {
        return await this.execute({
            type: "search_read",
            model,
            args: domain,
            fields,
            options,
            queue,
        });
    }

    async read(model, ids, fields = [], options = [], queue = false) {
        return await this.execute({
            type: "read",
            model,
            ids,
            fields,
            options,
            queue,
        });
    }

    async call(model, method, args = [], kwargs = {}, queue = false) {
        return await this.execute({
            type: "call",
            model,
            method,
            args,
            kwargs,
            queue,
        });
    }

    async silentCall(model, method, args = [], kwargs = {}, queue = false) {
        try {
            return await this.execute({
                type: "call",
                model,
                method,
                args,
                kwargs,
                queue,
            });
        } catch (e) {
            logPosMessage(
                "DataService",
                "silentCall",
                "Silent call failed",
                CONSOLE_COLOR,
                [e],
            );
            return false;
        }
    }

    async callRelated(
        model,
        method,
        args = [],
        kwargs = {},
        queue = false,
        loadMessingRecords = false,
    ) {
        let data = await this.execute({
            type: "call",
            model,
            method,
            args,
            kwargs,
            queue,
        });
        if (isQueued(data)) {
            return data;
        }

        if (loadMessingRecords) {
            data = await this.missingRecursive(data);
        }

        log.pipeline("callRelated: connect", () => ({
            model,
            method,
            loadMessingRecords,
            models: data
                ? Object.fromEntries(
                      Object.entries(data).map(([name, rows]) => [
                          name,
                          Array.isArray(rows) ? rows.length : null,
                      ]),
                  )
                : null,
        }));
        if (data) {
            this.deviceSync?.dispatch && this.deviceSync.dispatch(data);
            const result = this.models.connectNewData(data);
            this.syncServerDataInIndexedDB(data);
            return result;
        }
        return false;
    }

    async create(model, values, queue = true) {
        return await this.execute({ type: "create", model, values, queue });
    }

    async ormWrite(model, ids, values, queue = true, optimistic = false) {
        const result = await this.execute({
            type: "write",
            model,
            ids,
            values,
            queue,
            optimistic,
        });
        if (!isQueued(result) && this.deviceSync?.dispatch) {
            Promise.resolve(
                this.deviceSync.dispatch({ [model]: ids.map((id) => ({ id })) }),
            ).catch(() => {});
        }
        return result;
    }

    async ormDelete(model, ids, queue = true) {
        return await this.execute({ type: "delete", model, ids, queue });
    }

    localDeleteCascade(record, removeFromServer = false) {
        const recordModel = record.model.name;

        const cascadeDeleteModels = new Set(this.opts.cascadeDeleteModels);
        const databaseTable = this.opts.databaseTable;

        const relationsToDelete = Object.values(this.relations[recordModel])
            .filter((rel) => cascadeDeleteModels.has(rel.relation))
            .map((rel) => rel.name);
        const recordsToDelete = relationsToDelete.flatMap(
            (relation) => record[relation] || [],
        );

        const idbKey = (rec) => rec[databaseTable[rec.model.name]?.key || "id"];
        log.lifecycle("localDeleteCascade", () => ({
            model: recordModel,
            id: record.id,
            removeFromServer,
            relations: relationsToDelete,
            cascade: recordsToDelete.length,
        }));
        this.deleteRecordsInIndexedDB(recordModel, [idbKey(record)]);
        for (const item of recordsToDelete) {
            this.deleteRecordsInIndexedDB(item.model.name, [idbKey(item)]);
            item.delete({ silent: !removeFromServer });
        }

        const result = record.delete({ silent: !removeFromServer });
        return result;
    }

    async preLoadData(data) {
        return data;
    }

    isLimitedLoading() {
        const url = new URL(window.location.href);
        const limitedLoading =
            url.searchParams.get("limited_loading") === "0" ? false : true;
        log.logic("isLimitedLoading", () => ({ limitedLoading }));

        if (!limitedLoading) {
            url.searchParams.delete("limited_loading");
            window.history.replaceState({}, "", url);
        }

        return limitedLoading;
    }
}

export const PosDataService = {
    dependencies: PosData.serviceDependencies,
    async start(env, deps) {
        return new PosData(env, deps).ready;
    },
};

registry.category("services").add("pos_data", PosDataService);
