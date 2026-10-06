/**
 * Regression tests for defects found in the audits of this module.
 *
 * Each one drives the real code path (not a local copy of the expression) and asserts the
 * corrected behaviour, so re-introducing the defect fails here rather than in a browser tour.
 */
import { describe, expect, test } from "@odoo/hoot";
import { BackorderDialog } from "@stock_barcode/components/backorder_dialog";
import LineComponent from "@stock_barcode/components/line";
import MainComponent from "@stock_barcode/components/main";
import LazyBarcodeCache from "@stock_barcode/lazy_barcode_cache";
import BarcodeModel from "@stock_barcode/models/barcode_model";
import BarcodePickingModel from "@stock_barcode/models/barcode_picking_model";
import BarcodeQuantModel from "@stock_barcode/models/barcode_quant_model";
import { Digipad } from "@stock_barcode/widgets/digipad";
import { StockBarcodeQuantOne2ManyField } from "@stock_barcode/widgets/set_quant_stock_move_line";
import { Mutex } from "@web/core/utils/concurrency";

describe.current.tags("headless");

function makeCache(records = {}) {
    const cache = new LazyBarcodeCache({
        "barcode.nomenclature": [{ id: 1, is_gs1_nomenclature: false, rule_ids: [] }],
        ...records,
    });
    // No server in a unit test: a cache miss must not attempt an RPC.
    cache._getMissingRecord = async () => false;
    return cache;
}

// --- getQuants: the lot lookup keeps its product filter ---------------------
test("getQuants resolves a lot name within the scanned product", async () => {
    const cache = makeCache({
        "product.trace": [
            { id: 11, name: "L1", product_id: 100 },
            { id: 12, name: "L1", product_id: 200 },
        ],
        "stock.quant": [
            {
                id: 1,
                product_id: 200,
                location_id: 5,
                quantity: 3,
                trace_id: 12,
                owner_id: false,
            },
        ],
        "product.product": [{ id: 200, barcode: "P200", uom_id: 1 }],
    });
    cache.productsWithAllQuants.add(200);
    const quants = await cache.getQuants({ id: 200 }, 5, { lot_name: "L1" });
    expect(quants.length).toBe(1, {
        message: "lot L1 of product 200 must be found, not product 100's homonym",
    });
    expect(quants[0].id).toBe(1);
});

// --- getQuants: owner may be given as a record or as an id -----------------
test("getQuants accepts an owner record as well as an owner id", async () => {
    const cache = makeCache({
        "stock.quant": [
            {
                id: 1,
                product_id: 100,
                location_id: 5,
                quantity: 3,
                owner_id: 42,
                trace_id: false,
            },
        ],
        "product.product": [{ id: 100, barcode: "P", uom_id: 1 }],
    });
    cache.productsWithAllQuants.add(100);
    const byId = await cache.getQuants({ id: 100 }, 5, { owner_id: 42 });
    const byRecord = await cache.getQuants({ id: 100 }, 5, {
        owner_id: { id: 42, name: "Azure" },
    });
    expect(byId.length).toBe(1);
    expect(byRecord.length).toBe(1, {
        message: "a res.partner record must resolve to its id before comparing",
    });
});

// --- getQuants: a product with no quants at all ----------------------------
test("getQuants tolerates a product with no quants", async () => {
    // The product's quants are known (fetched, and there are none): the empty branch runs
    // without an RPC.
    const cache = makeCache({
        "product.product": [{ id: 100, barcode: "P", uom_id: 1 }],
        "stock.quant": [],
    });
    cache.productsWithAllQuants.add(100);
    expect((await cache.getQuants({ id: 100 }, 5)).length).toBe(0);
    // …and the per-location entry it creates is a map, keyed by location id, like every other
    // write to this cache — it used to be an array here and an object everywhere else.
    expect(Array.isArray(cache.dbQuantCache[100])).toBe(false);
    expect((await cache.getQuants({ id: 100 }, 5)).length).toBe(0);
});

