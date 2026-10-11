import { Logger } from "@bus/workers/bus_worker_utils";
import { after, before, describe, expect, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-dom";

describe.current.tags("desktop");

before(() => indexedDB.deleteDatabase("test_db"));
after(() => indexedDB.deleteDatabase("test_db"));

test("J16: a new Logger opens no IndexedDB until the first log", async () => {
    indexedDB.deleteDatabase("j16_db");
    const logger = new Logger("j16_db");
    expect(logger._db).toBe(undefined);
    expect(logger._dbPromise).toBe(undefined);
    await logger.log("first");
    expect(logger._db).not.toBe(undefined);
    expect(await logger.getLogs()).toEqual(["first"]);
    logger.close();
    indexedDB.deleteDatabase("j16_db");
});

test("logs are saved and garbage-collected after TTL", async () => {
    indexedDB.deleteDatabase("test_db");
    const logger = new Logger("test_db");
    await logger.log("foo");
    await logger.log("bar");
    expect(await logger.getLogs()).toEqual(["foo", "bar"]);
    await advanceTime(Logger.LOG_TTL + 1000);
    expect(await logger.getLogs()).toEqual([]);
    logger.close();
    indexedDB.deleteDatabase("test_db");
});

test("a closed database handle is forgotten and reopened on the next use", async () => {
    indexedDB.deleteDatabase("reopen_db");
    const logger = new Logger("reopen_db");
    await logger.log("before");
    expect(logger._db).not.toBe(null);

    const stale = logger._db;
    stale.close();
    stale.onclose?.();
    expect(logger._db).toBe(null);
    expect(logger._dbPromise).toBe(null);

    await logger.log("after");
    expect(logger._db).not.toBe(null);
    expect(await logger.getLogs()).toEqual(["before", "after"]);
    logger.close();
    indexedDB.deleteDatabase("reopen_db");
});

test("a handle that dies without a close event is dropped on the failed use", async () => {
    indexedDB.deleteDatabase("drop_db");
    const logger = new Logger("drop_db");
    await logger.log("first");
    logger._db.close();
    await expect(logger.log("second")).rejects.toThrow();
    expect(logger._db).toBe(null);
    await logger.log("third");
    expect(await logger.getLogs()).toEqual(["first", "third"]);
    logger.close();
    indexedDB.deleteDatabase("drop_db");
});

test("a closed logger lets its store be deleted and leaves the GC", async () => {
    indexedDB.deleteDatabase("closed_db");
    const logger = new Logger("closed_db");
    await logger.log("first");
    logger.close();
    expect(Logger.instances.includes(logger)).toBe(false);
    const deleted = await new Promise((resolve) => {
        const request = indexedDB.deleteDatabase("closed_db");
        request.onsuccess = () => resolve("deleted");
        request.onblocked = () => resolve("blocked");
    });
    expect(deleted).toBe("deleted");
});

test("an open landing after close() leaves no handle", async () => {
    indexedDB.deleteDatabase("late_db");
    const logger = new Logger("late_db");
    const logged = logger.log("first");
    logger.close();
    await expect(logged).rejects.toThrow();
    expect(logger._db).toBe(null);
    indexedDB.deleteDatabase("late_db");
});
