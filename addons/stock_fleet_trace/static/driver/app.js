// Driver screen: works a delivery trip on the phone without connection.
// The page is rendered by /stock_fleet_trace/driver with its translated terms in
// <body data-boot>, cached by the service worker, and syncs the event queue
// whenever the phone has signal.

import { hashEvent } from "./canonical.js";
import * as db from "./db.js";

const BASE = "/stock_fleet_trace";
const SYNC_INTERVAL = 30000;
const FIX_MAX_AGE = 120000;
const FINAL_EVENTS = ["deliver", "partial", "not_delivered"];
// A request that gets no answer in this time is treated as no signal; sending
// events waits longer, since the server applies them before it answers.
const RPC_TIMEOUT = 15000;
const EVENTS_TIMEOUT = 90000;
// Events per request: a weak signal carries a few at a time.
const SYNC_CHUNK = 5;
// Final events the server did not apply leave the stop open again.
const REOPENING_STATES = ["review", "dismissed"];
// Camera formats: lot labels come as QR, Code 128, DataMatrix, EAN or Code 39.
const BARCODE_FORMATS = ["qr_code", "code_128", "data_matrix", "ean_13", "code_39"];

const boot = JSON.parse(document.body.dataset.boot || "{}");
const T = boot.terms || {};

const state = {
    screen: "trips",
    trips: [],
    pkg: null,
    events: [],
    stopId: null,
    form: null,
    syncing: false,
    online: navigator.onLine,
    sessionExpired: false,
    lastSync: null,
    pending: 0,
    othersPending: 0,
    deviceUuid: null,
};

class SessionExpired extends Error {}
class ServerError extends Error {}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Replace Python-style %(name)s placeholders of a translated term. */
function fmt(term, values = {}) {
    return (term || "").replace(/%\((\w+)\)s/g, (match, name) =>
        name in values ? String(values[name]) : match,
    );
}

function h(tag, attrs = {}, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
        if (value === null || value === undefined || value === false) {
            continue;
        }
        if (key.startsWith("on")) {
            el.addEventListener(key.slice(2), value);
        } else if (key === "class") {
            el.className = value;
        } else if (key in el && typeof value !== "string") {
            el[key] = value;
        } else {
            el.setAttribute(key, value === true ? "" : value);
        }
    }
    for (const child of children.flat(Infinity)) {
        if (child !== null && child !== undefined && child !== false) {
            el.append(child instanceof Node ? child : String(child));
        }
    }
    return el;
}

function pad(number) {
    return String(number).padStart(2, "0");
}

/** Local time as ISO 8601 with its UTC offset, e.g. 2026-09-29T09:30:00-06:00. */
function isoWithOffset(date) {
    const offset = -date.getTimezoneOffset();
    const sign = offset >= 0 ? "+" : "-";
    const minutes = Math.abs(offset);
    return (
        `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
        `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}` +
        `${sign}${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`
    );
}

function formatTime(iso) {
    if (!iso) {
        return T.never;
    }
    const date = new Date(iso);
    return `${pad(date.getDate())}/${pad(date.getMonth() + 1)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function same(a, b) {
    return (a || "").trim().toUpperCase() === (b || "").trim().toUpperCase();
}

function vibrate(pattern) {
    if (navigator.vibrate) {
        navigator.vibrate(pattern);
    }
}

// ---------------------------------------------------------------------------
// Server
// ---------------------------------------------------------------------------

async function rpc(url, params, timeout = RPC_TIMEOUT) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    let response;
    try {
        response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                id: Date.now(),
                params,
            }),
            signal: controller.signal,
        });
    } catch {
        // No signal, or a signal too weak to answer in time.
        throw new TypeError("offline");
    } finally {
        clearTimeout(timer);
    }
    if (response.redirected && response.url.includes("/web/login")) {
        // Odoo sends an expired session to the login page.
        throw new SessionExpired();
    }
    const type = response.headers.get("content-type") || "";
    if (!response.ok || !type.includes("json")) {
        throw new ServerError(`HTTP ${response.status}`);
    }
    const body = await response.json();
    if (body.error) {
        const name = (body.error.data && body.error.data.name) || "";
        if (body.error.code === 100 || name.includes("SessionExpired")) {
            throw new SessionExpired();
        }
        throw new ServerError(
            (body.error.data && body.error.data.message) || body.error.message,
        );
    }
    return body.result;
}

/** Run ``task`` holding ``name`` across every tab of this phone. */
function withLock(name, task) {
    if (navigator.locks) {
        return navigator.locks.request(name, task);
    }
    return task();
}

// ---------------------------------------------------------------------------
// Location
// ---------------------------------------------------------------------------

let lastFix = null;

function watchLocation() {
    if (!navigator.geolocation) {
        return;
    }
    navigator.geolocation.watchPosition(
        (position) => {
            lastFix = position;
        },
        () => {},
        { enableHighAccuracy: true, maximumAge: 60000 },
    );
}

/** The phone's position, best effort: null when there is no fix in time. */
function currentPosition() {
    if (lastFix && Date.now() - lastFix.timestamp < FIX_MAX_AGE) {
        return Promise.resolve(lastFix);
    }
    if (!navigator.geolocation) {
        return Promise.resolve(null);
    }
    return new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                lastFix = position;
                resolve(position);
            },
            () => resolve(lastFix),
            { enableHighAccuracy: true, timeout: 6000, maximumAge: FIX_MAX_AGE },
        );
    });
}

