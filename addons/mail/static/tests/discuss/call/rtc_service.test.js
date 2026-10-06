// @ts-check
import { defineMailModels, start, startServer } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";

describe.current.tags("desktop");
defineMailModels();

test("network broadcasts only advance sequence from a numeric message field", async () => {
    const env = await start();
    const store = env.services["mail.store"];
    const session = store["discuss.channel.rtc.session"].insert({ id: 42 });
    session.sequence = 1;
    for (const message of [
        null,
        undefined,
        "ping",
        0,
        {},
        { sequence: "7" },
        { sequence: 0 },
    ]) {
        await store.rtc._onNetworkBroadcast({ senderId: session.id, message });
        expect(session.sequence).toBe(1);
    }
    await store.rtc._onNetworkBroadcast({
        senderId: session.id,
        message: { sequence: 7 },
    });
    expect(session.sequence).toBe(7);
    await store.rtc._onNetworkBroadcast({
        senderId: session.id,
        message: { sequence: 3 },
    });
    expect(session.sequence).toBe(7);
});

test("partial session updates keep the raised hand and merge into a pending full update", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    const env = await start();
    const store = env.services["mail.store"];
    const rtc = store.rtc;
    const channel = store.Thread.insert({ model: "discuss.channel", id: channelId });
    const session = store["discuss.channel.rtc.session"].insert({
        id: 42,
        channel_member_id: { id: 1042, channel_id: channel },
    });
    rtc.state.remoteChannelId = channelId;
    rtc.updateSessionInfo({ 42: { isRaisingHand: true, is_muted: true } });
    rtc.updateSessionInfo({ 42: { is_camera_on: false } });
    await animationFrame();
    expect(Boolean(session.raisingHand)).toBe(true);
    expect(session.is_muted).toBe(true);
    rtc.updateSessionInfo({ 42: { is_deaf: true } });
    await animationFrame();
    expect(Boolean(session.raisingHand)).toBe(true);
    expect(session.is_deaf).toBe(true);
    rtc.updateSessionInfo({ 42: { isRaisingHand: false } });
    await animationFrame();
    expect(session.raisingHand).toBe(undefined);
});
