import {
    click,
    contains,
    defineMailModels,
    mockGetMedia,
    openDiscuss,
    start,
    startServer,
} from "@mail/../tests/mail_test_helpers";
import { CallRecordingService } from "@mail_speech/call_recording_service";
import { beforeEach, describe, expect, test } from "@odoo/hoot";
import { advanceTime } from "@odoo/hoot-dom";
import {
    asyncStep,
    getService,
    onRpc,
    patchWithCleanup,
    waitForSteps,
} from "@web/../tests/web_test_helpers";

describe.current.tags("desktop");
defineMailModels();

beforeEach(() => {
    mockGetMedia();
});

test("hanging up leaves the call", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    onRpc("/mail/rtc/channel/leave_call", () => asyncStep("leave_call"));
    await start();
    await openDiscuss(channelId);
    await click("[title='Start Call']");
    await contains(".o-discuss-Call");
    await click("[title='Disconnect']");
    await contains(".o-discuss-Call", { count: 0 });
    await waitForSteps(["leave_call"]);
});

test("an unanswered invitation is cancelled when it times out", async () => {
    const pyEnv = await startServer();
    const channelId = pyEnv["discuss.channel"].create({ name: "General" });
    const [selfMemberId] = pyEnv["discuss.channel.member"].search([
        ["channel_id", "=", channelId],
    ]);
    const bobMemberId = pyEnv["discuss.channel.member"].create({
        channel_id: channelId,
        partner_id: pyEnv["res.partner"].create({ name: "Bob" }),
    });
    const bobSessionId = pyEnv["discuss.channel.rtc.session"].create({
        channel_member_id: bobMemberId,
        channel_id: channelId,
    });
    pyEnv["discuss.channel.member"].write([selfMemberId], {
        rtc_inviting_session_id: bobSessionId,
    });
    onRpc("/mail/rtc/channel/leave_call", async (request) => {
        const { params } = await request.clone().json();
        asyncStep(`leave_call:${params.channel_id}`);
    });
    await start();
    await openDiscuss(channelId);
    await contains(".o-discuss-CallInvitation");
    await advanceTime(30_000);
    await waitForSteps([`leave_call:${channelId}`]);
    await contains(".o-discuss-CallInvitation", { count: 0 });
});

test("only leaving the recorded call stops the recording", async () => {
    const pyEnv = await startServer();
    const recordedId = pyEnv["discuss.channel"].create({ name: "Recorded" });
    const otherId = pyEnv["discuss.channel"].create({ name: "Other" });
    patchWithCleanup(CallRecordingService.prototype, {
        async stop() {
            asyncStep(`stop:${this.state.channelId}`);
            this.state.channelId = null;
        },
    });
    await start();
    getService("discuss.call_recording").state.channelId = recordedId;
    await openDiscuss(recordedId);
    await click("[title='Start Call']");
    await contains(".o-discuss-Call");
    const other = getService("mail.store").Thread.insert({
        model: "discuss.channel",
        id: otherId,
    });
    await getService("discuss.rtc").leaveCall(other);
    expect.verifySteps([]);
    await click("[title='Disconnect']");
    await waitForSteps([`stop:${recordedId}`]);
});