function round7(value) {
    return Math.round(value * 1e7) / 1e7;
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

let chainLock = Promise.resolve();

/**
 * Capture an immutable event, chained to the trip's previous one, and queue it.
 *
 * @param {string} eventType deliver, partial, not_delivered, scan or incident
 * @param {number|false} pickingId the stop it concerns
 * @param {Object} payload what the server applier reads
 */
function captureEvent(eventType, pickingId, payload) {
    const tripId = state.pkg.trip.id;
    const chainHead = state.pkg.chain_head || "";
    const capturedAt = isoWithOffset(new Date());
    const run = async () => {
        const position = await currentPosition();
        const previous = await db.getTripEvents(tripId);
        const event = {
            client_uuid: crypto.randomUUID(),
            event_type: eventType,
            picking_id: pickingId || false,
            payload,
            captured_at: capturedAt,
            latitude: position ? round7(position.coords.latitude) : null,
            longitude: position ? round7(position.coords.longitude) : null,
            device_uuid: state.deviceUuid,
            prev_hash: previous.length ? previous.at(-1).event.event_hash : chainHead,
        };
        event.event_hash = await hashEvent(event);
        await db.addEvent({
            batch_id: tripId,
            user_id: boot.user_id,
            sync: "queued",
            state: "queued",
            error: false,
            event,
        });
    };
    // Serialized, here and across tabs: two events captured at once must not
    // chain to the same hash.
    const locked = () => withLock(`sft-chain-${tripId}`, run);
    chainLock = chainLock.then(locked, locked);
    return chainLock;
}

/** Whether a stored record belongs to the user logged in on this phone. */
function mine(record) {
    return !record.user_id || record.user_id === boot.user_id;
}

async function loadEvents() {
    state.events = state.pkg ? await db.getTripEvents(state.pkg.trip.id) : [];
    const all = await db.getAllEvents();
    const queued = all.filter((record) => record.sync === "queued");
    state.pending = queued.filter(mine).length;
    state.othersPending = queued.length - state.pending;
}

function stopEvents(pickingId) {
    return state.events.filter((record) => record.event.picking_id === pickingId);
}

/** The stop's status: the server's, else the last result captured on the phone. */
function stopStatus(stop) {
    const final = stopEvents(stop.picking_id)
        .filter(
            (record) =>
                FINAL_EVENTS.includes(record.event.event_type) &&
                (stop.state === "done" || !REOPENING_STATES.includes(record.state)),
        )
        .at(-1);
    if (final) {
        return {
            code: final.event.event_type,
            label: T[`status_${final.event.event_type}`],
            record: final,
        };
    }
    if (stop.state === "done") {
        return { code: "done", label: T.status_done };
    }
    if (stop.state === "cancel") {
        return { code: "cancel", label: T.status_cancel };
    }
    if (stop.state === "left") {
        // No longer on the trip on the server: nothing left to do here.
        return { code: "left", label: T.status_left };
    }
    return { code: "todo", label: T.status_todo };
}

function stopScans(pickingId) {
    return stopEvents(pickingId).filter(
        (record) =>
            record.event.event_type === "scan" &&
            !REOPENING_STATES.includes(record.state),
    );
}

/**
 * Units counted at a stop for a lot (empty lot: a product without one). One
 * scan counts in full: the slip counts every line, a lot label all of its lot.
 */
function scannedQuantity(stop, lot, onBoard) {
    const scans = stopScans(stop.picking_id);
    if (scans.some((record) => same(record.event.payload.code, stop.name))) {
        return onBoard;
    }
    if (!lot) {
        return 0;
    }
    const lotScans = scans.filter((record) => same(record.event.payload.code, lot));
    if (lotScans.some((record) => !record.event.payload.quantity)) {
        return onBoard;
    }
    return Math.min(
        onBoard,
        lotScans.reduce((total, record) => total + record.event.payload.quantity, 0),
    );
}

/**
 * Why Delivered would be refused, as the server checks it: once lots were
 * scanned at a stop, every line must be scanned in full. Null when fine.
 */
function deliverBlockedByScans(stop) {
    const scans = stopScans(stop.picking_id);
    if (!scans.length) {
        return null;
    }
    const onBoard = new Map();
    for (const line of stop.lines) {
        const key = `${line.product_id}|${line.lot || ""}`;
        onBoard.set(key, (onBoard.get(key) || 0) + line.quantity);
    }
    for (const [key, quantity] of onBoard) {
        const lot = key.split("|")[1];
        const scanned = scannedQuantity(stop, lot, quantity);
        // A product without lot counts only once the slip was scanned.
        if (lot && scanned !== quantity) {
            return T.deliver_scans_incomplete;
        }
    }
    return null;
}

// ---------------------------------------------------------------------------
// Sync
// ---------------------------------------------------------------------------

let syncAgain = false;

async function sync() {
    if (!navigator.onLine) {
        return;
    }
    if (state.syncing) {
        // Captured while a sync runs: send it right after, not in 30 s.
        syncAgain = true;
        return;
    }
    syncAgain = false;
    state.syncing = true;
    updateSyncBar();
    const errors = [];
    try {
        await withLock("sft-sync", () => sendQueued(errors));
        if (state.pkg) {
            // Best effort: the stops' server state.
            await refreshPackage(state.pkg.trip.id).catch(() => {});
        }
        state.sessionExpired = false;
        state.lastSync = new Date().toISOString();
        await db.setMeta("last_sync", state.lastSync);
    } catch (error) {
        if (error instanceof SessionExpired) {
            state.sessionExpired = true;
        } else if (!(error instanceof TypeError)) {
            // TypeError is no signal: the queue waits for the next try.
            errors.push(error.message);
        }
    } finally {
        state.syncing = false;
        await loadEvents();
        if (errors.length) {
            showMessage("error", fmt(T.sync_error, { error: errors.join("; ") }));
        }
        updateSyncBar();
        if (!state.form) {
            render();
        }
    }
    if (syncAgain) {
        sync();
    }
}

/**
 * Send this user's queued events, trip by trip, a few at a time in chain
 * order. A trip's last hash (its head) goes with the last chunk only, once
 * everything before it arrived.
 */
async function sendQueued(errors) {
    const all = (await db.getAllEvents()).filter(mine);
    const tripIds = [
        ...new Set(all.filter((r) => r.sync === "queued").map((r) => r.batch_id)),
    ];
    for (const tripId of tripIds) {
        const events = (await db.getTripEvents(tripId)).filter(mine);
        const queued = events.filter((record) => record.sync === "queued");
        try {
            for (let start = 0; start < queued.length; start += SYNC_CHUNK) {
                const chunk = queued.slice(start, start + SYNC_CHUNK);
                const last = start + SYNC_CHUNK >= queued.length;
                const result = await rpc(
                    `${BASE}/trip/${tripId}/events`,
                    {
                        events: chunk.map((record) => record.event),
                        head: last ? events.at(-1).event.event_hash : null,
                    },
                    EVENTS_TIMEOUT,
                );
                await db.markSynced(chunk, result);
            }
        } catch (error) {
            if (!(error instanceof ServerError)) {
                throw error;
            }
            errors.push(error.message);
        }
    }
}

async function refreshPackage(tripId) {
    // The phone's last event tells the trip it still holds some, even when
    // sending them fails: it cannot return until they arrive or the phone is
    // released.
    const own = (await db.getTripEvents(tripId)).filter(mine);
    const head = own.length ? own.at(-1).event.event_hash : null;
    const pkg = await rpc(`${BASE}/trip/${tripId}/package`, { head });
    pkg.downloaded_at = new Date().toISOString();
    pkg.user_id = boot.user_id;
    // A stop not delivered leaves the trip on the server; the phone keeps
    // showing the stops it recorded something for, with that result.
    const previous = await db.getPackage(tripId);
    if (previous) {
        const recorded = new Set(
            (await db.getTripEvents(tripId)).map((record) => record.event.picking_id),
        );
        const current = new Set(pkg.stops.map((stop) => stop.picking_id));
        for (const stop of previous.stops) {
            if (!current.has(stop.picking_id) && recorded.has(stop.picking_id)) {
                pkg.stops.push({ ...stop, state: "left" });
            }
        }
    }
    await db.putPackage(pkg);
    if (state.pkg && state.pkg.trip.id === tripId) {
        state.pkg = pkg;
    }
    return pkg;
}

let downloading = null;

/** Download, one after the other, the package of every trip in ``trips``. */
function downloadAll(trips) {
    if (downloading) {
        return downloading;
    }
    downloading = (async () => {
        for (const trip of trips) {
            try {
                await refreshPackage(trip.id);
            } catch (error) {
                if (!(error instanceof ServerError)) {
                    break; // No signal or session: the next sync tries again.
                }
            }
        }
    })().finally(() => {
        downloading = null;
        if (state.screen === "trips" && !state.form) {
            loadTrips().then(render);
        }
    });
    return downloading;
}

/**
 * The trips to show: this user's cached list and downloaded packages at once,
 * then the server's list when ``online`` and there is signal.
 */
async function loadTrips(online = false) {
    const packages = (await db.getPackages()).filter(mine);
    const cached = await db.getMeta(`trips_${boot.user_id}`, []);
    let trips = cached;
    if (online && navigator.onLine) {
        try {
            trips = await rpc(`${BASE}/driver/trips`, {});
            await db.setMeta(`trips_${boot.user_id}`, trips);
            // Every trip the driver has is on the phone before the signal goes,
            // not only the ones opened with signal.
            downloadAll(trips);
            state.sessionExpired = false;
        } catch (error) {
            if (error instanceof SessionExpired) {
                state.sessionExpired = true;
            } else if (error instanceof ServerError) {
                showMessage("error", error.message);
            }
        }
    }
    const listed = new Set(trips.map((trip) => trip.id));
    trips = [...trips];
    // Downloaded trips stay reachable offline even when no longer listed.
    for (const pkg of packages) {
        if (!listed.has(pkg.trip.id)) {
            trips.push({ ...pkg.trip, stop_count: pkg.stops.length });
        }
    }
    const downloaded = new Set(packages.map((pkg) => pkg.trip.id));
    state.trips = trips.map((trip) => ({
        ...trip,
        downloaded: downloaded.has(trip.id),
    }));
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

async function openTrip(tripId) {
    let pkg = await db.getPackage(tripId);
    if (pkg && !mine(pkg)) {
        pkg = null;
    }
    if (!pkg) {
        showMessage("info", T.downloading);
        try {
            pkg = await refreshPackage(tripId);
            clearMessage();
        } catch (error) {
            if (error instanceof SessionExpired) {
                state.sessionExpired = true;
            }
            showMessage(
                "error",
                error instanceof ServerError ? error.message : T.download_failed,
            );
            updateSyncBar();
            return;
        }
    }
    state.pkg = pkg;
    state.screen = "trip";
    state.stopId = null;
    state.form = null;
    await loadEvents();
    render();
    // The downloaded trip opens at once; the server's state follows if there is signal.
    refreshPackage(tripId)
        .then(() => !state.form && state.screen !== "trips" && render())
        .catch(() => {});
}

function openStop(pickingId) {
    state.screen = "stop";
    state.stopId = pickingId;
    state.form = null;
    render();
    window.scrollTo(0, 0);
}

function currentStop() {
    return (
        state.pkg && state.pkg.stops.find((stop) => stop.picking_id === state.stopId)
    );
}

async function goBack() {
    state.form = null;
    if (state.screen === "stop") {
        state.screen = "trip";
        state.stopId = null;
    } else {
        state.screen = "trips";
        state.pkg = null;
        await loadTrips();
        loadTrips(true).then(() => state.screen === "trips" && render());
    }
    render();
}

// ---------------------------------------------------------------------------
// Scanning
// ---------------------------------------------------------------------------

/**
 * The code as the trip names it: without a scanner's symbology prefix, and the
 * lot alone from a GS1 label that carries it under application identifier 10.
 */
function normalizeCode(raw) {
    const text = (raw || "").trim();
    const symbology = text.match(/^\][A-Za-z]\d/);
    let code = symbology ? text.slice(3) : text;
    const printed = code.match(/\(10\)([^(]+)/);
    if (printed) {
        return printed[1].trim();
    }
    // Raw GS1: application identifiers one after another, variable ones ended
    // by the group separator. Only a GS1 symbol, or data that reads as one, is parsed.
    if (symbology || code.includes("\u001d") || /^01\d{14}/.test(code)) {
        const fixed = { "01": 14, "02": 14, 11: 6, 13: 6, 15: 6, 17: 6 };
        while (code.length > 2) {
            const ai = code.slice(0, 2);
            if (ai in fixed) {
                code = code.slice(2 + fixed[ai]);
            } else if (ai === "10" || ai === "21") {
                const end = code.indexOf("\u001d");
                const value = end === -1 ? code.slice(2) : code.slice(2, end);
                if (ai === "10") {
                    return value.trim();
                }
                code = end === -1 ? "" : code.slice(end + 1);
            } else {
                break;
            }
        }
    }
    return (symbology ? text.slice(3) : text).split("\u001d").join("");
}

async function handleScan(raw) {
    const code = normalizeCode(raw);
    if (!code || !state.pkg || state.form) {
        return;
    }
    const pkg = state.pkg;
    const slip = pkg.stops.find((stop) => same(stop.name, code));
    if (slip) {
        vibrate(60);
        openStop(slip.picking_id);
        const units = slip.lines.reduce((total, line) => total + line.quantity, 0);
        const counted = stopScans(slip.picking_id).some((record) =>
            same(record.event.payload.code, slip.name),
        );
        if (stopStatus(slip).code === "todo" && !counted) {
            // One scan of the slip registers every unit of the delivery.
            await captureEvent("scan", slip.picking_id, { code: slip.name });
            await loadEvents();
            if (!state.form) {
                render();
            }
        }
        showMessage(
            "ok",
            fmt(T.scan_stop_full, {
                stop: slip.name,
                customer: slip.partner || "",
                units,
            }),
        );
        return;
    }
    if (same(pkg.trip.name, code)) {
        showMessage("info", fmt(T.scan_trip_sheet, { trip: pkg.trip.name }));
        return;
    }
    const matches = [];
    for (const stop of pkg.stops) {
        for (const line of stop.lines) {
            if (line.lot && same(line.lot, code)) {
                matches.push({ stop, line });
            }
        }
    }
    const stop = state.screen === "stop" ? currentStop() : null;
    if (!stop) {
        if (matches.length) {
            const stops = [...new Set(matches.map((m) => m.stop.name))].join(", ");
            showMessage("info", fmt(T.scan_lot_goes_to, { lot: code, stops }));
        } else {
            vibrate([200, 100, 200]);
            showMessage("warn", fmt(T.scan_unknown, { code, trip: pkg.trip.name }));
        }
        return;
    }
    let here = matches.filter((m) => m.stop.picking_id === stop.picking_id);
    // The same lot name on two products counts for the first, as the server does.
    here = here.filter((m) => m.line.product_id === here[0]?.line.product_id);
    if (!here.length) {
        vibrate([300, 100, 300, 100, 300]);
        if (matches.length) {
            const stops = [...new Set(matches.map((m) => m.stop.name))].join(", ");
            showMessage(
                "warn",
                fmt(T.scan_lot_other_stop, { lot: code, stop: stop.name, stops }),
            );
        } else {
            showMessage(
                "warn",
                fmt(T.scan_lot_not_on_board, { lot: code, stop: stop.name }),
            );
        }
        return;
    }
    const lot = here[0].line.lot;
    const onBoard = here.reduce((total, m) => total + m.line.quantity, 0);
    const scanned = scannedQuantity(stop, lot, onBoard);
    const status = stopStatus(stop);
    if (status.code !== "todo" || scanned >= onBoard) {
        // Checked, but not counted: the server would refuse the scan.
        vibrate(60);
        showMessage(
            "ok",
            fmt(T.scan_lot_ok, {
                lot,
                product: here[0].line.product,
                scanned,
                board: onBoard,
            }),
        );
        return;
    }
    // One scan of a lot label registers all of that lot for the stop.
    await captureEvent("scan", stop.picking_id, { code: lot });
    await loadEvents();
    vibrate(60);
    if (!state.form) {
        render();
    }
    showMessage(
        "ok",
        fmt(T.scan_lot_ok, {
            lot,
            product: here[0].line.product,
            scanned: onBoard,
            board: onBoard,
        }),
    );
    sync();
}

let cameraStream = null;

async function openCamera() {
    if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
        showMessage("warn", T.camera_unsupported);
        return;
    }
    let detector;
    try {
        const supported = await window.BarcodeDetector.getSupportedFormats();
        detector = new window.BarcodeDetector({
            formats: BARCODE_FORMATS.filter((format) => supported.includes(format)),
        });
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" },
        });
    } catch {
        showMessage("warn", T.camera_unavailable);
        return;
    }
    const video = h("video", { playsinline: true, autoplay: true, muted: true });
    video.srcObject = cameraStream;
    const overlay = h(
        "div",
        { class: "sft-camera" },
        video,
        h("div", { class: "sft-camera-frame" }),
        h("button", { class: "sft-btn sft-btn-light", onclick: closeCamera }, T.cancel),
    );
    document.body.append(overlay);
    const tick = async () => {
        if (!cameraStream) {
            return;
        }
        try {
            const codes = video.readyState >= 2 ? await detector.detect(video) : [];
            if (codes.length) {
                closeCamera();
                handleScan(codes[0].rawValue);
                return;
            }
        } catch {
            // A frame that cannot be read yet; try the next one.
        }
        setTimeout(tick, 200);
    };
    tick();
}

function closeCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
    }
    document.querySelectorAll(".sft-camera").forEach((el) => el.remove());
}

function scanBox() {
    const input = h("input", {
        type: "text",
        class: "sft-input sft-scan-input",
        placeholder: T.scan_placeholder,
        autocomplete: "off",
        autocapitalize: "characters",
        enterkeyhint: "go",
        id: "sft-scan",
    });
    const submit = (ev) => {
        ev.preventDefault();
        const value = input.value;
        input.value = "";
        handleScan(value);
    };
    return h(
        "form",
        { class: "sft-scan", onsubmit: submit },
        input,
        h("button", { type: "submit", class: "sft-btn sft-btn-secondary" }, T.check),
        "BarcodeDetector" in window
            ? h(
                  "button",
                  {
                      type: "button",
                      class: "sft-btn sft-btn-primary",
                      onclick: openCamera,
                  },
                  T.camera,
              )
            : null,
    );
}

// ---------------------------------------------------------------------------
// Signature
// ---------------------------------------------------------------------------

function signaturePad() {
    const canvas = h("canvas", { class: "sft-signature", width: 600, height: 220 });
    const pad = { canvas, signed: false };
    const context = canvas.getContext("2d");
    context.lineWidth = 3;
    context.lineCap = "round";
    context.strokeStyle = "#111";
    let drawing = false;
    const point = (ev) => {
        const rect = canvas.getBoundingClientRect();
        return [
            ((ev.clientX - rect.left) * canvas.width) / rect.width,
            ((ev.clientY - rect.top) * canvas.height) / rect.height,
        ];
    };
    canvas.addEventListener("pointerdown", (ev) => {
        drawing = true;
        canvas.setPointerCapture(ev.pointerId);
        context.beginPath();
        context.moveTo(...point(ev));
    });
    canvas.addEventListener("pointermove", (ev) => {
        if (drawing) {
            context.lineTo(...point(ev));
            context.stroke();
            pad.signed = true;
        }
    });
    const stopDrawing = () => {
        drawing = false;
    };
    canvas.addEventListener("pointerup", stopDrawing);
    canvas.addEventListener("pointercancel", stopDrawing);
    pad.clear = () => {
        context.clearRect(0, 0, canvas.width, canvas.height);
        pad.signed = false;
    };
    /** Base64 PNG without the data: prefix, as the Image field stores it. */
    pad.value = () =>
        pad.signed
            ? canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "")
            : null;
    pad.element = h(
        "div",
        { class: "sft-field" },
        h("label", {}, T.signature),
        canvas,
        h(
            "button",
            { type: "button", class: "sft-btn sft-btn-light", onclick: pad.clear },
            T.clear,
        ),
    );
    return pad;
}

