// @ts-check
import {
    contains,
    defineMailModels,
    inputFiles,
    insertText,
    openDiscuss,
    start,
    startServer,
    triggerHotkey,
} from "@mail/../tests/mail_test_helpers";
import { FETCH_DATA_DEBOUNCE_DELAY } from "@mail/core/common/constants";
import { Store } from "@mail/core/common/store_service";
import { describe, expect, test } from "@odoo/hoot";
import { advanceTime, Deferred } from "@odoo/hoot-mock";
import {
    getService,
    makeServerError,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

test("jumping to the present keeps a message that arrived while the latest page loaded", async () => {
    const pyEnv = await startServer();
    const partnerId = pyEnv["res.partner"].create({ name: "John" });
    const messageIds = pyEnv["mail.message"].create([
        { body: "message 1", model: "res.partner", res_id: partnerId },
        { body: "message 2", model: "res.partner", res_id: partnerId },
    ]);
    const serverSnapshot = new Deferred();
    onRpc("/mail/thread/messages", async () => {
        await serverSnapshot;
    });
    await start();
    const store = getService("mail.store");
    const thread = store.Thread.insert({ id: partnerId, model: "res.partner" });
    thread.loadNewer = true;
    const loading = thread.loadAround();
    const lateId = messageIds[1] + 100;
    thread.pendingNewMessages.push(
        store["mail.message"].insert({
            id: lateId,
            body: "committed after the snapshot",
            thread: { id: partnerId, model: "res.partner" },
        }),
    );
    serverSnapshot.resolve();
    await loading;
    expect(thread.loadNewer).toBe(false);
    expect(thread.messages.map((message) => message.id)).toEqual([
        ...messageIds,
        lateId,
    ]);
    expect(thread.pendingNewMessages.length).toBe(0);
});

test("a star toggle creates no record for a message this tab never loaded", async () => {
    await start();
    const store = getService("mail.store");
    const known = store["mail.message"].insert({ id: 5, starred: true });
    getService("mail.core.common")._handleNotificationToggleStar(
        { message_ids: [5, 404], starred: false },
        { id: 10 },
    );
    expect(known.starred).toBe(false);
    expect(store["mail.message"].get(404)).toBe(undefined);
});

test("starring a message this tab never loaded counts it and reloads the Bookmarks tab", async () => {
    await start();
    const store = getService("mail.store");
    const bookmarkTab = store.messagingMenu.bookmarkTab;
    const counter = store.starred_counter;
    bookmarkTab.loadStatusByFilterId = { _base: "loaded" };
    getService("mail.core.common")._handleNotificationToggleStar(
        { message_ids: [404], starred: true },
        { id: 11 },
    );
    expect(store.starred_counter).toBe(counter + 1);
    expect(bookmarkTab.getLoadStatus()).toBe("new");
    expect(store["mail.message"].get(404)).toBe(undefined);
});

test("getOrFetch returns the known thread and warns when the fetch fails", async () => {
    let failFetch = false;
    onRpc("/mail/data", () => {
        if (failFetch) {
            throw makeServerError({ message: "fetch boom" });
        }
    });
    await start();
    const store = getService("mail.store");
    const thread = store.Thread.insert({ model: "res.partner", id: 3 });
    const warnings = [];
    patchWithCleanup(console, {
        warn: (...args) => warnings.push(args.map(String).join(" ")),
    });
    failFetch = true;
    const fetching = store.Thread.getOrFetch({ model: "res.partner", id: 3 }, [
        "hasReadAccess",
    ]);
    await advanceTime(FETCH_DATA_DEBOUNCE_DELAY);
    const result = await fetching;
    expect(result?.eq(thread)).toBe(true);
    expect(warnings.some((line) => line.includes("res.partner,3"))).toBe(true);
});

test("deleting a thread deletes its followers", async () => {
    await start();
    const store = getService("mail.store");
    const thread = store.Thread.insert({
        model: "res.partner",
        id: 3,
        followers: [{ id: 11 }],
        selfFollower: { id: 12 },
    });
    const [follower] = thread.followers;
    const selfFollower = thread.selfFollower;
    expect(follower.thread?.eq(thread)).toBe(true);
    thread.delete();
    expect(follower.exists()).toBe(false);
    expect(selfFollower.exists()).toBe(false);
});

test("merging into a queued data fetch keeps the stricter readonly and silent flags", async () => {
    await start();
    const store = getService("mail.store");
    patchWithCleanup(Store.prototype, {
        _fetchStoreDataRpc() {
            expect.step(`readonly=${this.fetchReadonly} silent=${this.fetchSilent}`);
            return Promise.resolve({});
        },
    });
    /** @param {number[]} queued */
    const merge = (queued, incoming) => [...queued, ...incoming];
    const first = store.fetchStoreData("probe", [1], { merge });
    const second = store.fetchStoreData("probe", [2], {
        merge,
        readonly: false,
        silent: false,
    });
    await advanceTime(FETCH_DATA_DEBOUNCE_DELAY);
    await Promise.all([first, second]);
    expect.verifySteps(["readonly=false silent=false"]);
});

test("an upload the proxy refuses as too large says so instead of showing the proxy page", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "channel_1" });
    onRpc(
        "/mail/attachment/upload",
        () =>
            new Response(
                "<html><body><h1>413 Request Entity Too Large</h1><hr><center>nginx</center></body></html>",
                { status: 413 },
            ),
    );
    await start();
    await openDiscuss(channelId);
    const file = new File(["hello, world"], "text.txt", { type: "text/plain" });
    await inputFiles(".o-mail-Composer input[type=file]", [file]);
    await contains(".o_notification", { text: "File too large" });
    await contains(".o_notification", { count: 1 });
    await contains(".o-mail-AttachmentContainer", { count: 0 });
    expect(getService("mail.attachment_upload").pendingUploads.size).toBe(0);
});

test("a channel message whose optimistic post fails gets its text back in the composer", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "general" });
    await start();
    await openDiscuss(channelId);
    patchWithCleanup(Store.prototype, {
        getNextTemporaryId() {
            throw new Error("temporary id boom");
        },
    });
    patchWithCleanup(console, { warn: () => {} });
    await insertText(".o-mail-Composer-input", "Hello");
    triggerHotkey("Enter");
    await contains(".o_notification", {
        text: "Your message could not be sent. Its text is back in the composer.",
    });
    await contains(".o-mail-Composer-input", { value: "Hello" });
    await contains(".o-mail-Message", { count: 0 });
});
