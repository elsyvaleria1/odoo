// @ts-check
import { defineMailModels, start as start2 } from "@mail/../tests/mail_test_helpers";
import { makeStore, Record, Store } from "@mail/core/common/record";
import { AND, fields } from "@mail/model/misc";
import { afterEach, beforeEach, describe, expect, test } from "@odoo/hoot";
import { mockService } from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";

describe.current.tags("desktop");
defineMailModels();

const localRegistry = registry.category("discuss.model.test");

beforeEach(() => {
    Record.register(localRegistry);
    Store.register(localRegistry);
    mockService("store", (env) => makeStore(env, { localRegistry }));
});
afterEach(() => {
    for (const [modelName] of localRegistry.getEntries()) {
        localRegistry.remove(modelName);
    }
});

async function start() {
    const env = await start2();
    return env.services.store;
}

function registerPair() {
    (class Pair extends Record {
        static id = AND("left", "right");
        left;
        right;
    }).register(localRegistry);
}

test("a computed value its relation rejects fails that update only, after the rest of its flush", async () => {
    registerPair();
    (class Thread extends Record {
        static id = "name";
        name;
        trigger = fields.Attr(false);
        broken = fields.Attr(undefined, {
            /** @this {Thread} */
            compute() {
                if (this.trigger) {
                    throw new Error("compute boom");
                }
            },
        });
        pair = fields.One(/** @type {string} */ ("Pair"), {
            /** @this {Thread} */
            compute() {
                return this.trigger ? "not a composite id" : undefined;
            },
        });
        topic = fields.Attr("", {
            /** @this {Thread} */
            onUpdate() {
                expect.step(`onUpdate(${this.topic})`);
            },
        });
    }).register(localRegistry);
    (class Member extends Record {
        static id = "name";
        name;
    }).register(localRegistry);
    const store = await start();
    store.logErrors = false;
    const thread = store.Thread.insert("General");
    const doomed = store.Member.insert("doomed");
    Record.onChange(thread, "topic", () => expect.step("onChange(topic)"));

    expect(() =>
        store.MAKE_UPDATE(() => {
            thread.trigger = true;
            thread.topic = "weather";
            doomed.delete();
        }),
    ).toThrow("compute boom");
    expect.verifySteps(["onUpdate(weather)", "onChange(topic)"]);
    expect(doomed.exists()).toBe(false);
    expect(thread.pair).toBe(undefined);

    expect(() => store.Member.insert("unrelated")).not.toThrow();
});

test("a sort that throws on a scalar field is reported instead of aborting the flush", async () => {
    (class Thread extends Record {
        static id = "name";
        name;
        tags = fields.Attr([], {
            sort() {
                throw new Error("sort boom");
            },
        });
        topic = fields.Attr("");
    }).register(localRegistry);
    const store = await start();
    store.logErrors = false;
    const thread = store.Thread.insert("General");
    Record.onChange(thread, "topic", () => expect.step("onChange(topic)"));

    expect(() =>
        store.MAKE_UPDATE(() => {
            thread.tags = ["b", "a"];
            thread.topic = "weather";
        }),
    ).toThrow("sort boom");
    expect.verifySteps(["onChange(topic)"]);
    expect(() => store.Thread.insert("Other")).not.toThrow();
});

test("a row that fails to insert does not drop the rows after it", async () => {
    registerPair();
    (class Message extends Record {
        static id = "id";
        id;
        pair = fields.One(/** @type {string} */ ("Pair"));
    }).register(localRegistry);
    const store = await start();
    store.logErrors = false;

    expect(() =>
        store.Message.insert([{ id: 1 }, { id: 2, pair: "scalar" }, { id: 3 }]),
    ).toThrow(/doesn't support single-id data/);
    expect(store.Message.get(1)).not.toBe(undefined);
    expect(store.Message.get(3)).not.toBe(undefined);

    expect(() =>
        store.insert({ Message: [{ id: 4, pair: "scalar" }, { id: 5 }] }),
    ).toThrow(/doesn't support single-id data/);
    expect(store.Message.get(5)).not.toBe(undefined);
});

test("onChange on several keys runs once when they change in the same update", async () => {
    (class Thread extends Record {
        static id = "name";
        name;
        topic = fields.Attr("");
        label = fields.Attr("");
    }).register(localRegistry);
    const store = await start();
    const thread = store.Thread.insert("General");
    Record.onChange(thread, ["topic", "label"], () => expect.step("changed"));

    store.MAKE_UPDATE(() => {
        thread.topic = "a";
        thread.label = "b";
    });
    expect.verifySteps(["changed"]);
    thread.topic = "c";
    expect.verifySteps(["changed"]);
    thread.label = "d";
    expect.verifySteps(["changed"]);
});

test("in() on a record list follows membership, not a re-inserted namesake", async () => {
    (class Thread extends Record {
        static id = "name";
        name;
        members = fields.Many(/** @type {string} */ ("Member"));
    }).register(localRegistry);
    (class Member extends Record {
        static id = "name";
        name;
    }).register(localRegistry);
    const store = await start();
    const thread = store.Thread.insert("General");
    const alice = store.Member.insert("alice");
    const bob = store.Member.insert("bob");
    thread.members = [alice];
    expect(alice.in(thread.members)).toBe(true);
    expect(bob.in(thread.members)).toBe(false);
    expect(bob.notIn(thread.members)).toBe(true);
    expect(alice.in([bob, alice])).toBe(true);

    alice.delete();
    const newAlice = store.Member.insert("alice");
    thread.members.add(newAlice);
    expect(newAlice.in(thread.members)).toBe(true);
    expect(alice.in(thread.members)).toBe(false);
});