// ---------------------------------------------------------------------------
// Stop actions
// ---------------------------------------------------------------------------

function field(label, control, required = false) {
    return h(
        "div",
        { class: "sft-field" },
        h("label", {}, label, required ? " *" : ""),
        control,
    );
}

function select(options, placeholder) {
    return h(
        "select",
        { class: "sft-input" },
        h("option", { value: "" }, placeholder),
        options.map(([value, label]) => h("option", { value: String(value) }, label)),
    );
}

/**
 * The form of one action. Each returns its element and a builder that reads
 * the inputs and returns the payload, or throws a translated message.
 */
function actionForm(kind, stop) {
    const pkg = state.pkg;
    const receiver = h("input", {
        type: "text",
        class: "sft-input",
        autocomplete: "off",
    });
    const note = h("textarea", { class: "sft-input", rows: 3 });
    let pad = null;
    let fields = [];
    let build = null;
    const withReceiver = (payload) => {
        const name = receiver.value.trim();
        const signature = pad.value();
        if (name) {
            payload.receiver_name = name;
        }
        if (signature) {
            payload.signature = signature;
        }
        return payload;
    };
    if (kind === "deliver") {
        pad = signaturePad();
        fields = [field(T.receiver_name, receiver), pad.element];
        build = () => withReceiver({});
    } else if (kind === "partial") {
        pad = signaturePad();
        fields = [
            field(T.partial_note, note, true),
            field(T.receiver_name, receiver),
            pad.element,
        ];
        build = () => {
            if (!note.value.trim()) {
                throw new Error(T.note_required);
            }
            return withReceiver({ note: note.value.trim() });
        };
    } else if (kind === "not_delivered") {
        const reason = select(
            pkg.unbatch_reasons.map((r) => [r.id, r.name]),
            T.choose_reason,
        );
        fields = [field(T.reason, reason, true), field(T.note, note)];
        build = () => {
            if (!reason.value) {
                throw new Error(T.reason_required);
            }
            const payload = { reason_id: Number(reason.value) };
            if (note.value.trim()) {
                payload.note = note.value.trim();
            }
            return payload;
        };
    } else if (kind === "incident") {
        const type = select(
            pkg.incident_types.map((t) => [t.code, t.name]),
            T.choose_incident_type,
        );
        fields = [field(T.incident_type, type, true), field(T.description, note, true)];
        build = () => {
            if (!type.value || !note.value.trim()) {
                throw new Error(T.incident_required);
            }
            return {
                incident: { incident_type: type.value, description: note.value.trim() },
            };
        };
    }
    for (const plugin of window.sftDriverPlugins || []) {
        const extra = plugin.actionFields?.(kind, stop, pluginApi);
        if (extra) {
            fields.push(extra);
        }
    }
    const titles = {
        deliver: T.action_deliver,
        partial: T.action_partial,
        not_delivered: T.action_not_delivered,
        incident: T.action_incident,
    };
    const submit = async (ev) => {
        ev.preventDefault();
        let payload;
        try {
            payload = build();
        } catch (error) {
            showMessage("warn", error.message);
            return;
        }
        const button = ev.target.querySelector("button[type=submit]");
        button.disabled = true;
        button.textContent = T.saving;
        await captureEvent(kind, stop ? stop.picking_id : false, payload);
        state.form = null;
        await loadEvents();
        render();
        showMessage("ok", T.saved);
        sync();
    };
    return h(
        "form",
        { class: "sft-card sft-form", onsubmit: submit },
        h("h2", {}, titles[kind]),
        stop
            ? h("p", { class: "sft-muted" }, `${stop.name} · ${stop.partner || ""}`)
            : null,
        fields,
        h(
            "div",
            { class: "sft-row" },
            h(
                "button",
                {
                    type: "button",
                    class: "sft-btn sft-btn-light",
                    onclick: () => {
                        state.form = null;
                        render();
                    },
                },
                T.cancel,
            ),
            h("button", { type: "submit", class: "sft-btn sft-btn-primary" }, T.save),
        ),
    );
}