// --- GS1: an unknown location must not blow up the scan handler ------------
test("an unknown GS1 location yields a result object, not undefined", async () => {
    const cache = makeCache({ "stock.location": [] });
    const ctx = { cache, groups: {}, useExistingLots: true, notification: () => {} };
    const data = { type: "location", value: "NOPE", rule: { type: "location" } };
    const base = await BarcodeModel.prototype._processGs1Data.call(ctx, data);
    expect(base).toEqual(
        {},
        { message: "no location found -> empty result, no match" },
    );

    // And the picking override, which reads `result.location` straight away, survives it.
    const pickingCtx = {
        cache,
        groups: {},
        useExistingLots: true,
        notification: () => {},
    };
    let error = null;
    try {
        await BarcodePickingModel.prototype._processGs1Data.call(pickingCtx, data);
    } catch (e) {
        error = e;
    }
    expect(error).toBe(null, { message: `override threw: ${error}` });
});

// --- line sorting: a consistent comparator ---------------------------------
test("_sortLine keeps the input order of lines sharing a sortIndex", async () => {
    const lines = [
        { sortIndex: 2, tag: "c" },
        { sortIndex: 1, tag: "a" },
        { sortIndex: 1, tag: "b" },
    ];
    const sorted = BarcodeModel.prototype._sortLine.call({}, lines);
    expect(sorted.map((l) => l.tag).join("")).toBe("abc", {
        message: "equal indices must compare equal, so the sort stays stable",
    });
});

// --- scan pipeline: cleanup runs after the barcodes it follows -------------
test("processBarcode finishes the scan before tearing down its own state", async () => {
    const order = [];
    const ctx = {
        splitBarcode: () => ["AAA", "BBB"],
        uriInCache: () => false,
        actionMutex: new Mutex(),
        trigger: (name) => order.push(`trigger:${name}`),
        _getMissingRecords: async () => {},
        _processBarcode: async () => {
            order.push("processed");
        },
        _processBarcodes: BarcodeModel.prototype._processBarcodes,
        postProcessBarcode: BarcodeModel.prototype.postProcessBarcode,
        notificationCache: new Set(),
    };
    await BarcodeModel.prototype.processBarcode.call(ctx, "AAA,BBB");
    expect(order.filter((e) => e === "processed").length).toBe(2, {
        message: `both barcodes processed, got ${JSON.stringify(order)}`,
    });
    const lastProcessed = order.lastIndexOf("processed");
    const cleared = order.indexOf("trigger:clearBarcodesCountProcessed");
    expect(cleared > lastProcessed).toBe(true, {
        message: `cleanup must come last, got ${JSON.stringify(order)}`,
    });
});

test("processBarcode tears down its state when processing throws", async () => {
    const triggered = [];
    const ctx = {
        splitBarcode: () => ["AAA", "BBB"],
        uriInCache: () => false,
        actionMutex: new Mutex(),
        trigger: (name) => triggered.push(name),
        _getMissingRecords: async () => {},
        _processBarcode: async () => {
            throw new Error("not in the cache");
        },
        _processBarcodes: BarcodeModel.prototype._processBarcodes,
        postProcessBarcode: BarcodeModel.prototype.postProcessBarcode,
        notificationCache: new Set(["stale"]),
    };
    await expect(
        BarcodeModel.prototype.processBarcode.call(ctx, "AAA,BBB"),
    ).rejects.toThrow("not in the cache");
    expect(ctx._currentBarcode).toBe(undefined, {
        message: "a failed scan must not block re-scanning the same barcodes",
    });
    expect(ctx.notificationCache.size).toBe(0);
    expect(triggered.includes("clearBarcodesCountProcessed")).toBe(true);
});

