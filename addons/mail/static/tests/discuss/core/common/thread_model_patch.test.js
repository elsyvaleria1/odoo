// @ts-check
import { defineMailModels, start, startServer } from "@mail/../tests/mail_test_helpers";
import { Store } from "@mail/core/common/store_service";
import { describe, expect, test } from "@odoo/hoot";
import {
    getService,
    mockService,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("reading displayName does not reorder channel_name_member_ids in place", async () => {
    await start();
    const store = getService("mail.store");
    const thread = store["discuss.channel"].insert({
        id: 1,
        channel_type: "group",
        channel_name_member_ids: [
            { id: 30, guest_id: { id: 3, name: "Charlie" } },
            { id: 10, guest_id: { id: 1, name: "Alice" } },
            { id: 20, guest_id: { id: 2, name: "Bob" } },
        ],
    });
    expect(thread.channel_name_member_ids.map((member) => member.id)).toEqual([
        30, 10, 20,
    ]);

    expect(thread.displayName).toBe("Alice, Bob, and Charlie");

    expect(thread.channel_name_member_ids.map((member) => member.id)).toEqual([
        30, 10, 20,
    ]);
});

test("getOrFetch resolves (never rejects) when the channel fetch fails", async () => {
    await start();
    const store = getService("mail.store");
    patchWithCleanup(Store.prototype, {
        fetchChannel() {
            return Promise.reject(new Error("boom"));
        },
    });
    let rejected = false;
    /** @type {string|import("models").Thread|undefined} */
    let result = "unset";
    await store.Thread.getOrFetch({ id: 999, model: "discuss.channel" }).then(
        (thread) => (result = thread),
        () => (rejected = true),
    );
    expect(rejected).toBe(false);
    expect(result).toBe(undefined);
});

test("checkReadAccess answers whether the channel could be fetched", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    await start();
    const store = getService("mail.store");
    const channel = store["discuss.channel"].insert({
        id: channelId,
        channel_type: "channel",
    });
    expect(await channel.checkReadAccess()).toBe(true);
    const gone = store["discuss.channel"].insert({ id: 999, channel_type: "channel" });
    expect(await gone.checkReadAccess()).toBe(false);
});

test("rename reverts the optimistic name when the server call fails", async () => {
    await start();
    const store = getService("mail.store");
    const thread = store["discuss.channel"].insert({
        id: 1,
        channel_type: "channel",
        name: "Original",
    });
    mockService("orm", {
        call() {
            return Promise.reject(new Error("boom"));
        },
    });
    let threw = false;
    await thread.rename("New name").catch(() => (threw = true));
    expect(threw).toBe(true);
    expect(thread.name).toBe("Original");
});

test("notifyDescriptionToServer reverts the optimistic description on failure", async () => {
    await start();
    const store = getService("mail.store");
    const thread = store["discuss.channel"].insert({
        id: 1,
        channel_type: "channel",
        description: "Old description",
    });
    mockService("orm", {
        call() {
            return Promise.reject(new Error("boom"));
        },
    });
    let threw = false;
    await thread
        .notifyDescriptionToServer("New description")
        .catch(() => (threw = true));
    expect(threw).toBe(true);
    expect(thread.description).toBe("Old description");
});