/**
 * What a plugin of another module (window.sftDriverPlugins) works with: its
 * ``actionFields(kind, stop, api)`` returns an element added to the form of a
 * stop action, or nothing.
 */
const pluginApi = {
    h,
    fmt,
    rpc,
    field,
    showMessage: (kind, text) => showMessage(kind, text),
    terms: T,
    isOnline: () => state.online,
};

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const app = document.getElementById("sft-app");

function showMessage(kind, text) {
    const box = document.getElementById("sft-message");
    if (!box) {
        return;
    }
    box.className = `sft-message sft-message-${kind}`;
    box.textContent = text;
    box.hidden = false;
}

function clearMessage() {
    const box = document.getElementById("sft-message");
    if (box) {
        box.hidden = true;
    }
}

function updateSyncBar() {
    const bar = document.getElementById("sft-sync");
    if (!bar) {
        return;
    }
    const parts = [
        state.online ? T.online : T.offline,
        fmt(T.pending_count, { count: state.pending }),
        fmt(T.last_sync, { time: formatTime(state.lastSync) }),
    ];
    if (state.othersPending) {
        // Captured by another driver on this phone: sent when that driver logs in.
        parts.push(fmt(T.other_user_pending, { count: state.othersPending }));
    }
    if (state.syncing) {
        parts.push(T.syncing);
    }
    bar.className = `sft-sync ${state.online ? "sft-sync-online" : "sft-sync-offline"}`;
    bar.replaceChildren(
        ...[
            h("span", {}, parts.join(" · ")),
            state.sessionExpired
                ? h(
                      "a",
                      {
                          class: "sft-session",
                          href: `/web/login?redirect=${encodeURIComponent(location.pathname + location.search)}`,
                      },
                      T.session_expired,
                  )
                : null,
            state.online && state.pending && !state.syncing
                ? h(
                      "button",
                      { class: "sft-btn sft-btn-small", onclick: sync },
                      T.sync_now,
                  )
                : null,
        ].filter(Boolean),
    );
}

