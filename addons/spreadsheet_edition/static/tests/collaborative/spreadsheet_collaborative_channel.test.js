import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { EventBus } from "@odoo/owl";
import { defineSpreadsheetModels } from "@spreadsheet/../tests/helpers/data";
import { makeSpreadsheetMockEnv } from "@spreadsheet/../tests/helpers/model";
import { SpreadsheetCollaborativeChannel } from "@spreadsheet_edition/bundle/o_spreadsheet/collaborative/spreadsheet_collaborative_channel";
import { mockService } from "@web/../tests/web_test_helpers";

describe.current.tags("headless");
defineSpreadsheetModels();

async function setupEnvWithMockBus({ mockRPC } = {}) {
    const _bus = new EventBus();

    const busService = {
        channels: [],
        addChannel(name) {
            this.channels.push(name);
            return () => this.channels.splice(this.channels.indexOf(name), 1);
        },
        subscribe: (eventName, handler) => {
            const listener = ({ detail }) => {
                if (detail.type === eventName) {
                    handler(detail.payload, { id: detail.id });
                }
            };
            _bus.addEventListener("notif", listener);
            return () => _bus.removeEventListener("notif", listener);
        },
        notify: (message) => {
            _bus.trigger("notif", message);
        },
    };
    const rpc =
        mockRPC ||
        function (route, params) {
            // Mock the server behavior: new revisions are pushed in the bus
            if (params.method === "dispatch_spreadsheet_message") {
                const [documentId, message] = params.args;
                busService.notify({
                    type: "spreadsheet",
                    payload: { id: documentId, model: params.model, ...message },
                });
                return true;
            }
        };
    mockService("bus_service", busService);
    return makeSpreadsheetMockEnv({
        mockRPC: rpc,
    });
}

test("sending a message forward it to the registered listener", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    let i = 5;
    channel.onNewMessage("anId", (message) => {
        expect.step("message");
        expect(message.greeting).toBe("hello", {
            message: "It should have the correct message content",
        });
        i = 8;
    });
    await channel.sendMessage({ greeting: "hello" });
    expect(i).toBe(8);
    // It should have received the message
    expect.verifySteps(["message", "message"]);
});

test("the bus channel carries the access token the server checks", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    const sharedChannel = new SpreadsheetCollaborativeChannel(
        env,
        "my.model",
        5,
        "a-token",
    );
    expect(channel._channel).toBe("spreadsheet_collaborative_session:my.model:5");
    expect(sharedChannel._channel).toBe(
        "spreadsheet_collaborative_session:my.model:5:a-token",
    );
});

test("previous messages are forwarded when registering a listener", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    await channel.sendMessage({ greeting: "hello" });
    channel.onNewMessage("anId", (message) => {
        expect.step("message");
        expect(message.greeting).toBe("hello", {
            message: "It should have the correct message content",
        });
    });
    // It should have received the pending message
    expect.verifySteps(["message", "message"]);
});

test("the channel does not care about other bus messages", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    channel.onNewMessage("anId", () => expect.step("message"));
    env.services.bus_service.notify("a-random-channel", "a-random-message");
    await animationFrame();
    // The message should not have been received
    expect.verifySteps([]);
});

test("a spreadsheet of another model with the same id is not this one", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    channel.onNewMessage("anId", (message) => expect.step(message.model));
    env.services.bus_service.notify({
        type: "spreadsheet",
        payload: { id: 5, model: "other.model", type: "CLIENT_MOVED" },
    });
    env.services.bus_service.notify({
        type: "spreadsheet",
        payload: { id: 5, model: "my.model", type: "CLIENT_MOVED" },
    });
    await animationFrame();
    expect.verifySteps(["my.model"]);
});

test("a revision the loaded data already holds is not delivered again", async function () {
    const env = await setupEnvWithMockBus();
    const channel = new SpreadsheetCollaborativeChannel(
        env,
        "my.model",
        5,
        undefined,
        7,
    );
    channel.onNewMessage("anId", (message) => expect.step(message.type));
    for (const revisionSequence of [6, 7, 8]) {
        env.services.bus_service.notify({
            type: "spreadsheet",
            payload: {
                id: 5,
                model: "my.model",
                type: `REVISION_${revisionSequence}`,
                revisionSequence,
            },
        });
    }
    env.services.bus_service.notify({
        type: "spreadsheet",
        payload: { id: 5, model: "my.model", type: "CLIENT_MOVED" },
    });
    await animationFrame();
    expect.verifySteps(["REVISION_8", "CLIENT_MOVED"]);
});

test("a released channel gives its bus claim back and hears nothing more", async function () {
    const env = await setupEnvWithMockBus();
    const kept = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    const released = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    kept.onNewMessage("anId", () => expect.step("kept"));
    released.onNewMessage("anId", () => expect.step("released"));
    released.release();
    released.release();
    expect(env.services.bus_service.channels).toEqual([
        "spreadsheet_collaborative_session:my.model:5",
    ]);
    env.services.bus_service.notify({
        type: "spreadsheet",
        payload: { id: 5, model: "my.model", type: "CLIENT_MOVED" },
    });
    await animationFrame();
    expect.verifySteps(["kept"]);
});

test("Message accepted by the server is immediately handled", async function () {
    const env = await setupEnvWithMockBus({
        mockRPC: async function (route, params) {
            // Mock the server to accept the revision
            if (params.method === "dispatch_spreadsheet_message") {
                return true;
            }
        },
    });
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    channel.onNewMessage("anId", (message) => {
        expect.step("message");
        expect(message.greeting).toBe("hello");
    });
    channel.sendMessage({ greeting: "hello" });
    await animationFrame();
    expect.verifySteps(["message"]);
});

test("Message refused by the server is not immediately handled", async function () {
    const env = await setupEnvWithMockBus({
        mockRPC: async function (route, params) {
            // Mock the server to refuse the revision
            if (params.method === "dispatch_spreadsheet_message") {
                return false;
            }
        },
    });
    const channel = new SpreadsheetCollaborativeChannel(env, "my.model", 5);
    channel.onNewMessage("anId", () => {
        expect.step("message");
    });
    channel.sendMessage({ greeting: "hello" });
    await animationFrame();
    expect.verifySteps([]);
});
