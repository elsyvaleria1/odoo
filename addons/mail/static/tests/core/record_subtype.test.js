// @ts-check
import { defineMailModels, start as start2 } from "@mail/../tests/mail_test_helpers";
import { makeStore, Record, Store } from "@mail/core/common/record";
import { AND, fields } from "@mail/model/misc";
import { afterEach, beforeEach, describe, expect, test } from "@odoo/hoot";
import { mockService, patchWithCleanup } from "@web/../tests/web_test_helpers";
import { registry } from "@web/core/registry";

describe.current.tags("desktop");
defineMailModels();

const localRegistry = registry.category("discuss.model.subtype.test");

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

class Conversation extends Record {
    static id = AND("model", "id");
    static _discriminator = "model";
    /** @type {string} */
    model;
    /** @type {number} */
    id;
    notes = fields.Many(/** @type {string} */ ("Note"), { inverse: "conversation" });
    get kind() {
        return "plain";
    }
}

class Room extends Conversation {
    static _name = "chat.room";
    seats = fields.Many(/** @type {string} */ ("Seat"), { inverse: "room" });
    get kind() {
        return "room";
    }
}

class Note extends Record {
    static id = "id";
    /** @type {number} */
    id;
    conversation = fields.One(/** @type {string} */ ("Conversation"));
}

class Seat extends Record {
    static id = "id";
    /** @type {number} */
    id;
    room = fields.One(/** @type {string} */ ("chat.room"));
}

function registerModels() {
    for (const Model of [Conversation, Room, Note, Seat]) {
        Model.register(localRegistry);
    }
}

test("the discriminator picks the subtype, and both models return the same record", async () => {
    registerModels();
    const store = await start();
    const room = store.Conversation.insert({ model: "chat.room", id: 1 });
    const document = store.Conversation.insert({ model: "res.partner", id: 1 });
    expect(room instanceof Room).toBe(true);
    expect(document instanceof Room).toBe(false);
    expect(room.kind).toBe("room");
    expect(document.kind).toBe("plain");
    expect(store["chat.room"].get(1)).toBe(room);
    expect(store["chat.room"].get({ id: 1 })).toBe(room);
    expect(store.Conversation.get({ model: "chat.room", id: 1 })).toBe(room);
    expect(room.localId).toBe(
        store.Conversation.localId({ model: "chat.room", id: 1 }),
    );
    expect(Object.values(store.Conversation.records)).toHaveLength(2);
    expect(Object.values(store["chat.room"].records)).toEqual([room]);
    expect(store["chat.room"].get({ model: "res.partner", id: 1 })).toBe(undefined);
});

test("a subtype inherits its parent model, not the other way around", async () => {
    registerModels();
    const store = await start();
    const room = store["chat.room"].insert(1);
    expect(room.Model.inherits("Conversation")).toBe(true);
    expect(room.Model.inherits("chat.room")).toBe(true);
    expect(store.Conversation.inherits("chat.room")).toBe(false);
    expect(store.Note.inherits("Conversation")).toBe(false);
});

test("inserting through the subtype fills in the discriminator", async () => {
    registerModels();
    const store = await start();
    const room = store["chat.room"].insert(7);
    expect(room.model).toBe("chat.room");
    expect(room.id).toBe(7);
    expect(store.Conversation.get({ model: "chat.room", id: 7 })).toBe(room);
    expect(store["chat.room"].insert({ id: 7 })).toBe(room);
});

test("a subtype record cannot be created under another discriminator value", async () => {
    registerModels();
    const store = await start();
    expect(() => store["chat.room"].insert({ model: "res.partner", id: 3 })).toThrow(
        /whose model is "res.partner"/,
    );
});

test("only the subtype has its own fields", async () => {
    registerModels();
    const store = await start();
    const room = store["chat.room"].insert({ id: 1, seats: [10, 11] });
    const document = store.Conversation.insert({ model: "res.partner", id: 1 });
    expect(room.seats.map((seat) => seat.id)).toEqual([10, 11]);
    expect(store.Seat.get(10).room).toBe(room);
    expect(store.Conversation._.fields.has("seats")).toBe(false);
    expect(document.seats).toBe(undefined);
});

test("a relation to the parent model holds subtype records, inverse included", async () => {
    registerModels();
    const store = await start();
    const room = store["chat.room"].insert(1);
    const note = store.Note.insert({
        id: 5,
        conversation: { model: "chat.room", id: 1 },
    });
    expect(note.conversation).toBe(room);
    expect(room.notes.map((n) => n.id)).toEqual([5]);
});

test("a relation to the subtype accepts a bare id", async () => {
    registerModels();
    const store = await start();
    const seat = store.Seat.insert({ id: 3, room: 4 });
    expect(seat.room instanceof Room).toBe(true);
    expect(seat.room.model).toBe("chat.room");
    expect(seat.room.seats.map((s) => s.id)).toEqual([3]);
});

test("deleting a subtype record removes it from every model of the chain", async () => {
    registerModels();
    const store = await start();
    const room = store["chat.room"].insert(1);
    room.delete();
    expect(store["chat.room"].get(1)).toBe(undefined);
    expect(store.Conversation.get({ model: "chat.room", id: 1 })).toBe(undefined);
    expect(Object.values(store.Conversation.records)).toHaveLength(0);
});

test("a patch of the parent prototype reaches subtype records", async () => {
    registerModels();
    patchWithCleanup(Conversation.prototype, {
        get label() {
            return `${this.kind}:${this.id}`;
        },
    });
    const store = await start();
    expect(store["chat.room"].insert(2).label).toBe("room:2");
    expect(store.Conversation.insert({ model: "res.partner", id: 2 }).label).toBe(
        "plain:2",
    );
});

test("extending a model that declares no discriminator keeps two separate identities", async () => {
    class Plain extends Record {
        static id = "id";
        /** @type {number} */
        id;
    }
    class Derived extends Plain {
        static _name = "Derived";
    }
    Plain.register(localRegistry);
    Derived.register(localRegistry);
    const store = await start();
    const derived = store.Derived.insert(1);
    const plain = store.Plain.insert(1);
    expect(derived).not.toBe(plain);
    expect(plain instanceof Derived).toBe(false);
    expect(store.Plain.get(1)).toBe(plain);
});