function header(title, subtitle, back) {
    return h(
        "header",
        { class: "sft-header" },
        back
            ? h(
                  "button",
                  { class: "sft-back", onclick: goBack, "aria-label": T.back },
                  "‹",
              )
            : null,
        h(
            "div",
            {},
            h("h1", {}, title),
            subtitle ? h("div", { class: "sft-subtitle" }, subtitle) : null,
        ),
    );
}

function tripStateLabel(code) {
    return T[`trip_${code}`] || code || "";
}

function renderTrips() {
    const list = state.trips.length
        ? state.trips.map((trip) =>
              h(
                  "button",
                  { class: "sft-card sft-trip", onclick: () => openTrip(trip.id) },
                  h("strong", {}, trip.name),
                  h("span", {}, trip.vehicle || ""),
                  h(
                      "span",
                      { class: "sft-muted" },
                      tripStateLabel(trip.state),
                      trip.stop_count
                          ? ` · ${fmt(T.stop_count, { count: trip.stop_count })}`
                          : "",
                      trip.downloaded ? ` · ${T.downloaded}` : "",
                  ),
              ),
          )
        : [
              h(
                  "p",
                  { class: "sft-muted" },
                  state.online ? T.no_trips : T.no_trips_offline,
              ),
          ];
    return [
        header(T.my_trips, boot.user_name),
        h(
            "button",
            {
                class: "sft-btn sft-btn-light sft-wide",
                onclick: async () => {
                    await loadTrips();
                    render();
                },
            },
            T.refresh,
        ),
        ...list,
        h(
            "button",
            { class: "sft-btn sft-btn-light sft-wide", onclick: logOut },
            state.online ? T.log_out : T.log_out_offline,
        ),
    ];
}

