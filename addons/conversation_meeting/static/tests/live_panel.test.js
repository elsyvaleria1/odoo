import { ConversationLivePanel } from "@conversation_meeting/live_panel/live_panel";
import { expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, useProps, xml } from "@odoo/owl";
import { mockService, mountWithCleanup } from "@web/../tests/web_test_helpers";

function fakeRecord(data, { dirty = false } = {}) {
    const record = { resId: 7, data, dirty, loads: 0 };
    record.load = async () => {
        record.loads += 1;
    };
    return record;
}

function mockBus() {
    const bus = { channels: [], handlers: {} };
    mockService("bus_service", {
        addChannel: (channel) => bus.channels.push(channel),
        deleteChannel: (channel) =>
            bus.channels.splice(bus.channels.indexOf(channel), 1),
        subscribe: (type, handler) => (bus.handlers[type] = handler),
        unsubscribe: (type) => delete bus.handlers[type],
    });
    return bus;
}

class Root extends Component {
    static template = xml`<ConversationLivePanel record="this.props.record"/>`;
    static components = { ConversationLivePanel };
    static props = null;
    props = useProps(this.constructor.props);
}

test("a live record subscribes to its record channel, not a token", async () => {
    const bus = mockBus();
    const record = fakeRecord({
        is_live: true,
        live_elapsed_s: 30,
        live_chunk_count: 2,
    });
    await mountWithCleanup(Root, { props: { record } });

    expect(bus.channels).toEqual(["speech.live/conversation.conversation/7"]);
    expect(".badge").toHaveText("LIVE");
    expect(".o_conversation_live_panel .text-muted").toHaveText("00:30 · 2 chunks");
});

test("a chunk updates the panel from the payload and reloads a clean record", async () => {
    const bus = mockBus();
    const record = fakeRecord({
        is_live: true,
        live_elapsed_s: 0,
        live_chunk_count: 0,
    });
    await mountWithCleanup(Root, { props: { record } });

    await bus.handlers["speech.live"]({
        model: "conversation.conversation",
        id: 7,
        event: "chunk",
        text: "hola",
        chunks: 1,
        elapsed_s: 15,
    });
    await animationFrame();

    expect(".fst-italic").toHaveText("hola");
    expect(".o_conversation_live_panel .text-muted").toHaveText("00:15 · 1 chunks");
    expect(record.loads).toBe(1);
});

test("a dirty record is never reloaded under the moderator", async () => {
    const bus = mockBus();
    const record = fakeRecord(
        { is_live: true, live_elapsed_s: 0, live_chunk_count: 0 },
        { dirty: true },
    );
    await mountWithCleanup(Root, { props: { record } });

    await bus.handlers["speech.live"]({
        model: "conversation.conversation",
        id: 7,
        event: "notice",
        at_s: 60,
        text: "Decisión sin dueño",
    });
    await animationFrame();

    expect(".alert-warning").toHaveText(/01:00.*Decisión sin dueño/);
    expect(record.loads).toBe(0);
});

test("another record's notification is ignored and stop ends the session", async () => {
    const bus = mockBus();
    const record = fakeRecord({
        is_live: true,
        live_elapsed_s: 0,
        live_chunk_count: 0,
    });
    await mountWithCleanup(Root, { props: { record } });

    await bus.handlers["speech.live"]({
        model: "conversation.conversation",
        id: 8,
        event: "chunk",
        text: "ajeno",
        chunks: 9,
    });
    await animationFrame();
    expect(".fst-italic").toHaveCount(0);

    await bus.handlers["speech.live"]({
        model: "conversation.conversation",
        id: 7,
        event: "stopped",
    });
    await animationFrame();
    expect(".badge").toHaveCount(0);
    expect(".o_conversation_live_panel").toHaveText("No live session.");
});

test("a record that is not live subscribes to nothing", async () => {
    const bus = mockBus();
    await mountWithCleanup(Root, { props: { record: fakeRecord({ is_live: false }) } });

    expect(bus.channels).toEqual([]);
    expect(".o_conversation_live_panel").toHaveText("No live session.");
});