// --- the quantity mutex holds until the update settles ---------------------
test("updateLineQty holds the mutex until updateLine settles", async () => {
    let resolveUpdate;
    const updateDone = new Promise((r) => (resolveUpdate = r));
    const order = [];
    const ctx = {
        actionMutex: new Mutex(),
        pageLines: [{ virtual_id: 1 }],
        trigger: () => {},
        updateLine: async () => {
            await updateDone;
            order.push("update");
        },
    };
    const done = BarcodePickingModel.prototype.updateLineQty.call(ctx, 1, 1);
    const next = ctx.actionMutex.exec(() => order.push("next"));
    for (let tick = 0; tick < 10; tick++) {
        await Promise.resolve();
    }
    expect(order).toEqual([], {
        message: "the mutex must not release while updateLine is still pending",
    });
    resolveUpdate();
    await Promise.all([done, next]);
    expect(order).toEqual(["update", "next"]);
});

// --- location paths survive names with regex metacharacters ---------------
test("the location path strip handles names with regex metacharacters", async () => {
    const ctx = { model: { shouldShortenLocationName: false } };
    const strip = (name) =>
        LineComponent.prototype._getLocationPath.call(
            ctx,
            { display_name: "", name: "" },
            {
                display_name: `WH/Stock/${name}`,
                name,
            },
        );
    expect(strip("Shelf A")).toBe("WH/Stock/");
    expect(strip("Zone (A)")).toBe("WH/Stock/", {
        message: "parentheses are not a group here",
    });
    expect(strip("Zone (")).toBe("WH/Stock/", {
        message: "an unbalanced paren must not throw",
    });
});

// --- a barcode that missed once must be retried after a refresh ------------
test("refreshing the cache forgets earlier barcode misses", async () => {
    const cache = makeCache({ "product.trace": [] });
    let lookups = 0;
    cache._getMissingRecord = async function (barcode, model, filters = {}) {
        lookups++;
        this.missingBarcodeKeyCache.add(JSON.stringify([barcode, model, filters]));
    };
    await cache.getRecordByBarcode("LATER", "product.trace");
    await cache.getRecordByBarcode("LATER", "product.trace");
    const beforeRefresh = lookups;
    cache.forgetMissingBarcodes();
    expect(cache.missingBarcodeKeyCache.size).toBe(0, {
        message: "a record created after page load must become findable again",
    });
    await cache.getRecordByBarcode("LATER", "product.trace");
    expect(lookups).toBe(beforeRefresh + 1);
});

// --- 2026-09-28 audit -------------------------------------------------------
test("a refused destination leaves an earlier accepted one in place", async () => {
    const accepted = { id: 1 };
    const refused = { id: 2 };
    const ctx = {
        config: { restrict_scan_dest_location: "mandatory" },
        _useReservation: true,
        _isSublocation: () => false,
        _defaultDestLocation: () => ({ id: 99 }),
        notification: () => {},
        lastScanned: { destLocation: accepted },
    };
    const process = BarcodePickingModel.prototype._processLocationDestination;
    await process.call(ctx, { destLocation: refused });
    expect(ctx.lastScanned.destLocation).toBe(accepted, {
        message: "a wrong scan must not erase the destination scanned before it",
    });
    // `_checkBarcode` records the first destination before it is checked.
    ctx.lastScanned.destLocation = refused;
    await process.call(ctx, { destLocation: refused });
    expect(ctx.lastScanned.destLocation).toBe(false, {
        message:
            "a refused destination must not satisfy the mandatory-destination guard",
    });
});

test("source confirmation survives the very first scan", async () => {
    const ctx = {
        config: { restrict_scan_source_location: true },
        groups: { group_stock_multi_locations: true },
        lastScanned: {},
        location: { id: 5 },
        needSourceConfirmation: {},
        scanHistory: [{ location: { id: 5 } }],
        getQtyDone: () => 1,
        lineIsReserved: () => true,
        lineIsInTheCurrentLocation: () => true,
    };
    const line = { location_id: { id: 6 }, product_id: { id: 100 } };
    const canTake =
        BarcodePickingModel.prototype.lineCanBeTakenFromTheCurrentLocation.call(
            ctx,
            line,
        );
    expect(canTake).toBe(false);
    expect(ctx.needSourceConfirmation[5][100]).toBe(true);
});

