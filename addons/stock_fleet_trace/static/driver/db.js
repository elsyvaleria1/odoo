const DB_NAME = "stock_fleet_trace_driver";
const DB_VERSION = 1;

let dbPromise = null;

function promisify(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

function open() {
    if (!dbPromise) {
        dbPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = () => {
                const db = request.result;
                db.createObjectStore("meta");
                db.createObjectStore("packages", { keyPath: "trip.id" });
                const events = db.createObjectStore("events", {
                    keyPath: "seq",
                    autoIncrement: true,
                });
                events.createIndex("batch_id", "batch_id");
                events.createIndex("client_uuid", "event.client_uuid", {
                    unique: true,
                });
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => reject(request.error);
        });
    }
    return dbPromise;
}

async function store(name, mode = "readonly") {
    const db = await open();
    return db.transaction(name, mode).objectStore(name);
}

export async function getMeta(key, fallback = null) {
    const value = await promisify((await store("meta")).get(key));
    return value === undefined ? fallback : value;
}

export async function setMeta(key, value) {
    return promisify((await store("meta", "readwrite")).put(value, key));
}

export async function getPackage(tripId) {
    return (await promisify((await store("packages")).get(tripId))) || null;
}

export async function getPackages() {
    return promisify((await store("packages")).getAll());
}

export async function putPackage(pkg) {
    return promisify((await store("packages", "readwrite")).put(pkg));
}

/**
 * @param {number} tripId
 * @returns {Promise<Object[]>}
 */
export async function getTripEvents(tripId) {
    const index = (await store("events")).index("batch_id");
    const records = await promisify(index.getAll(tripId));
    return records.sort((a, b) => a.seq - b.seq);
}

export async function getAllEvents() {
    return promisify((await store("events")).getAll());
}

export async function addEvent(record) {
    return promisify((await store("events", "readwrite")).add(record));
}

/**
 * @param {Object[]} records
 * @param {Object} result
 */
export async function markSynced(records, result) {
    const db = await open();
    const tx = db.transaction("events", "readwrite");
    const events = tx.objectStore("events");
    for (const record of records) {
        const answer = result[record.event.client_uuid];
        if (answer) {
            events.put({
                ...record,
                sync: "sent",
                state: answer.state,
                error: answer.error || false,
            });
        }
    }
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}
