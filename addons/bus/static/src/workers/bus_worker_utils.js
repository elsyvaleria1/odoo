/** @odoo-module native */
export function debounce(func, wait) {
    let timeout;
    function debounced() {
        const context = this;
        const args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(() => {
            timeout = null;
            func.apply(context, args);
        }, wait);
    }
    debounced.cancel = function () {
        clearTimeout(timeout);
        timeout = null;
    };
    return debounced;
}

export class Deferred {
    constructor() {
        const { promise, resolve, reject } = Promise.withResolvers();
        return Object.assign(promise, { resolve, reject });
    }
}

export class Logger {
    static LOG_TTL = 24 * 60 * 60 * 1000;
    static gcInterval = null;
    static instances = [];
    _db;

    static async gcOutdatedLogs() {
        const threshold = Date.now() - Logger.LOG_TTL;
        for (const logger of this.instances) {
            if (!logger._db && !logger._dbPromise) {
                continue;
            }
            try {
                await logger._ensureDatabaseAvailable();
                await new Promise((res, rej) => {
                    const transaction = logger._db.transaction("logs", "readwrite");
                    const store = transaction.objectStore("logs");
                    const req = store
                        .index("timestamp")
                        .openCursor(IDBKeyRange.upperBound(threshold));
                    req.onsuccess = (event) => {
                        const cursor = event.target.result;
                        if (cursor) {
                            cursor.delete();
                            cursor.continue();
                        }
                    };
                    req.onerror = (e) => rej(e.target.error);
                    transaction.oncomplete = res;
                    transaction.onerror = (e) => rej(e.target.error);
                });
            } catch (error) {
                logger._forgetDatabase();
                console.error(
                    `Failed to clear logs for logger "${logger._name}":`,
                    error,
                );
            }
        }
    }

    constructor(name) {
        this._name = name;
        Logger.instances.push(this);
    }

    static _ensureGcScheduled() {
        Logger.gcInterval ??= setInterval(
            () => Logger.gcOutdatedLogs(),
            Logger.LOG_TTL,
        );
    }

    _forgetDatabase() {
        this._db = null;
        this._dbPromise = null;
    }

    close() {
        this._closed = true;
        Logger.instances = Logger.instances.filter((logger) => logger !== this);
        this._db?.close();
        this._forgetDatabase();
    }

    async _ensureDatabaseAvailable() {
        if (this._db) {
            return;
        }
        this._dbPromise ??= new Promise((res, rej) => {
            const request = indexedDB.open(this._name, 1);
            request.onsuccess = (event) => {
                if (this._closed) {
                    event.target.result.close();
                    rej(new Error(`Logger "${this._name}" is closed`));
                    return;
                }
                this._db = event.target.result;
                this._db.onclose = () => this._forgetDatabase();
                this._db.onversionchange = () => {
                    this._db?.close();
                    this._forgetDatabase();
                };
                res();
            };
            request.onupgradeneeded = (event) => {
                if (!event.target.result.objectStoreNames.contains("logs")) {
                    const store = event.target.result.createObjectStore("logs", {
                        autoIncrement: true,
                    });
                    store.createIndex("timestamp", "timestamp", { unique: false });
                }
            };
            request.onerror = (e) => {
                this._forgetDatabase();
                rej(e.target.error);
            };
        });
        return this._dbPromise;
    }

    async log(message) {
        await this._ensureDatabaseAvailable();
        Logger._ensureGcScheduled();
        let transaction;
        try {
            transaction = this._db.transaction("logs", "readwrite");
        } catch (error) {
            this._forgetDatabase();
            throw error;
        }
        const store = transaction.objectStore("logs");
        const addRequest = store.add({ timestamp: Date.now(), message });
        return new Promise((res, rej) => {
            addRequest.onsuccess = res;
            addRequest.onerror = (e) => rej(e.target.error);
        });
    }

    async getLogs() {
        await this._ensureDatabaseAvailable();
        Logger._ensureGcScheduled();
        await Logger.gcOutdatedLogs();
        const transaction = this._db.transaction("logs", "readonly");
        const store = transaction.objectStore("logs");
        const request = store.getAll();
        return new Promise((res, rej) => {
            request.onsuccess = (ev) =>
                res(ev.target.result.map(({ message }) => message));
            request.onerror = (e) => rej(e.target.error);
        });
    }
}