test("pack-in-pack keeps the parameters of the scanned package", async () => {
    const calls = [];
    const params = { package_name: "PACK-X" };
    const ctx = {
        selectedLine: { result_package_id: { id: 3 } },
        getPackageToPackIds: () => [3],
        _putPackInPack: async (...args) => calls.push(args),
    };
    await BarcodePickingModel.prototype._putInPack.call(ctx, params);
    expect(calls.length).toBe(1);
    expect(calls[0][1]).toBe(params);
});

test("displayBarcodeLines leaves the lines alone when the deleted one is not shown", async () => {
    const lines = [{ id: 1 }, { id: 2 }];
    const ctx = {
        lineModel: "stock.move.line",
        orm: { search: async () => [] },
        currentState: { lines },
    };
    await BarcodeModel.prototype.displayBarcodeLines.call(ctx, 42);
    expect(lines.map((l) => l.id)).toEqual([1, 2]);
});

test("RFID reads arriving while a batch is processed start the next batch", async () => {
    const processed = [];
    const ctx = {
        actionMutex: new Mutex(),
        bufferedBarcodes: ["urn:A"],
        bufferingTimeout: 1,
        model: {
            processBarcode: async (barcodes) => {
                processed.push(barcodes);
                // What `onMobileReaderScanned` does when the reader sends more tags.
                ctx.bufferedBarcodes = ctx.bufferedBarcodes.concat(["urn:B"]);
            },
        },
    };
    await MainComponent.prototype._onMobileReaderScanned.call(ctx);
    expect(processed).toEqual(["urn:A"]);
    expect(ctx.bufferedBarcodes).toEqual(["urn:B"], {
        message: "a read received during processing must not be wiped with the batch",
    });
});

test("an unreserved subline is not counted twice by the backorder check", async () => {
    const product = { id: 100, tracking: "lot" };
    const reserved = {
        virtual_id: 1,
        product_id: product,
        move_id: 1,
        reserved_uom_qty: 10,
        qty_done: 4,
    };
    const extra = {
        virtual_id: 2,
        product_id: product,
        move_id: 1,
        reserved_uom_qty: 0,
        qty_done: 3,
    };
    // `_groupSublines` gives the parent the sublines' totals.
    const grouped = {
        ...reserved,
        virtual_id: "g",
        lines: [reserved, extra],
        qty_done: 7,
    };
    const dialogs = [];
    const ctx = {
        precision: 2,
        _compareQuantities: BarcodePickingModel.prototype._compareQuantities,
        config: { create_backorder: "ask" },
        lastScanned: {},
        currentState: { lines: [reserved, extra] },
        _setUser: async () => {},
        _getParentLine: () => grouped,
        showBackOrderDialog: true,
        trigger: () => {},
        groups: {},
        dialogService: {
            add: (_dialog, props) => dialogs.push(props.uncompletedLines),
        },
    };
    await BarcodePickingModel.prototype._validate.call(ctx);
    expect(dialogs.length).toBe(1, {
        message: "7 of 10 done must ask about the backorder",
    });
    expect(
        dialogs[0].map((line) => [line.virtual_id, line.qty_done, line.backorderQty]),
    ).toEqual([["g", 7, 3]], {
        message: "the dialog shows the quantities the check decided on",
    });
});

test("a sound the browser refuses turns the barcode sounds off", async () => {
    const played = [];
    const ctx = {
        config: { play_sound: true },
        state: { uiBlocked: false },
        sounds: {
            play: async (name) => {
                played.push(name);
                return false;
            },
        },
    };
    await MainComponent.prototype.playSound.call(ctx, { detail: "error" });
    await MainComponent.prototype.playSound.call(ctx, { detail: "error" });
    expect(played).toEqual(["error"]);
    expect(ctx.config.play_sound).toBe(false);
});