function logOut() {
    // Logging out needs the server; queued events stay on the phone, kept per
    // user, and go out the next time this user signs in.
    if (!state.online) {
        return;
    }
    if (
        state.pending &&
        !window.confirm(fmt(T.log_out_pending, { count: state.pending }))
    ) {
        return;
    }
    const back = `/web/login?redirect=${encodeURIComponent("/stock_fleet_trace/driver")}`;
    location.href = `/web/session/logout?redirect=${encodeURIComponent(back)}`;
}

function renderTrip() {
    const pkg = state.pkg;
    const stops = pkg.stops.map((stop, index) => {
        const status = stopStatus(stop);
        const queued = stopEvents(stop.picking_id).some((r) => r.sync === "queued");
        const review = stopEvents(stop.picking_id).some((r) => r.state === "review");
        return h(
            "button",
            {
                class: `sft-card sft-stop sft-status-${status.code}`,
                onclick: () => openStop(stop.picking_id),
            },
            h("span", { class: "sft-stop-seq" }, String(index + 1)),
            h(
                "span",
                { class: "sft-stop-body" },
                h("strong", {}, stop.partner || stop.name),
                h("span", { class: "sft-muted" }, stop.name),
                h(
                    "span",
                    { class: "sft-badge" },
                    status.label,
                    queued ? ` · ${T.not_sent}` : "",
                    review ? ` · ${T.to_review}` : "",
                ),
            ),
        );
    });
    return [
        header(
            pkg.trip.name,
            [pkg.trip.vehicle, tripStateLabel(pkg.trip.state)]
                .filter(Boolean)
                .join(" · "),
            true,
        ),
        state.form ? null : scanBox(),
        state.form === "incident" ? actionForm("incident", null) : null,
        h("h2", {}, T.stops),
        stops.length ? stops : h("p", { class: "sft-muted" }, T.no_stops),
        state.form
            ? null
            : h(
                  "button",
                  {
                      class: "sft-btn sft-btn-warning sft-wide",
                      onclick: () => {
                          state.form = "incident";
                          render();
                      },
                  },
                  T.action_incident,
              ),
        h(
            "p",
            { class: "sft-muted sft-small" },
            fmt(T.package_downloaded, { time: formatTime(pkg.downloaded_at) }),
        ),
    ];
}

