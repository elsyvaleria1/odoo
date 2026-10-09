import { describe, expect, test } from "@odoo/hoot";
import { tick, waitUntil } from "@odoo/hoot-dom";
import { advanceTime, Deferred } from "@odoo/hoot-mock";
import { isQueued } from "@point_of_sale/app/services/data_service";
import { UNSYNC_QUEUE_STORE } from "@point_of_sale/app/utils/offline_queue";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { ConnectionLostError, RPCError } from "@web/core/network";

import { definePosModels } from "../data/generate_model_definitions.js";
import { getFilledOrder, setupPosEnv } from "../utils.js";

definePosModels();

describe("data_service", () => {
    test("localDeleteCascade", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);

        expect(store.models["pos.order"].length).toBe(1);
        expect(store.models["pos.order.line"].length).toBe(2);
        data.localDeleteCascade(order);
        expect(store.models["pos.order"].length).toBe(0);
        expect(store.models["pos.order.line"].length).toBe(0);
    });

    test("missingRecursive keeps its input when offline", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.offline = true;

        const rows = {
            "pos.order": [{ id: "aaa-uuid", uuid: "aaa-uuid", lines: [] }],
            "pos.order.line": [{ id: "bbb-uuid", uuid: "bbb-uuid" }],
        };
        const result = await data.missingRecursive(rows);
        expect(result["pos.order"]).toHaveLength(1);
        expect(result["pos.order.line"]).toHaveLength(1);
        expect(result["pos.order"][0].uuid).toBe("aaa-uuid");
    });

    test("loadConnectedData tolerates an undefined model payload", async () => {
        const store = await setupPosEnv();
        const results = store.models.loadConnectedData(
            { "pos.order.line": undefined },
            [],
        );
        expect(results["pos.order.line"] ?? []).toHaveLength(0);
    });

    test("a client-side fault keeps the queued entry, bounded by MAX_SYNC_ATTEMPTS", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        data.network.deadSyncData = [];

        let calls = 0;
        data.execute = async () => {
            calls++;
            throw new TypeError("client-side fault");
        };
        data.network.unsyncData.push({
            args: [{ type: "write", model: "pos.order", ids: [1], values: {} }],
            date: "2025-01-01 00:00:00",
            try: 1,
            uuid: "fault-1",
        });

        for (let i = 0; i < 10; i++) {
            await data.syncData().catch(() => {});
            if (!data.network.unsyncData.length) {
                break;
            }
        }

        expect(data.network.unsyncData).toHaveLength(0);
        expect(data.network.deadSyncData).toHaveLength(1);
        expect(calls).toBe(5);
    });

    test("a server rejection dead-letters immediately", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        data.network.deadSyncData = [];

        let calls = 0;
        data.execute = async () => {
            calls++;
            throw new RPCError("server said no");
        };
        data.network.unsyncData.push({
            args: [{ type: "write", model: "pos.order", ids: [1], values: {} }],
            date: "2025-01-01 00:00:00",
            try: 1,
            uuid: "rejected-1",
        });

        await data.syncData().catch(() => {});

        expect(calls).toBe(1);
        expect(data.network.unsyncData).toHaveLength(0);
        expect(data.network.deadSyncData).toHaveLength(1);
    });

    test("an operation queued offline resolves to its queue entry and carries its uuid on every attempt", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        const sent = [];
        patchWithCleanup(data.orm, {
            create: async (_model, _values, kwargs) => {
                sent.push(kwargs?.context?.pos_operation_uuid);
                throw new ConnectionLostError();
            },
        });

        const result = await data.create("pos.category", [{ name: "Offline" }]);

        expect(isQueued(result)).toBe(true);
        expect(data.network.unsyncData.map((entry) => entry.uuid)).toEqual([
            result.uuid,
        ]);
        expect(sent).toEqual([result.uuid]);

        patchWithCleanup(data.orm, {
            create: async (_model, _values, kwargs) => {
                sent.push(kwargs?.context?.pos_operation_uuid);
                return [4242];
            },
        });
        await data.syncData();

        expect(sent).toEqual([result.uuid, result.uuid]);
        expect(data.network.unsyncData).toHaveLength(0);
        expect(store.models["pos.category"].get(4242).name).toBe("Offline");
    });

    test("a read is never queued, even when asked to", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        data.network.offline = true;

        let error;
        try {
            await data.searchRead("pos.category", [], [], {}, true);
        } catch (e) {
            error = e;
        }

        expect(error).toBeInstanceOf(ConnectionLostError);
        expect(data.network.unsyncData).toHaveLength(0);
    });

    test("a replayed create whose missing product cannot be fetched still completes", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        data.network.deadSyncData = [];
        data.network.unsyncData.push({
            args: [
                {
                    type: "create",
                    model: "product.combo.item",
                    values: [{ product_id: 99999, combo_id: 1, extra_price: 0 }],
                    queue: true,
                },
            ],
            date: "2025-01-01 00:00:00",
            try: 1,
            uuid: "replay-1",
        });
        const called = [];
        patchWithCleanup(data.orm, {
            create: async () => [4243],
            call: async (model, method) => {
                called.push(`${model}.${method}`);
                throw new ConnectionLostError();
            },
        });

        let settled = false;
        const replay = data.syncData().finally(() => {
            settled = true;
        });
        for (let i = 0; i < 20 && !settled; i++) {
            await tick();
        }

        expect(settled).toBe(true);
        await replay;
        expect(called).toEqual(["product.template.load_product_from_pos"]);
        expect(data.network.unsyncData).toHaveLength(0);
        expect(store.models["product.combo.item"].get(4243)).not.toBe(undefined);
    });

    test("a keystroke burst writes the edited line and its order, not every open order", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        for (let i = 0; i < 30; i++) {
            await getFilledOrder(store);
        }
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => `${model}:${row.uuid ?? row.id}`));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();
        data.debouncedSynchronizeLocalDataInIndexedDB.cancel();

        await data._synchronizeLocalDataInIndexedDB();
        const fullSync = written.length;
        written.length = 0;

        const order = store.models["pos.order"].getAll().at(-1);
        const line = order.lines[0];
        for (const qty of [1, 12, 123, 12, 1]) {
            line.setQuantity(qty);
        }
        data.debouncedSynchronizeLocalDataInIndexedDB.cancel();
        await data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(fullSync).toBe(90);
        expect(written.sort()).toEqual(
            [`pos.order:${order.uuid}`, `pos.order.line:${line.uuid}`].sort(),
        );
    });

    test("a line deleted after its edit is not written back", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => `${model}:${row.uuid}`));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();
        const [line, kept] = order.lines;
        line.setQuantity(7);
        kept.setQuantity(8);
        line.delete();
        data.debouncedSynchronizeLocalDataInIndexedDB.cancel();

        await data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(written).not.toInclude(`pos.order.line:${line.uuid}`);
        expect(written).toInclude(`pos.order.line:${kept.uuid}`);
    });

    test("a delete waits for the write in flight instead of being overwritten by it", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const line = order.lines[0];
        const operations = [];
        const writing = new Deferred();
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                if (model === "pos.order.line") {
                    await writing;
                    operations.push(...rows.map((row) => `create:${row.uuid}`));
                }
                return rows.map(() => ({ status: "fulfilled" }));
            },
            delete: async (model, keys) => {
                operations.push(...keys.map((key) => `delete:${key}`));
            },
        });

        const sync = data.indexedDBMutex.exec(() =>
            data._synchronizeLocalDataInIndexedDB(),
        );
        await tick();
        const deletion = data.deleteRecordsInIndexedDB("pos.order.line", [line.uuid]);
        await tick();
        writing.resolve();
        await Promise.all([sync, deletion]);

        expect(operations.filter((op) => op.endsWith(line.uuid))).toEqual([
            `create:${line.uuid}`,
            `delete:${line.uuid}`,
        ]);
    });

    test("a uiState change alone writes its order", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => `${model}:${row.uuid}`));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();

        order.setScreenData({ name: "PaymentScreen" });
        await tick();
        data.debouncedSynchronizeLocalDataInIndexedDB.cancel();
        await data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(written).toEqual([`pos.order:${order.uuid}`]);
    });

    test("a nested uiState change writes its order once per change", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => JSON.parse(row.JSONuiState)));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();
        const flush = async () => {
            await tick();
            data.debouncedSynchronizeLocalDataInIndexedDB.cancel();
            await data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });
        };

        order.uiState.TipScreen.inputTipAmount = "5";
        await flush();
        await flush();
        order.uiState.selected_orderline_uuid = order.lines[0].uuid;
        await flush();

        expect(written.map((state) => state.TipScreen.inputTipAmount)).toEqual([
            "5",
            "5",
        ]);
        expect(written[1].selected_orderline_uuid).toBe(order.lines[0].uuid);
    });

    test("a finalized synced order of a past session is purged at boot, not re-read", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const sessionId = parseInt(odoo.pos_session_id);
        const restoredOrder = (uuid, id, state, session_id) => ({
            id,
            uuid,
            state,
            session_id,
            config_id: 1,
            lines: [],
            payment_ids: [],
        });
        const results = store.models.loadConnectedData(
            {
                "pos.order": [
                    restoredOrder("old-paid", 7001, "paid", sessionId + 100),
                    restoredOrder("old-draft", 7002, "draft", sessionId + 100),
                    restoredOrder("current-paid", 7003, "paid", sessionId),
                    restoredOrder(
                        "unsynced-paid",
                        "unsynced-paid",
                        "paid",
                        sessionId + 100,
                    ),
                ],
            },
            [],
        );
        const deleted = [];
        const reread = [];
        patchWithCleanup(data, {
            async deleteRecordsInIndexedDB(model, keys) {
                deleted.push(...keys.map((key) => `${model}:${key}`));
            },
        });
        patchWithCleanup(data.orm, {
            async call(model, method, args) {
                if (method !== "read_pos_orders") {
                    return super.call(...arguments);
                }
                reread.push(...args[0][0][2]);
                return { "pos.order": [] };
            },
        });

        data.purgeRestoredOrders(results);
        await data.checkAndDeleteMissingOrders(results);

        expect(deleted).toInclude("pos.order:old-paid");
        expect(reread.sort()).toEqual([7002, 7003]);
        expect(store.models["pos.order"].getBy("uuid", "old-paid")).toBe(undefined);
        expect(store.models["pos.order"].getBy("uuid", "unsynced-paid")).not.toBe(
            undefined,
        );
    });

    test("a past-session order a pending refund points at stays, in memory and in IndexedDB", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const sessionId = parseInt(odoo.pos_session_id);
        const product = store.models["product.product"].getFirst();
        const results = store.models.loadConnectedData(
            {
                "pos.order": [
                    {
                        id: 7001,
                        uuid: "refunded",
                        state: "paid",
                        session_id: sessionId + 100,
                        config_id: 1,
                        lines: [8001],
                        payment_ids: [],
                    },
                    {
                        id: "refund",
                        uuid: "refund",
                        state: "draft",
                        session_id: sessionId + 100,
                        config_id: 1,
                        lines: ["refund-line"],
                        payment_ids: [],
                    },
                ],
                "pos.order.line": [
                    {
                        id: 8001,
                        uuid: "refunded-line",
                        order_id: 7001,
                        product_id: product.id,
                        qty: 2,
                        price_unit: 10,
                        refund_orderline_ids: ["refund-line"],
                    },
                    {
                        id: "refund-line",
                        uuid: "refund-line",
                        order_id: "refund",
                        product_id: product.id,
                        qty: -1,
                        price_unit: 10,
                        refunded_orderline_id: 8001,
                    },
                ],
            },
            [],
        );
        const removed = [];
        const recordRemoval = async (model, keys) => {
            removed.push(...keys.map((key) => `${model}:${key}`));
        };
        patchWithCleanup(data, { deleteRecordsInIndexedDB: recordRemoval });
        patchWithCleanup(data.indexedDB, {
            create: async (_model, rows) => rows.map(() => ({ status: "fulfilled" })),
            delete: recordRemoval,
        });

        data.purgeRestoredOrders(results);
        await data._synchronizeLocalDataInIndexedDB();

        const refundLine = store.models["pos.order.line"].getBy("uuid", "refund-line");
        expect(refundLine.refunded_orderline_id?.id).toBe(8001);
        expect(refundLine.serializeForORM().refunded_orderline_id).toBe(8001);
        expect(removed).not.toInclude("pos.order:refunded");
        expect(removed).not.toInclude("pos.order.line:refunded-line");
    });

    test("a past-session paid order with an unsynced edit is not purged at boot", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const results = store.models.loadConnectedData(
            {
                "pos.order": [
                    {
                        id: 7009,
                        uuid: "edited",
                        state: "paid",
                        session_id: parseInt(odoo.pos_session_id) + 100,
                        config_id: 1,
                        lines: [],
                        payment_ids: [],
                        __dirty: true,
                    },
                ],
            },
            [],
        );
        patchWithCleanup(data, { async deleteRecordsInIndexedDB() {} });

        data.purgeRestoredOrders(results);

        const order = store.models["pos.order"].getBy("uuid", "edited");
        expect(order?.isDirty()).toBe(true);
        expect(results["pos.order"]).toInclude(order);
    });

    const cashMoveEntry = (uuid) => ({
        args: [
            {
                type: "call",
                model: "pos.session",
                method: "try_cash_in_out",
                args: [
                    [1],
                    "in",
                    9,
                    "float",
                    1,
                    { translatedType: "in", formattedAmount: "$ 9.00" },
                ],
                kwargs: {},
            },
        ],
        date: "2025-01-01 00:00:00",
        try: 1,
        uuid,
    });

    test("an operation that fails while online is retried with a growing delay until it is sent", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [];
        data.network.offline = false;
        const attempts = [];
        let failures = 2;
        patchWithCleanup(data.orm, {
            call: async (_model, method) => {
                attempts.push(method);
                if (failures-- > 0) {
                    throw new ConnectionLostError();
                }
                return true;
            },
        });
        const settle = async () => {
            await data.mutex.getUnlockedDef();
            await tick();
        };

        const result = await data.call(
            "pos.session",
            "try_cash_in_out",
            cashMoveEntry("x").args[0].args,
            {},
            true,
        );
        expect(isQueued(result)).toBe(true);
        expect(attempts).toHaveLength(1);

        await advanceTime(1900);
        await settle();
        expect(attempts).toHaveLength(1);
        await advanceTime(100);
        await waitUntil(() => attempts.length === 2 && !data.mutex.locked);
        expect(data.network.unsyncData).toHaveLength(1);

        await advanceTime(3900);
        await settle();
        expect(attempts).toHaveLength(2);
        await advanceTime(100);
        await waitUntil(() => attempts.length === 3 && !data.network.unsyncData.length);

        await advanceTime(120000);
        await settle();
        expect(attempts).toHaveLength(3);
    });

    test("an operation the server refuses on replay is shown to the cashier", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        data.network.unsyncData = [cashMoveEntry("refused-1")];
        data.network.deadSyncData = [];
        const shown = [];
        patchWithCleanup(data.dialog, {
            add: (_component, props) => shown.push(props),
        });
        data.execute = async () => {
            const error = new RPCError("Session closed");
            error.data = { message: "This session is closed." };
            throw error;
        };

        await data.syncData();

        expect(data.network.deadSyncData).toHaveLength(1);
        expect(shown).toHaveLength(1);
        expect(shown[0].body).toInclude("Cash in of $ 9.00 (float)");
        expect(shown[0].body).toInclude("This session is closed.");
    });

    test("every pending local write is issued in the task that asks for it", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => `${model}:${row.uuid}`));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.markLocalRecordsDirty(
            "pos.order.line",
            order.lines.map((line) => line.id),
        );

        const writing = data._synchronizeLocalDataInIndexedDB({ onlyDirty: true });

        expect(written.sort()).toEqual(
            [
                `pos.order:${order.uuid}`,
                ...order.lines.map((line) => `pos.order.line:${line.uuid}`),
            ].sort(),
        );
        await writing;
    });

    test("a change still waiting for the debounce is written at once when the page hides", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const order = await getFilledOrder(store);
        const line = order.lines[0];
        const written = [];
        patchWithCleanup(data.indexedDB, {
            create: async (model, rows) => {
                written.push(...rows.map((row) => `${model}:${row.uuid}`));
                return rows.map(() => ({ status: "fulfilled" }));
            },
        });
        data.listenToLocalChanges();
        line.setQuantity(7);
        expect(written).toEqual([]);

        const flushing = data.flushLocalDataInIndexedDB();

        expect(written).toInclude(`pos.order.line:${line.uuid}`);
        await flushing;
        const count = written.length;
        await advanceTime(1000);
        expect(written).toHaveLength(count);
    });

    test("a boot without the server keeps the synced orders it cannot check", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        const results = store.models.loadConnectedData(
            {
                "pos.order": [
                    {
                        id: 7010,
                        uuid: "synced-draft",
                        state: "draft",
                        session_id: parseInt(odoo.pos_session_id),
                        config_id: 1,
                        lines: [],
                        payment_ids: [],
                    },
                ],
            },
            [],
        );
        data.network.offline = true;

        await data.checkAndDeleteMissingOrders(results);

        expect(store.models["pos.order"].getBy("uuid", "synced-draft")).not.toBe(
            undefined,
        );
    });

    test("Reload Data clears only the server cache, after writing the latest local changes", async () => {
        const store = await setupPosEnv();
        const data = store.data;
        let cleared;
        patchWithCleanup(data, {
            syncLocalDataInIndexedDB: async () => expect.step("flushed"),
        });
        patchWithCleanup(data.indexedDB, {
            dbStores: [
                ["uuid", "pos.order"],
                ["uuid", "pos.order.line"],
                ["uuid", "pos.payment"],
                ["id", "product.product"],
                ["uuid", UNSYNC_QUEUE_STORE],
            ],
            clear: async (stores) => {
                expect.step("cleared");
                cleared = stores;
                return true;
            },
            close: () => expect.step("closed"),
        });

        await data.resetServerCacheForReload();

        expect(cleared).toEqual(["product.product"]);
        expect.verifySteps(["flushed", "cleared", "closed"]);
    });
});