test("scanned fractions compare equal to the reservation they add up to", async () => {
    const ctx = {
        precision: 2,
        _compareQuantities: BarcodePickingModel.prototype._compareQuantities,
    };
    const line = { qty_done: 0.7 + 0.1, reserved_uom_qty: 0.8 };
    expect(BarcodePickingModel.prototype._lineIsComplete.call(ctx, line)).toBe(true, {
        message: `qty_done=${line.qty_done} is complete at 2 decimals`,
    });
});

test("un-completing a package resets every subline, not below zero", async () => {
    const done = { virtual_id: 1, qty_done: 5, reserved_uom_qty: 5, product_id: {} };
    const untouched = {
        virtual_id: 2,
        qty_done: 0,
        reserved_uom_qty: 5,
        product_id: {},
    };
    // A package line is a copy of its first subline, here the untouched one.
    const packageLine = { ...untouched, virtual_id: "p", lines: [untouched, done] };
    const ctx = {
        actionMutex: new Mutex(),
        packageLines: [packageLine],
        record: {},
        trigger: () => {},
        _setUser: () => {},
        _markLineAsDirty: () => {},
        _updateLineQty: BarcodePickingModel.prototype._updateLineQty,
    };
    await BarcodePickingModel.prototype.completePackage.call(ctx, "p");
    expect([untouched.qty_done, done.qty_done]).toEqual([0, 0]);
    await BarcodePickingModel.prototype.completePackage.call(ctx, "p");
    expect([untouched.qty_done, done.qty_done]).toEqual([5, 5]);
});

test("saves run one after the other", async () => {
    const events = [];
    let release;
    const ctx = {
        async _save() {
            events.push("start");
            await new Promise((resolve) => (release = resolve));
            events.push("end");
        },
    };
    const first = BarcodeModel.prototype.save.call(ctx);
    const second = BarcodeModel.prototype.save.call(ctx);
    await Promise.resolve();
    expect(events).toEqual(["start"], {
        message: "the second save waits for the first",
    });
    release();
    await first;
    for (let tick = 0; events.length < 3 && tick < 20; tick++) {
        await Promise.resolve();
    }
    expect(events).toEqual(["start", "end", "start"]);
    release();
    await second;
    expect(events).toEqual(["start", "end", "start", "end"]);
});

test("a notification can show again once it is closed", async () => {
    const shown = [];
    const ctx = {
        notificationCache: new Set(),
        trigger: () => {},
        notificationService: {
            add: (message, options) => shown.push({ message, close: options.onClose }),
        },
    };
    const notify = (msg) => BarcodeModel.prototype.notification.call(ctx, msg);
    notify("Nothing to apply");
    notify("Nothing to apply");
    expect(shown.length).toBe(1, { message: "not twice while it is displayed" });
    shown[0].close();
    notify("Nothing to apply");
    expect(shown.length).toBe(2, {
        message: "a closed notification must not stay muted",
    });
});

test("a cached barcode failing the filter is looked up with the filter", async () => {
    const cache = makeCache({
        "product.trace": [{ id: 11, name: "L1", product_id: 100 }],
    });
    const lookups = [];
    cache._getMissingRecord = async function (barcode, model, filters) {
        lookups.push(filters);
        this.setCache({ "product.trace": [{ id: 12, name: "L1", product_id: 200 }] });
    };
    const lot = await cache.getRecordByBarcode("L1", "product.trace", {
        filters: { "product.trace": { product_id: 200 } },
    });
    expect(lookups.length).toBe(1);
    expect(lot?.id).toBe(12, { message: "product 200's L1, not undefined" });
});