function renderStop() {
    const stop = currentStop();
    if (!stop) {
        state.screen = "trip";
        return renderTrip();
    }
    const status = stopStatus(stop);
    const lines = stop.lines.map((line) => {
        const scanned = scannedQuantity(stop, line.lot, line.quantity);
        return h(
            "tr",
            {},
            h("td", {}, line.product),
            h("td", {}, line.lot || "—"),
            h("td", { class: "sft-num" }, `${line.quantity} ${line.uom || ""}`),
            h(
                "td",
                { class: "sft-num" },
                line.lot ? `${Math.min(scanned, line.quantity)}` : "",
            ),
        );
    });
    const history = stopEvents(stop.picking_id)
        .filter((r) => r.event.event_type !== "scan")
        .map((r) =>
            h(
                "li",
                {},
                `${formatTime(r.event.captured_at)} · ${T[`status_${r.event.event_type}`] || r.event.event_type} · `,
                r.sync === "queued" ? T.not_sent : T[`state_${r.state}`] || r.state,
                r.error ? h("div", { class: "sft-error" }, r.error) : null,
            ),
        );
    const open = status.code === "todo";
    const action = (kind, cls) =>
        h(
            "button",
            {
                class: `sft-btn ${cls}`,
                onclick: () => {
                    // Refused here what the server would send to review.
                    const blocked =
                        kind === "deliver" ? deliverBlockedByScans(stop) : null;
                    if (blocked) {
                        vibrate([200, 100, 200]);
                        showMessage("warn", blocked);
                        return;
                    }
                    state.form = kind;
                    render();
                },
            },
            T[`action_${kind}`],
        );
    const mapUrl =
        stop.latitude || stop.longitude
            ? `geo:${stop.latitude},${stop.longitude}?q=${stop.latitude},${stop.longitude}`
            : stop.address
              ? `geo:0,0?q=${encodeURIComponent(stop.address)}`
              : null;
    return [
        header(stop.partner || stop.name, `${stop.name} · ${status.label}`, true),
        stop.address
            ? h(
                  "p",
                  { class: "sft-address" },
                  stop.address,
                  mapUrl
                      ? h("a", { href: mapUrl, class: "sft-link" }, ` ${T.open_map}`)
                      : null,
              )
            : null,
        state.form ? null : scanBox(),
        h(
            "table",
            { class: "sft-lines" },
            h(
                "thead",
                {},
                h(
                    "tr",
                    {},
                    h("th", {}, T.product),
                    h("th", {}, T.lot),
                    h("th", {}, T.quantity),
                    h("th", {}, T.checked),
                ),
            ),
            h(
                "tbody",
                {},
                lines.length ? lines : h("tr", {}, h("td", { colspan: 4 }, T.no_lines)),
            ),
        ),
        state.form ? actionForm(state.form, stop) : null,
        !state.form && open
            ? h(
                  "div",
                  { class: "sft-actions" },
                  action("deliver", "sft-btn-success"),
                  action("partial", "sft-btn-primary"),
                  action("not_delivered", "sft-btn-danger"),
                  action("incident", "sft-btn-warning"),
              )
            : null,
        !state.form && !open
            ? h(
                  "div",
                  { class: "sft-actions" },
                  h(
                      "p",
                      { class: "sft-muted" },
                      fmt(T.stop_closed, { status: status.label }),
                  ),
                  action("incident", "sft-btn-warning"),
              )
            : null,
        history.length
            ? [h("h2", {}, T.history), h("ul", { class: "sft-history" }, history)]
            : null,
    ];
}

function render() {
    const screens = { trips: renderTrips, trip: renderTrip, stop: renderStop };
    const message = document.getElementById("sft-message");
    app.replaceChildren(
        h("div", { id: "sft-sync" }),
        message || h("div", { id: "sft-message", class: "sft-message", hidden: true }),
        h("main", { class: "sft-main" }, screens[state.screen]()),
    );
    updateSyncBar();
    const scan = document.getElementById("sft-scan");
    if (scan && !state.form) {
        scan.focus({ preventScroll: true });
    }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function start() {
    if ("serviceWorker" in navigator && boot.service_worker) {
        navigator.serviceWorker
            .register(boot.service_worker, { scope: boot.scope })
            .catch(() => {});
    }
    state.deviceUuid = await db.getMeta("device_uuid");
    if (!state.deviceUuid) {
        state.deviceUuid = crypto.randomUUID();
        await db.setMeta("device_uuid", state.deviceUuid);
    }
    state.lastSync = await db.getMeta("last_sync");
    watchLocation();
    window.addEventListener("online", () => {
        state.online = true;
        updateSyncBar();
        sync();
    });
    window.addEventListener("offline", () => {
        state.online = false;
        updateSyncBar();
    });
    // Ask Chrome not to evict what is not sent yet when the phone runs low on space.
    if (navigator.storage && navigator.storage.persist) {
        navigator.storage.persist().catch(() => {});
    }
    setInterval(sync, SYNC_INTERVAL);
    // What the phone holds shows at once; the server's list follows with signal.
    await loadEvents();
    await loadTrips();
    render();
    const preselected = Number(new URLSearchParams(location.search).get("trip"));
    if (preselected) {
        await openTrip(preselected);
    }
    // The list with signal also downloads every trip, not only the one opened.
    loadTrips(true).then(() => state.screen === "trips" && render());
    sync();
}

start();
