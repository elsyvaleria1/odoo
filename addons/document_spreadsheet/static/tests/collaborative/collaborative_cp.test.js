import { defineDocumentSpreadsheetModels } from "@document_spreadsheet/../tests/helpers/data";
import {
    createSpreadsheet,
    displayedConnectedUsers,
    getSynchedStatus,
} from "@document_spreadsheet/../tests/helpers/spreadsheet_test_utils";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { setCellContent } from "@spreadsheet/../tests/helpers/commands";
import { getCellContent } from "@spreadsheet/../tests/helpers/getters";
import {
    joinSession,
    leaveSession,
} from "@spreadsheet_edition/../tests/helpers/collaborative_helpers";
import { mockService, onRpc } from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";

defineDocumentSpreadsheetModels();

describe.current.tags("desktop");

test("Number of connected users is correctly rendered", async function () {
    const { transportService } = await createSpreadsheet();
    await animationFrame();
    expect(displayedConnectedUsers()).toBe(0, {
        message: "It should display no other connected user",
    });
    joinSession(transportService, { id: 1234, userId: 9999 });
    await animationFrame();
    expect(displayedConnectedUsers()).toBe(1, {
        message: "It should display one other connected users",
    });

    // The same user is connected with two different tabs.
    joinSession(transportService, { id: 4321, userId: 9999 });
    await animationFrame();
    expect(displayedConnectedUsers()).toBe(1, {
        message: "It should display one other connected users",
    });

    leaveSession(transportService, 4321);
    await animationFrame();
    expect(displayedConnectedUsers()).toBe(1, {
        message: "It should display one other connected users",
    });

    leaveSession(transportService, 1234);
    await animationFrame();
    expect(displayedConnectedUsers()).toBe(0, {
        message: "It should display no other connected user",
    });
});

test("collaborative session client has the user id", async function () {
    const uid = user.userId;
    const { model } = await createSpreadsheet();
    const clients = [...model.getters.getConnectedClients()];
    expect(clients.length).toBe(1);
    const localClient = clients[0];
    expect(localClient.name).toBe(user.name);
    expect(localClient.userId).toBe(uid);
});

test("Sync status is correctly rendered", async function () {
    const { model, transportService } = await createSpreadsheet();
    await animationFrame();
    expect(getSynchedStatus()).toBe("Saved");
    await transportService.concurrent(async () => {
        setCellContent(model, "A1", "hello");
        await animationFrame();
        expect(getSynchedStatus()).toBe("Saving");
    });
    await animationFrame();
    expect(getSynchedStatus()).toBe("Saved");
});

test("a revision the server history no longer has reloads", async function () {
    mockService("action", {
        doAction(actionRequest) {
            if (actionRequest === "reload_context") {
                expect.step("reload");
            } else {
                return super.doAction(...arguments);
            }
        },
    });
    const { transportService } = await createSpreadsheet();
    transportService.broadcast({
        type: "REMOTE_REVISION",
        serverRevisionId: "an invalid revision id",
        nextRevisionId: "the next revision id",
        revision: {},
    });
    await animationFrame();
    expect.verifySteps(["reload"]);
});

test("a missed revision is caught up from the server, not by a reload", async function () {
    mockService("action", {
        doAction(actionRequest) {
            if (actionRequest === "reload_context") {
                expect.step("reload");
            } else {
                return super.doAction(...arguments);
            }
        },
    });
    const { model, transportService } = await createSpreadsheet();
    const head = model.session.getRevisionId();
    const sheetId = model.getters.getActiveSheetId();
    const revision = (serverRevisionId, nextRevisionId, col, content) => ({
        type: "REMOTE_REVISION",
        version: 1,
        clientId: "raoul",
        serverRevisionId,
        nextRevisionId,
        commands: [{ type: "UPDATE_CELL", sheetId, col, row: 0, content }],
    });
    const missed = revision(head, "missed", 0, "missed");
    const received = revision("missed", "received", 1, "received");
    onRpc("get_spreadsheet_revisions_after", ({ args }) => {
        expect.step(`after ${args[1] === head ? "the head" : args[1]}`);
        return [missed, received];
    });
    transportService.broadcast(received);
    await animationFrame();
    expect.verifySteps(["after the head"]);
    expect(getCellContent(model, "A1")).toBe("missed");
    expect(getCellContent(model, "B1")).toBe("received");
    expect(model.session.getRevisionId()).toBe("received");
});

test("a catch-up the server fails reloads, as before catching up", async function () {
    mockService("action", {
        doAction(actionRequest) {
            if (actionRequest === "reload_context") {
                expect.step("reload");
            } else {
                return super.doAction(...arguments);
            }
        },
    });
    onRpc("get_spreadsheet_revisions_after", () => {
        throw new Error("the server failed");
    });
    const { model, transportService } = await createSpreadsheet();
    transportService.broadcast({
        type: "REMOTE_REVISION",
        version: 1,
        clientId: "raoul",
        serverRevisionId: "not this session's head",
        nextRevisionId: "next",
        commands: [],
    });
    await animationFrame();
    expect.verifySteps(["reload"]);
    expect(model.session.getRevisionId()).not.toBe("next");
});