test("a lot name joining an existing quant gives the line records, not ids", async () => {
    const cache = makeCache({
        "product.product": [{ id: 100, barcode: "P", uom_id: 1 }],
        "uom.uom": [{ id: 1, name: "Units" }],
        "stock.location": [{ id: 5, barcode: "L5", name: "Shelf" }],
        "product.trace": [{ id: 12, name: "L1", product_id: 100 }],
        "stock.quant": [
            {
                id: 7,
                product_id: 100,
                product_uom_id: 1,
                location_id: 5,
                trace_id: 12,
                package_id: false,
                owner_id: false,
                quantity: 4,
                dummy_id: "",
            },
        ],
    });
    cache.productsWithAllQuants.add(100);
    const line = {
        virtual_id: 99,
        product_id: cache.getRecord("product.product", 100),
        location_id: cache.getRecord("stock.location", 5),
        trace_id: false,
        lot_name: false,
    };
    const ctx = {
        cache,
        _quantToLine: BarcodeQuantModel.prototype._quantToLine,
        _nextVirtualId: () => 1000,
    };
    await BarcodeQuantModel.prototype._updateLotName.call(ctx, line, "L1");
    expect(line.id).toBe(7);
    expect(line.virtual_id).toBe(99, { message: "the line keeps its identity" });
    expect(line.product_id.id).toBe(100, { message: "a record, not the raw id" });
    expect(line.location_id.id).toBe(5);
    expect(line.trace_id.id).toBe(12);
});

test("a count within the precision of the expected quantity is not faulty", async () => {
    const ctx = { showQuantityCount: true, precision: 2 };
    const line = {
        inventory_quantity_set: true,
        inventory_quantity: 0.1 + 0.2,
        quantity: 0.3,
    };
    expect(BarcodeQuantModel.prototype.lineIsFaulty.call(ctx, line)).toBe(false);
});

test("only the products the server names count as having all their quants", async () => {
    const cache = makeCache({});
    const records = cache.setBarcodeData({
        records: {
            "product.product": [
                { id: 1, barcode: "2300001000084" },
                // Brought along by a scanned packaging: its quants were not fetched.
                { id: 2, barcode: "5468123001239" },
            ],
        },
        products_with_all_quants: [1],
    });
    expect(records["product.product"].length).toBe(2);
    expect([...cache.productsWithAllQuants]).toEqual([1], {
        message: "the route's own list, not a guess from the searched barcodes",
    });
});

test("reading the page lines leaves the state's order alone", async () => {
    const [second, first] = [
        { virtual_id: 2, sortIndex: 2 },
        { virtual_id: 1, sortIndex: 1 },
    ];
    const ctx = {
        currentState: { lines: [second, first] },
        _moveEntirePackage: () => false,
        _sortLine: BarcodeModel.prototype._sortLine,
    };
    const pageLines = Object.getOwnPropertyDescriptor(
        BarcodePickingModel.prototype,
        "pageLines",
    ).get.call(ctx);
    expect(pageLines.map((l) => l.virtual_id)).toEqual([1, 2]);
    expect(ctx.currentState.lines.map((l) => l.virtual_id)).toEqual([2, 1], {
        message: "a getter must not reorder the state it reads",
    });
});

test("the exit quantities are sent in the move's unit", async () => {
    const calls = [];
    const ctx = {
        record: { state: "assigned" },
        moveIds: [1],
        cache: makeCache({
            "stock.move": [{ id: 1, product_uom_id: 1 }],
            "uom.uom": [
                { id: 1, name: "Units", factor: 1 },
                { id: 2, name: "Pack of 6", factor: 6 },
            ],
        }),
        initialState: {
            lines: [
                {
                    move_id: 1,
                    qty_done: 1,
                    reserved_uom_qty: 0,
                    product_uom_id: { id: 2, factor: 6 },
                },
                {
                    move_id: 1,
                    qty_done: 4,
                    reserved_uom_qty: 10,
                    product_uom_id: { id: 1, factor: 1 },
                },
            ],
        },
        orm: { call: (...args) => calls.push(args) },
        _getLineMoveId: BarcodePickingModel.prototype._getLineMoveId,
        _getLineToMoveUomFactor: BarcodePickingModel.prototype._getLineToMoveUomFactor,
    };
    BarcodePickingModel.prototype._onExit.call(ctx);
    expect(calls[0][2][1]).toEqual(
        { 1: { quantity_done: 10, reserved_uom_qty: 10 } },
        {
            message: "a pack of 6 and 4 units are 10 units, not 5",
        },
    );
});

test("a refused serial-packaging line stops the packaging's other lines", async () => {
    const results = [false, { id: 2 }, { id: 3 }];
    const ctx = { createNewLine: async () => results.shift() };
    const line = await BarcodeModel.prototype._createSerialPackagingLines.call(
        ctx,
        {},
        3,
    );
    expect(line).toBe(false);
    expect(results.length).toBe(2, {
        message:
            "no line may be created from the location the first one was refused at",
    });
});

test("the selected quant follows the line it shows, reloaded in place or not", async () => {
    const quant = (id, location, pack = false) => ({
        data: { id, location_id: { id: location }, package_id: pack && { id: pack } },
    });
    const record = {
        data: {
            location_id: { id: 1 },
            package_id: { id: 7 },
            product_stock_quant_ids: {
                records: [quant(10, 1, 7), quant(11, 1), quant(12, 2)],
            },
        },
    };
    const field = Object.create(StockBarcodeQuantOne2ManyField.prototype);
    field.props = { record };
    expect(field.selectedQuantId).toBe(10);
    Object.assign(record.data, { location_id: { id: 2 }, package_id: false });
    expect(field.selectedQuantId).toBe(12, {
        message: "a line reloaded after its save selects the quant it now names",
    });
});

test("a price-embedded barcode finds the product it was printed for", async () => {
    const ctx = {
        commands: {},
        packageTypes: [],
        groups: {},
        notification: () => {},
        parser: {
            parseBarcode: () => ({
                type: "price",
                code: "2355555009502",
                base_code: "2355555000004",
                value: 9.5,
            }),
        },
        cache: makeCache({
            "product.product": [{ id: 1, barcode: "2355555000004", uom_id: 1 }],
        }),
        _fetchRecordFromTheCache: BarcodeModel.prototype._fetchRecordFromTheCache,
    };
    const result = await BarcodeModel.prototype._parseBarcode.call(
        ctx,
        "2355555009502",
        {},
    );
    expect(result.product?.id).toBe(1, {
        message: "the product's barcode is the scanned one with the price zeroed",
    });
});

test("a second return command while the first is on its way creates no second return", async () => {
    let release;
    const calls = [];
    const ctx = {
        resModel: "stock.picking",
        resId: 7,
        orm: {
            call: async (...args) => {
                calls.push(args);
                await new Promise((resolve) => (release = resolve));
                return { type: "ir.actions.act_window" };
            },
        },
        action: { doAction: async () => {} },
    };
    const first = BarcodePickingModel.prototype._returnProducts.call(ctx);
    const second = BarcodePickingModel.prototype._returnProducts.call(ctx);
    expect(calls.length).toBe(1, {
        message: "each call creates a return picking server side",
    });
    release();
    await Promise.all([first, second]);
    const later = BarcodePickingModel.prototype._returnProducts.call(ctx);
    expect(calls.length).toBe(2, { message: "a later command is not refused" });
    release();
    await later;
});

test("a second tap on the backorder dialog's Validate does not validate twice", async () => {
    let release;
    let applied = 0;
    const ctx = {
        state: { applying: false },
        props: {
            onApply: async () => {
                applied++;
                await new Promise((resolve) => (release = resolve));
            },
            close: () => {},
        },
    };
    const first = BackorderDialog.prototype._onApply.call(ctx);
    const second = BackorderDialog.prototype._onApply.call(ctx);
    release();
    await Promise.all([first, second]);
    expect(applied).toBe(1);
});

test("the digipad's buttons follow the record's quantity", () => {
    const data = { quantity: 0 };
    const ctx = { props: { record: { data }, fieldToEdit: "quantity" } };
    const quantity = Object.getOwnPropertyDescriptor(Digipad.prototype, "quantity");
    expect(quantity?.get.call(ctx)).toBe(0);
    data.quantity = 4;
    expect(quantity?.get.call(ctx)).toBe(4, {
        message: "a quantity typed in the field enables 0 and -1",
    });
});
