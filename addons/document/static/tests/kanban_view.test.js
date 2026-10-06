import { defineDocumentsModels } from "@document/../tests/document_test_helpers";
import {
    DOCUMENT_UPLOAD_MARKER,
    MOVE_ACCESS_CHECK,
} from "@document/core/document_service";
import { documentsClientThumbnailService } from "@document/views/helper/document_client_thumbnail_service";
import { describe, expect, test } from "@odoo/hoot";
import {
    click,
    keyDown,
    press,
    queryAll,
    queryAllTexts,
    queryOne,
    setInputFiles,
    waitFor,
    waitForNone,
} from "@odoo/hoot-dom";
import { animationFrame, runAllTimers } from "@odoo/hoot-mock";
import { EventBus, markup } from "@odoo/owl";
import { inputFiles } from "@web/../tests/utils";
import {
    contains,
    defineActions,
    getService,
    mockService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
    toggleSearchBarMenu,
} from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";
import { WebClient } from "@web/webclient/webclient";

import {
    documentsMockUser,
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
    mimetypeExamplesBase64,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { embeddedActionsServerData } from "./helpers/test_server_data.js";
import {
    basicDocumentsKanbanArch,
    mountDocumentsKanbanView,
} from "./helpers/views/kanban.js";
import { getEnrichedSearchArch } from "./helpers/views/search.js";

describe.current.tags("desktop");

defineDocumentsModels();

defineActions([
    {
        id: 1,
        name: "Documents",
        res_model: "document.document",
        views: [[false, "kanban"]],
    },
]);

test("Open share with edit user_permission", async function () {
    onRpc("/documents/touch/accessTokenFolder1", () => ({}));
    const serverData = getDocumentsTestServerModelsData();
    const { id: folder1Id, name: folder1Name } = serverData["document.document"][0];
    mockService("document.document", {
        openSharingDialog: (documentIds) => {
            expect(documentIds).toEqual([folder1Id]);
            expect.step("open_share");
        },
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(
        `.o_kanban_record:contains(${folder1Name}) .o_record_selector`,
    ).click({
        ctrlKey: true,
    });
    await contains("button:contains(Share)").click();
    expect.verifySteps(["open_share"]);
});

test("Colorless-tags are also visible on cards", async function () {
    onRpc("/documents/touch/accessTokenFolder1", () => true);
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Testing tags", { folder_id: 1, tag_ids: [1, 2] }),
    ]);
    const { name: folder1Name } = serverData["document.document"][0];
    const archWithTags = basicDocumentsKanbanArch.replace(
        '<field name="name"/>',
        '<field name="name"/>\n' +
            '<field name="tag_ids" class="d-block text-wrap" widget="documents_many2many_tags" options="{\'color_field\': \'color\'}"/>',
    );
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView({ arch: archWithTags });
    await contains(`.o_kanban_record:contains(${folder1Name})`).click();
    await animationFrame();
    expect(
        ".o_kanban_record:contains('Testing tags') div[name='tag_ids'] div .o_tag:nth-of-type(1)",
    ).toHaveText("Colorless");
    expect(
        ".o_kanban_record:contains('Testing tags') div[name='tag_ids'] div .o_tag:nth-of-type(2)",
    ).toHaveText("Colorful");
});

test("Uploading from control panel", async () => {
    const _bus = new EventBus();
    mockService("file_upload", {
        bus: _bus,
        upload: (route) => {
            if (route.startsWith("/documents/upload")) {
                _bus.trigger("FILE_UPLOAD_LOADED", {
                    upload: {
                        data: new FormData(),
                        xhr: { status: 200, response: '{ "records": [] }' },
                    },
                });
                expect.step("doc uploaded");
            }
        },
    });
    const serverData = getDocumentsTestServerModelsData();
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains("button.btn.btn-primary.o-dropdown:contains('New')").click();
    await contains("button.btn.btn-link.o_documents_kanban_upload").click();
    await contains("input.o_input_file.o_hidden", {
        visible: false,
    }).click();
    await animationFrame();
    await setInputFiles([
        new File(["fake_file"], "fake_file.tiff", { type: "text/plain" }),
    ]);
    await animationFrame();

    expect.verifySteps(["doc uploaded"]);
});

test("Uploading while in Recent puts the file in My Drive", async () => {
    mockService("file_upload", {
        bus: new EventBus(),
        upload: (route, files, { buildFormData }) => {
            const formData = new FormData();
            buildFormData(formData);
            expect.step(`${route} ${formData.get("user_folder_id")}`);
        },
    });
    const serverData = getDocumentsTestServerModelsData();
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_search_panel_label_title:contains('Recent')").click();
    await contains("button.btn.btn-primary.o-dropdown:contains('New')").click();
    await contains("button.btn.btn-link.o_documents_kanban_upload").click();
    await contains("input.o_input_file.o_hidden", { visible: false }).click();
    await setInputFiles([new File(["x"], "recent.txt", { type: "text/plain" })]);
    await animationFrame();

    expect.verifySteps(["/documents/upload/ MY"]);
});

test("a failed upload-limit lookup is asked again, not remembered", async () => {
    let calls = 0;
    patchWithCleanup(DocumentsModels.DocumentsDocument.prototype, {
        get_document_max_upload_limit() {
            if (++calls === 1) {
                throw new Error("server unavailable");
            }
            return 1024;
        },
    });
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    const documentService = getService("document.document");
    await expect(documentService.getMaxUploadSize()).rejects.toThrow();
    await expect(documentService.getMaxUploadSize()).resolves.toBe(1024);
    await expect(documentService.getMaxUploadSize()).resolves.toBe(1024);
    expect(calls).toBe(2);
});

test("Uploading with no upload cap accepts the file", async () => {
    // the server answers null for an unlimited cap (max_fileupload_size=0);
    // an onRpc handler answering null falls through to the mock model, so the
    // model itself answers it
    patchWithCleanup(DocumentsModels.DocumentsDocument.prototype, {
        get_document_max_upload_limit() {
            expect.step("cap: null");
            return null;
        },
    });
    mockService("file_upload", {
        bus: new EventBus(),
        upload: (route) => {
            if (route.startsWith("/documents/upload")) {
                expect.step("doc uploaded");
            }
        },
    });
    const serverData = getDocumentsTestServerModelsData();
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains("button.btn.btn-primary.o-dropdown:contains('New')").click();
    await contains("button.btn.btn-link.o_documents_kanban_upload").click();
    await contains("input.o_input_file.o_hidden", {
        visible: false,
    }).click();
    await animationFrame();
    await setInputFiles([
        new File(["fake_file"], "fake_file.tiff", { type: "text/plain" }),
    ]);
    await animationFrame();

    expect.verifySteps(["cap: null", "doc uploaded"]);
});

test("Download button availability", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { folder_id: 1 }),
        makeDocumentRecordData(3, "Binary", { attachment_id: 1, folder_id: 1 }),
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "binary" }];
    const { name: folder1Name } = serverData["document.document"][0];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(`.o_kanban_record:contains(${folder1Name})`).click({
        ctrlKey: true,
    });
    await waitFor(".o_control_panel_actions:contains('Download')");

    await contains(`.o_kanban_record:contains(${folder1Name})`).click({
        ctrlKey: true,
    });
    await contains(".o_kanban_record:contains('Request')").click();
    await waitForNone(".o_control_panel_actions:contains('Download')");

    await contains(".o_kanban_record:contains('Binary')").click();
    await waitFor(".o_control_panel_actions:contains('Download')");
    await contains(`.o_kanban_record:contains(${folder1Name})`).click({
        ctrlKey: true,
    });
    await waitFor(".o_control_panel_actions:contains('Download')");

    await contains(".o_kanban_record:contains('Request')").click({ ctrlKey: true });
    await waitFor(".o_control_panel_actions:contains('Download')");
});

test("Drag and Drop - Search panel expand folders", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Sub Folder", { folder_id: 1, type: "folder" }),
        makeDocumentRecordData(3, "Test Folder", { type: "folder" }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const searchPanelSelector =
        ".o_search_panel_category_value .o_search_panel_label_title";
    expect(queryAllTexts(searchPanelSelector)).toEqual([
        "All",
        "Company",
        "My Drive",
        "Shared with me",
        "Recent",
        "Trash",
    ]);
    const { cancel, moveTo } = await contains(
        ".o_kanban_record[data-value-id='3']",
    ).drag();
    await moveTo(
        ".o_search_panel_category_value[data-value-id='COMPANY'] div.o_search_panel_label",
    );
    expect(queryAllTexts(searchPanelSelector)).toEqual([
        "All",
        "Company",
        "Folder 1",
        "Test Folder",
        "My Drive",
        "Shared with me",
        "Recent",
        "Trash",
    ]);
    await moveTo(
        ".o_search_panel_category_value[data-value-id='1'] div.o_search_panel_label",
    );
    expect(queryAllTexts(searchPanelSelector)).toEqual([
        "All",
        "Company",
        "Folder 1",
        "Sub Folder",
        "Test Folder",
        "My Drive",
        "Shared with me",
        "Recent",
        "Trash",
    ]);
    await cancel();

    expect(queryAll(".o_record_temporary", { root: document.body })).toHaveCount(0, {
        message: "temporary cards should have been cleaned up",
    });
});

test("Drag and Drop - A folder into itself or its children", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Sub Folder", { folder_id: 1, type: "folder" }),
        makeDocumentRecordData(3, "Folder 2", { type: "folder" }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const folder1 = ".o_kanban_record[data-value-id='1']";
    const folder2 = ".o_kanban_record[data-value-id='2']";
    const folder3 = ".o_kanban_record[data-value-id='3']";

    const { cancel, moveTo } = await contains(folder1).drag();
    await moveTo(folder2);
    expect(folder2).toHaveClass("o_drag_invalid");
    expect(".o_documents_dnd_text").toHaveText(
        "You cannot move a folder into itself or a children.",
    );
    await moveTo(folder3);
    expect(folder3).toHaveClass("o_drag_hover");
    expect(".o_documents_dnd_text").toHaveText("Folder 1");
    await moveTo(folder1);
    expect(folder1).toHaveClass("o_drag_invalid");
    expect(".o_documents_dnd_text").toHaveText(
        "You cannot move a folder into itself or a children.",
    );
    await cancel();
});

test("Drag and Drop - After selecting multiple documents", async function () {
    const serverData = getDocumentsTestServerModelsData(
        [1, 2, 3].map((idx) =>
            makeDocumentRecordData(idx + 1, `Test Document ${idx}`, { folder_id: 1 }),
        ),
    );
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const document2 = ".o_kanban_record[data-value-id='2']";
    const document4 = ".o_kanban_record[data-value-id='4']";

    await contains(document2).click({ ctrlKey: true });
    await contains(document4).click({ ctrlKey: true });

    let { cancel } = await contains(document2).drag();
    expect(document2).toHaveStyle({ opacity: "0.3" });
    expect(document4).toHaveStyle({ opacity: "0.3" });
    expect(".o_documents_dnd_text").toHaveText("Test Document 1");
    await cancel();

    ({ cancel } = await contains(document4).drag());
    expect(document2).toHaveStyle({ opacity: "0.3" });
    expect(document4).toHaveStyle({ opacity: "0.3" });
    expect(".o_documents_dnd_text").toHaveText("Test Document 3");
    await cancel();
});

test("Drag and Drop - Check permission when dropping documents", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Test Document 1"),
        // what the server computes for a viewer who does not own it
        makeDocumentRecordData(3, "Test Document 2", {
            user_permission: "view",
            user_can_move: false,
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    let { drop, moveTo } = await contains(".o_kanban_record[data-value-id='2']").drag();
    await moveTo(".o_kanban_record[data-value-id='1']");
    await drop();
    await waitFor(".o_notification");
    expect(".o_notification_content:eq(-1)").toHaveText("The document has been moved.");

    ({ drop, moveTo } = await contains(".o_kanban_record[data-value-id='3']").drag());
    await moveTo(".o_kanban_record[data-value-id='1']");
    await drop();
    await waitFor(".o_notification");
    expect(".o_notification_content:eq(-1)").toHaveText(
        "At least one document could not be moved due to access rights.",
    );
});

test("Drag and Drop - Check access rights confirmation popup when moving from kanban view", async function () {
    // every move is first sent checked: the server refuses one changing access
    onRpc("document.document", "write", ({ args, kwargs }) => {
        const checked = kwargs.context?.[MOVE_ACCESS_CHECK] ? " checked" : "";
        expect.step(`move ${args[0][0]} ${args[1].user_folder_id}${checked}`);
    });
    const documents = [
        [2, "Internal Viewer - Link None - Discoverable", "view", "none", false],
        [3, "Internal Editor - Link None - Discoverable", "edit", "none", false],
        [4, "Internal Viewer - Link Viewer - Discoverable", "view", "view", false],
        [5, "Internal Viewer - Link None - Must have link", "view", "none", true],
        [6, "Internal Viewer - Link Viewer - Must have link", "view", "view", true],
    ];
    const serverData = getDocumentsTestServerModelsData(
        documents.map(
            ([id, name, access_internal, access_via_link, is_access_via_link_hidden]) =>
                makeDocumentRecordData(id, name, {
                    access_internal,
                    access_via_link,
                    is_access_via_link_hidden,
                    type: "folder",
                }),
        ),
    );
    // 4 -> 6 differ only in discoverability, which a move never changes
    const cases = [
        [2, 3, true],
        [2, 4, true],
        [2, 5, false],
        [4, 6, false],
    ];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    for (const [docToMove, targetDoc, expectedConfirmation] of cases) {
        const { drop, moveTo } = await contains(
            `.o_kanban_record[data-value-id='${docToMove}']`,
        ).drag();
        await moveTo(`.o_kanban_record[data-value-id='${targetDoc}']`);
        await drop();
        if (expectedConfirmation) {
            await waitFor(".o_dialog:not(.o_inactive_modal)");
            expect(".o_dialog:not(.o_inactive_modal)").toHaveCount(1);
            await click(
                ".o_dialog:not(.o_inactive_modal) .modal-footer button:contains(Cancel)",
            );
            await animationFrame();
            expect(".o_dialog:not(.o_inactive_modal)").toHaveCount(0);
        } else {
            await animationFrame();
        }
        expect.verifySteps([`move ${docToMove} ${targetDoc} checked`]);
    }
});

test("Drag and Drop - Check access rights confirmation popup when moving from search panel", async function () {
    // stepped, then left to the mock server, which refuses a checked move
    // changing access
    onRpc("action_move_folder", ({ args, kwargs }) => {
        const checked = kwargs.context?.[MOVE_ACCESS_CHECK] ? "_checked" : "";
        expect.step(`action_move_folder_${args[0][0]}_${args[1]}${checked}`);
        expect(typeof args[1]).toBe("string");
    });
    const documents = [
        [2, "Internal Viewer - Link None - Discoverable", "view", "none", false],
        [3, "Internal Editor - Link None - Discoverable", "edit", "none", false],
        [4, "Internal Viewer - Link Viewer - Discoverable", "view", "view", false],
        [5, "Internal Viewer - Link None - Must have link", "view", "none", true],
        [6, "Internal Viewer - Link Viewer - Must have link", "view", "view", true],
    ];
    const labelByCode = { none: "None", view: "Viewer", edit: "Editor" };
    const nestedFolder = makeDocumentRecordData(7, "Nested in folder 2", {
        access_internal: "view",
        access_via_link: "none",
        is_access_via_link_hidden: false,
        type: "folder",
        user_folder_id: "2",
    });
    const serverData = getDocumentsTestServerModelsData(
        documents
            .map(
                ([
                    id,
                    name,
                    access_internal,
                    access_via_link,
                    is_access_via_link_hidden,
                ]) =>
                    makeDocumentRecordData(id, name, {
                        access_internal,
                        access_via_link,
                        is_access_via_link_hidden,
                        type: "folder",
                    }),
            )
            .concat(nestedFolder),
    );
    // 4 -> 6 differ only in discoverability, which a move never changes
    const cases = [
        [2, 3, true],
        [2, 4, true],
        [2, 5, false],
        [4, 6, false],
    ];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await click(
        ".o_search_panel_category_value[data-value-id='COMPANY'] .o_toggle_fold",
    );
    await animationFrame();

    for (const [docToMove, targetDoc, expectedConfirmation] of cases) {
        const { drop, moveTo } = await contains(
            `.o_search_panel_category_value[data-value-id='${docToMove}']`,
        ).drag();
        const targetFolder = document.querySelector(
            `.o_search_panel_category_value[data-value-id='${targetDoc}']`,
        );
        await moveTo(targetFolder);
        await moveTo(targetFolder, {
            position: { y: targetFolder.offsetHeight },
            relative: true,
        });
        await moveTo(targetFolder, {
            position: { x: targetFolder.offsetWidth },
            relative: true,
        });
        await drop();
        await animationFrame();
        if (expectedConfirmation) {
            await waitFor(".o_dialog:not(.o_inactive_modal)");
            expect(".o_dialog:not(.o_inactive_modal)").toHaveCount(1);
            const movedFolder = documents.find((doc) => doc[0] === docToMove);
            const targetFolder = documents.find((doc) => doc[0] === targetDoc);
            // a row per setting the move changes, showing its new value
            for (const [index, row] of [
                [2, "access_internal"],
                [3, "access_via_link"],
            ]) {
                const selector = `[aria-labelledby="o_documents_access_update_confirmation_${row}"]`;
                if (movedFolder[index] === targetFolder[index]) {
                    expect(selector).toHaveCount(0);
                } else {
                    expect(selector).toHaveText(labelByCode[targetFolder[index]]);
                }
            }
            await contains(
                ".o_dialog:not(.o_inactive_modal) .modal-footer button:contains(Cancel)",
            ).click();
            expect.step(`confirm_${docToMove}_${targetDoc}`);
            await waitForNone(".o_dialog:not(.o_inactive_modal)");
        }
    }
    await click(".o_search_panel_category_value[data-value-id='2'] .o_toggle_fold");
    await animationFrame();
    const source = contains(".o_search_panel_category_value[data-value-id='7']");
    const { drop, moveTo } = await source.drag();
    const lastCompanyChild = document.querySelector(
        ".o_search_panel_category_value[data-value-id='6']",
    );
    await moveTo(lastCompanyChild);
    await moveTo(lastCompanyChild, {
        position: { y: lastCompanyChild.offsetHeight },
        relative: true,
    });
    await drop();
    await animationFrame();
    expect.verifySteps([
        "action_move_folder_2_3_checked",
        "confirm_2_3",
        "action_move_folder_2_4_checked",
        "confirm_2_4",
        "action_move_folder_2_5_checked",
        "action_move_folder_4_6_checked",
        "action_move_folder_7_COMPANY_checked",
    ]);
});

test("Drag and Drop - a drop moves what the server says may move, not every editable", async function () {
    // an editor's document on the company root: user_can_move keeps it to managers
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Company Root Doc", {
            user_permission: "edit",
            user_can_move: false,
        }),
    ]);
    onRpc("document.document", "write", () => {
        expect.step("write");
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const { drop, moveTo } = await contains(
        ".o_kanban_record[data-value-id='2']",
    ).drag();
    await moveTo(".o_kanban_record[data-value-id='1']");
    await drop();
    await waitFor(".o_notification");
    expect(".o_notification_content:eq(-1)").toHaveText(
        "At least one document could not be moved due to access rights.",
    );
    expect.verifySteps([]);
});

test("Drag and Drop - Drop multiple documents at once", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Test Document 1"),
        // what the server computes for a viewer who does not own it
        makeDocumentRecordData(3, "Test Document 2", {
            user_permission: "view",
            user_can_move: false,
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    await contains(".o_kanban_record[data-value-id='2']").click({ ctrlKey: true });
    await contains(".o_kanban_record[data-value-id='3']").click({ ctrlKey: true });

    const { drop, moveTo } = await contains(
        ".o_kanban_record[data-value-id='2']",
    ).drag();
    await moveTo(".o_kanban_record[data-value-id='1']");
    await drop();
    await waitFor(".o_notification");
    expect(queryAllTexts(".o_notification_content")).toEqual([
        "At least one document could not be moved due to access rights.",
        "The document has been moved.",
    ]);
});

test("Drag and Drop - Drop document while holding CTRL", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Test Document"),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const { drop, moveTo } = await contains(
        ".o_kanban_record[data-value-id='2']",
    ).drag();
    expect(".o_documents_dnd_modifier").not.toBeVisible();
    await keyDown("Control");
    expect(".o_documents_dnd_modifier").toBeVisible();
    await moveTo(
        ".o_search_panel_category_value[data-value-id='COMPANY'] div.o_search_panel_label",
    );
    await moveTo(
        ".o_search_panel_category_value[data-value-id='1'] div.o_search_panel_label",
    );
    expect(".o_documents_dnd_modifier").toBeVisible();
    await drop();
    await waitFor(".o_notification");
    expect(".o_notification_content:eq(-1)").toHaveText("A shortcut has been created.");
});

test("Lock action availability and check", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Binary", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    const folder = ".o_kanban_record[data-value-id='1']";

    await contains(folder).click({ ctrlKey: true });
    await contains(".o_cp_action_menus button").click();
    await waitForNone(".o-dropdown--menu .o-dropdown-item:contains('Lock')");

    await contains(".o_kanban_record:contains('Binary')").click();
    await contains(".o_cp_action_menus button").click();
    await contains(".o-dropdown--menu .o-dropdown-item:contains('Lock')").click();
    await waitFor(".o_kanban_record i.fa-lock");

    await contains(".o_cp_action_menus button").click();
    await contains(".o-dropdown--menu .o-dropdown-item:contains('Unlock')").click();
    expect(".modal").toHaveCount(0, {
        message: "one's own lock is lifted without asking",
    });
    await waitForNone(".o_kanban_record i.fa-lock");

    await contains(folder).click({ ctrlKey: true });
    await contains(".o_cp_action_menus button").click();
    await waitForNone(".o-dropdown--menu .o-dropdown-item:contains('Lock')");
});

for (const isManager of [false, true]) {
    test(`another user's lock: no Lock nor Unlock, unless a manager, who is warned (manager: ${isManager})`, async function () {
        patchWithCleanup(documentsMockUser, { isManager });
        const serverData = getDocumentsTestServerModelsData([
            makeDocumentRecordData(2, "Theirs", {
                folder_id: 1,
                user_permission: "edit",
                lock_uid: serverState.odoobotId,
            }),
        ]);
        await makeDocumentsMockEnv({ serverData });
        await mountDocumentsKanbanView();
        await contains(".o_kanban_record:contains('Theirs')").click();
        await contains(".o_cp_action_menus button").click();
        if (!isManager) {
            expect(".o-dropdown--menu .o-dropdown-item:contains('Lock')").toHaveCount(
                0,
            );
            return;
        }
        await contains(".o-dropdown--menu .o-dropdown-item:contains('Unlock')").click();
        expect(".modal-body").toHaveText(
            "This document is locked by OdooBot.\nAre you sure you want to unlock it?",
        );
    });
}

test("only show common available actions", async function () {
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountDocumentsKanbanView();

    await contains(`.o_kanban_record:contains('Request 1')`).click();
    await waitFor(".o_control_panel_actions:contains('Action 1')");

    await contains(`.o_kanban_record:contains('Request 2')`).click();
    await waitForNone(".o_control_panel_actions:contains('Action 1')");
    await waitFor(".o_control_panel_actions:contains('Action 2 only')");
    await waitFor(".o_control_panel_actions:contains('Action 2 and 3')");

    await contains(`.o_kanban_record:contains('Request 3')`).click({ ctrlKey: true });
    await waitForNone(".o_control_panel_actions:contains('Action 2 only')");
    await waitFor(".o_control_panel_actions:contains('Action 2 and 3')");
});

test("Thumbnail: webp thumbnail generation", async function () {
    onRpc("/documents/document/3/update_thumbnail", async (args) => {
        const { params } = await args.json();
        expect.step("thumbnail generated");
        expect(params.thumbnail.startsWith("/9j/")).toEqual(true);
        return true;
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Test Document", {
            thumbnail_status: "client_generated",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "image/webp",
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 2, name: "binary" }];
    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(documentsClientThumbnailService, {
        _getLoadedImage() {
            const img = new Image();
            const imagePromise = new Deferred();
            img.onload = () => imagePromise.resolve(img);
            img.src = "data:image/webp;base64," + mimetypeExamplesBase64.WEBP;
            return imagePromise;
        },
    });
    await mountDocumentsKanbanView();
    expect.verifySteps(["thumbnail generated"]);
});

test("Document Request Upload", async function () {
    mockService("file_upload", {
        upload: (route) => {
            if (route === "/documents/upload/accessToken") {
                expect.step("upload_done");
            }
        },
    });

    const serverData = getDocumentsTestServerModelsData([
        {
            folder_id: 1,
            id: 2,
            name: "Test Request",
            access_token: "accessToken",
        },
    ]);

    const archWithRequest = basicDocumentsKanbanArch.replace(
        '<field name="name"/>',
        '<field name="name"/>\n' +
            '<t t-set="isRequest" t-value="record.type.raw_value === \'binary\' and !record.attachment_id.raw_value"/>\n' +
            '<input t-if="isRequest" type="file" class="o_hidden o_kanban_replace_document"/>\n',
    );
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView({ arch: archWithRequest });

    const file = new File(["hello world"], "text.txt", { type: "text/plain" });
    await inputFiles("input.o_kanban_replace_document", [file]);
    await animationFrame();
    expect.verifySteps(["upload_done"]);
});

test("focus when selecting all - ctrl + a", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Test Document", { folder_id: 1 }),
        makeDocumentRecordData(3, "Test Document 2", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();

    await contains(".o_kanban_renderer").click();

    await keyDown(["Control", "a"]);
    await waitFor(".o_kanban_record[data-value-id='1']:focus");
    await waitFor(".o_selection_box");
    expect(".o_record_selected").toHaveCount(3);

    await keyDown(["Control", "a"]);
    await waitFor(".o_kanban_record[data-value-id='1']:focus");
    await waitFor(".o_searchview");
    expect(".o_record_selected").toHaveCount(0);

    await contains(".o_kanban_record[data-value-id='3']").click();
    await keyDown(["Control", "a"]);
    await waitFor(".o_kanban_record[data-value-id='3']:focus");

    await keyDown(["Control", "a"]);
    await waitFor(".o_kanban_record[data-value-id='3']:focus");
});

test.tags("desktop");
test("document selector: include archived checkbox should not be shown", async () => {
    await mountDocumentsKanbanView();

    await toggleSearchBarMenu();
    await contains(".o_filter_menu .dropdown-item").click();
    await waitFor(".o_tree_editor_condition");

    expect(".form-switch label:contains(Include archived)").not.toHaveCount();
});

test("Split PDF button availability", async function () {
    const serverData = getDocumentsTestServerModelsData([
        {
            attachment_id: 1,
            id: 2,
            name: "text_file.txt",
            user_permission: "edit",
            mimetype: "image/webp",
        },
        {
            attachment_id: 2,
            id: 3,
            name: "pdf1.pdf",
            user_permission: "view",
            mimetype: "application/pdf",
        },
        {
            attachment_id: 3,
            id: 4,
            name: "pdf2.pdf",
            user_permission: "edit",
            mimetype: "application/pdf",
        },
    ]);

    serverData["ir.attachment"] = [
        { id: 1, name: "text_file.txt", mimetype: "image/webp" },
        { id: 2, name: "pdf1.pdf", mimetype: "application/pdf" },
        { id: 3, name: "pdf2.pdf", mimetype: "application/pdf" },
    ];

    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        [["search", false]]: getEnrichedSearchArch(),
    };

    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(
        ".o_kanban_record:contains('text_file.txt') .o_record_selector",
    ).click();
    await contains(".o_dropdown_title").click();
    await waitForNone(".o-dropdown-item:contains('Split PDF')");

    await contains(
        ".o_kanban_record:contains('text_file.txt') [name='document_preview']",
    ).click();
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitForNone(".o-dropdown-item:contains('Split PDF')");
    await press("escape");
    await waitForNone(".o-FileViewer");

    await contains(".o_kanban_record:contains('pdf1.pdf') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await waitForNone(".o-dropdown-item:contains('Split PDF')");

    await contains(
        ".o_kanban_record:contains('pdf1.pdf') [name='document_preview']",
    ).click();
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitForNone(".o-dropdown-item:contains('Split PDF')");
    await press("escape");
    await waitForNone(".o-FileViewer");

    await contains(".o_kanban_record:contains('pdf2.pdf') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await waitFor(".o-dropdown-item:contains('Split PDF')");

    await contains(
        ".o_kanban_record:contains('pdf2.pdf') [name='document_preview']",
    ).click();
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitFor(".o-dropdown-item:contains('Split PDF')");
});

test("Export action is not available in file viewer ", async function () {
    const serverData = getDocumentsTestServerModelsData([
        {
            folder_id: 1,
            id: 2,
            url: "https://youtu.be/Ayab6wZ_U1A",
            type: "url",
        },
    ]);

    const archWithURL = basicDocumentsKanbanArch.replace(
        '<field name="name"/>',
        '<field name="name"/>\n' + '<field name="url"/>',
    );

    DocumentsModels.DocumentsDocument._views = {
        kanban: archWithURL,
        [["search", false]]: getEnrichedSearchArch(),
    };

    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(
        ".o_kanban_record:contains('https://youtu.be/Ayab6wZ_U1A') .o_record_selector",
    ).click();
    await contains(".o_dropdown_title").click();
    await waitFor(".o-dropdown-item:contains('Export')");

    await contains(
        ".o_kanban_record:contains('https://youtu.be/Ayab6wZ_U1A') [name='document_preview']",
    ).click();
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitForNone(".o-dropdown-item:contains('Export')");
});

test("Control panel cog menu visibility", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { folder_id: 1 }),
    ]);
    const { name: folder1Name } = serverData["document.document"][0];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await waitFor(".o_kanban_renderer");

    await contains(".o_search_panel_label_title:contains('Company')").click();
    await waitFor(".o_last_breadcrumb_item:contains('Company')");
    expect(".o_cp_action_menus").toHaveCount(1, {
        message: "a root keeps the view's cog: a lone crumb is still a crumb",
    });
    await contains(`.o_kanban_record:contains('${folder1Name}')`).click();
    await waitFor(`.o_last_breadcrumb_item:contains('${folder1Name}')`);
    expect(`.o_cp_action_menus`).toHaveCount(1);
    await contains(".o_kanban_record:contains('Request') .o_record_selector").click({
        ctrlKey: true,
    });
    await animationFrame();
    expect(".o_control_panel .o_cog_menu_toggler").toHaveCount(0, {
        message: "a selection has its own actions: the cog steps aside, as web's",
    });
});

test("Select a range with SHIFT key", async () => {
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountDocumentsKanbanView();
    const { name: folder1Name } = embeddedActionsServerData["document.document"][0];
    await contains(
        `.o_kanban_record:contains(${folder1Name}) .o_record_selector`,
    ).click({
        ctrlKey: true,
    });
    await keyDown("Shift");
    await contains(".o_kanban_record:contains(Request 2)").click();
    expect(".o_kanban_record:contains(Request 1)").toHaveClass("o_record_selected");
    expect("div.o_record_selected").toHaveCount(3);
});

test("Select a range with SHIFT key, upwards", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
        makeDocumentRecordData(3, "Doc B", { folder_id: 1 }),
        makeDocumentRecordData(4, "Doc C", { folder_id: 1 }),
    ]);
    onRpc("/documents/touch/accessTokenFolder1", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_kanban_record:contains(Doc C)").click();
    expect(".o_kanban_record.o_record_selected").toHaveCount(1);
    await contains(".o_kanban_record:contains(Doc A)").click({ shiftKey: true });
    expect(".o_kanban_record.o_record_selected").toHaveCount(3);
    for (const name of ["Doc A", "Doc B", "Doc C"]) {
        expect(`.o_kanban_record:contains(${name})`).toHaveClass("o_record_selected");
    }
});

test("The kanban view mounts in debug mode", async () => {
    patchWithCleanup(odoo, { debug: "1" });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
    ]);
    onRpc("/documents/touch/accessTokenFolder1", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    expect(".o_kanban_record:contains(Doc A)").toHaveCount(1);
});

test("The search panel spins on the folder an upload targets", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
    ]);
    onRpc("/documents/touch/accessTokenFolder1", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_has_treeEntry .o_toggle_fold").click();
    expect(".o_search_panel_category_value.o_treeEntry:contains(Folder 1)").toHaveCount(
        1,
    );
    expect(".o_search_panel_category_value .fa-circle-notch").toHaveCount(0);
    const fileUpload = getService("file_upload");
    const uploaded = new Deferred();
    patchWithCleanup(fileUpload, {
        async upload(_route, _files, options) {
            const upload = { id: 1, data: new FormData(), state: "loading" };
            options?.buildFormData?.(upload.data);
            fileUpload.uploads[upload.id] = upload;
            uploaded.resolve();
            return upload;
        },
    });
    getService("document.document").uploadDocument(
        [new File(["x"], "x.txt")],
        "accessTokenFolder1",
        {},
        { targetFolderId: 1 },
    );
    await uploaded;
    await animationFrame();
    expect(
        ".o_search_panel_category_value.o_treeEntry:contains(Folder 1) .fa-circle-notch",
    ).toHaveCount(1);
});

test("Name in previewer is correct without attachment", async function () {
    const serverData = getDocumentsTestServerModelsData([
        {
            id: 10,
            name: "Shin chan: The Spicy Kasukabe",
            type: "url",
            url: "https://www.youtube.com/watch?v=Qv_-R9kw5eg",
            mimetype: "text/html",
            folder_id: 1,
        },
        {
            id: 11,
            name: "Mom vs Dad |Shinchan",
            type: "url",
            url: "https://www.youtube.com/watch?v=sZeU-nrm8UA",
            mimetype: "text/html",
            folder_id: 1,
        },
    ]);

    patchWithCleanup(HTMLIFrameElement.prototype, {
        contentWindow: {
            get: () => null,
        },
        contentDocument: {
            get: () => null,
        },
    });

    const previewedAttachments = [];
    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(getService("document.document"), {
        setPreviewedDocument(file) {
            if (file) {
                previewedAttachments.push({ id: file.id, name: file.name });
                expect.step(`preview_${file.name}`);
            }
            return super.setPreviewedDocument(...arguments);
        },
    });
    await mountDocumentsKanbanView();

    await contains(
        ".o_kanban_record:contains('Shin chan') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");

    const closeBtn = document.querySelector(".o-FileViewer [aria-label='Close']");
    closeBtn.click();
    await waitForNone(".o-FileViewer");

    await contains(
        ".o_kanban_record:contains('Mom vs Dad') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");

    expect(previewedAttachments).toHaveLength(2);

    expect(previewedAttachments).toEqual([
        { id: 10, name: "Shin chan: The Spicy Kasukabe" },
        { id: 11, name: "Mom vs Dad |Shinchan" },
    ]);

    expect.verifySteps([
        "preview_Shin chan: The Spicy Kasukabe",
        "preview_Mom vs Dad |Shinchan",
    ]);
});

test("Check actions with preview", async function () {
    const serverData = getDocumentsTestServerModelsData([
        {
            attachment_id: 1,
            id: 2,
            name: "Test_file.txt",
            mimetype: "image/webp",
        },
    ]);

    serverData["ir.attachment"] = [
        { id: 1, name: "Test_file.txt", mimetype: "image/webp" },
    ];

    const basicDocumentsKanbanArchWithLockUid = basicDocumentsKanbanArch.replace(
        '<field name="name"/>',
        '<field name="name"/>\n<field name="lock_uid"/>',
    );
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView({ arch: basicDocumentsKanbanArchWithLockUid });

    await contains(
        ".o_kanban_record:contains('Test_file.txt') [name='document_preview']",
    ).click();
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitFor(".o-dropdown-item:contains('Lock')");
    await contains(".o-dropdown-item:contains('Lock')").click();

    // a lock reloads that document only: the preview stays on it
    expect(".o-FileViewer").toHaveCount(1);
    await contains(".o-FileViewer .o_cp_action_menus .o-dropdown").click();
    await waitFor(".o-dropdown-item:contains('Unlock')");
});

test("Ensure previewer shows correct name after renaming a document", async function () {
    const serverData = getDocumentsTestServerModelsData([
        {
            attachment_id: 1,
            id: 2,
            name: "text_file.txt",
            mimetype: "image/webp",
        },
    ]);

    DocumentsModels["DocumentsDocument"]._views = {
        kanban: basicDocumentsKanbanArch,
        search: getEnrichedSearchArch(),
        form: "<form><field name='name'/></form>",
    };

    serverData["ir.attachment"] = [
        { id: 1, name: "text_file.txt", mimetype: "image/webp" },
    ];

    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        res_model: "document.document",
        type: "ir.actions.act_window",
        views: [[false, "kanban"]],
    });

    await contains(".o_kanban_record:contains('text_file.txt')").click({
        ctrlKey: true,
    });
    await contains(".o_control_panel_actions button:contains('Action')").click();
    await contains(".o-dropdown-item:contains('Rename')").click();
    await contains(".o_input").edit("test1.txt");
    await contains(".o_form_button_save:contains('Save')").click();
    expect(".o_kanban_record span:contains('test1.txt')").toHaveCount(1);
    await contains(
        ".o_kanban_record:contains('test1.txt') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");
    expect(".o-FileViewer-header span:contains('test1.txt')").toHaveCount(1);
});

test("Select all (Ctrl+A) in an empty folder does not crash", async function () {
    onRpc("/documents/touch/<access_token>", () => ({}));
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Empty Folder", {
            type: "folder",
            user_permission: "edit",
        }),
        makeDocumentRecordData(3, "In Folder 1", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(
        `.o_search_panel_label[data-tooltip="Company"] .o_toggle_fold`,
    ).click();

    await contains(`.o_search_panel_label[data-tooltip="Folder 1"] div`).click();
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(1);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_kanban_record.o_record_selected").toHaveCount(1);
    expect(".o_kanban_record[data-value-id='3']").toBeFocused();

    await contains(`.o_search_panel_label[data-tooltip="Empty Folder"] div`).click();
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(0);
    expect(".o_kanban_renderer").toHaveCount(1);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_error_dialog").toHaveCount(0);
    expect(".o_kanban_record.o_record_selected").toHaveCount(0);

    await contains(`.o_search_panel_label[data-tooltip="My Drive"] div`).click();
    expect(".o_kanban_record:not(.o_kanban_ghost)").toHaveCount(0);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_error_dialog").toHaveCount(0);
});

test("the cog menu's star follows the folder, and a cancelled trash reloads nothing", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
    ]);
    serverData["document.document"][0].user_permission = "edit";
    serverData["document.document"][0].user_folder_id = "MY";
    serverData["document.document"][0].owner_id = serverState.userId;
    onRpc("/documents/touch/*", () => ({}));
    onRpc("document.document", "action_toggle_user_favorite", ({ args }) => {
        expect.step(`toggle favorite ${args[0]}`);
        return true;
    });
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    expect.verifySteps(["reload"]);
    await contains(".o_kanban_record:contains('Folder 1')").click();
    await waitFor(".o_last_breadcrumb_item:contains('Folder 1')");
    expect.verifySteps(["reload"]);

    await contains(
        ".o_cp_action_menus .o_cog_menu_toggler, .o_cp_action_menus button",
    ).click();
    await contains(".o-dropdown-item:contains('Add Star')").click();
    await animationFrame();
    expect.verifySteps(["toggle favorite 1", "reload"]);

    await contains(
        ".o_cp_action_menus .o_cog_menu_toggler, .o_cp_action_menus button",
    ).click();
    await contains(".o-dropdown-item:contains('Move to Trash')").click();
    await contains(".modal .btn-secondary:contains('Discard')").click();
    await animationFrame();
    expect.verifySteps([]);
});

test("a folder the user may only view is starred from the cog all the same", async function () {
    const serverData = getDocumentsTestServerModelsData([]);
    serverData["document.document"][0].user_permission = "view";
    onRpc("/documents/touch/*", () => ({}));
    onRpc("document.document", "action_toggle_user_favorite", ({ args }) => {
        expect.step(`toggle favorite ${args[0]}`);
        return true;
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_kanban_record:contains('Folder 1')").click();
    await waitFor(".o_last_breadcrumb_item:contains('Folder 1')");
    await contains(
        ".o_cp_action_menus .o_cog_menu_toggler, .o_cp_action_menus button",
    ).click();
    await contains(".o-dropdown-item:contains('Add Star')").click();
    await animationFrame();
    expect.verifySteps(["toggle favorite 1"]);
});

test("the open folder's details count its documents' bytes, not rounded megabytes", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Big", { folder_id: 1, file_size: 1234567 }),
        makeDocumentRecordData(3, "Tiny", { folder_id: 1, file_size: 1 }),
    ]);
    onRpc("/documents/touch/*", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_kanban_record:contains('Folder 1')").click();
    await waitFor(".o_last_breadcrumb_item:contains('Folder 1')");
    const { focusedRecord } = getService("document.document");
    expect(focusedRecord.isContainer).toBe(true);
    expect(focusedRecord.data.file_size).toBe(1234568);
});

test("files dragged over a card keep the drop zone; leaving the view clears it", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: false }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    const view = queryOne(".o_kanban_renderer");
    const card = queryOne(".o_kanban_record:contains('Doc A')");
    const files = () => {
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(new File(["x"], "x.txt"));
        return dataTransfer;
    };
    view.dispatchEvent(
        new DragEvent("dragover", {
            bubbles: true,
            cancelable: true,
            dataTransfer: files(),
        }),
    );
    await animationFrame();
    const overClasses = () =>
        [...view.classList].filter((name) => name.startsWith("o_documents_drop_over"));
    expect(overClasses()).toHaveLength(1);
    view.dispatchEvent(
        new DragEvent("dragleave", {
            bubbles: true,
            relatedTarget: card,
            dataTransfer: files(),
        }),
    );
    await animationFrame();
    expect(overClasses()).toHaveLength(1, {
        message: "from the view onto one of its cards: still over the view",
    });
    view.dispatchEvent(
        new DragEvent("dragleave", {
            bubbles: true,
            relatedTarget: null,
            dataTransfer: files(),
        }),
    );
    await animationFrame();
    expect(overClasses()).toHaveLength(0);
});

test("another feature's upload does not reload the documents", async () => {
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    await mountDocumentsKanbanView();
    expect.verifySteps(["reload"]);
    const fileUpload = getService("file_upload");
    const loaded = (data) =>
        fileUpload.bus.trigger("FILE_UPLOAD_LOADED", {
            upload: {
                data,
                response: ["https://traceback.url"],
            },
        });
    loaded(new FormData());
    await animationFrame();
    expect.verifySteps([]);

    const documentData = new FormData();
    documentData.append(DOCUMENT_UPLOAD_MARKER, "1");
    loaded(documentData);
    await runAllTimers();
    await animationFrame();
    expect.verifySteps(["reload"]);
});

test("uploads finishing together reload once and leave all their documents selected", async () => {
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    onRpc("/documents/touch/*", () => ({}));
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Cloud One", { folder_id: 1 }),
        makeDocumentRecordData(3, "Cloud Two", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    expect.verifySteps(["reload"]);
    const fileUpload = getService("file_upload");
    for (const id of [2, 3]) {
        const data = new FormData();
        data.append(DOCUMENT_UPLOAD_MARKER, "1");
        fileUpload.bus.trigger("FILE_UPLOAD_LOADED", {
            upload: { data, response: { document_ids: [id] } },
        });
    }
    await runAllTimers();
    await animationFrame();
    expect.verifySteps(["reload"]);
    expect(".o_kanban_record.o_record_selected").toHaveCount(2);
});

test("a shift-click toward a selected card selects the whole range", async () => {
    const names = ["Doc A", "Doc B", "Doc C", "Doc D", "Doc E"];
    const serverData = getDocumentsTestServerModelsData(
        names.map((name, i) => makeDocumentRecordData(10 + i, name, { folder_id: 1 })),
    );
    onRpc("/documents/touch/accessTokenFolder1", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    const cards = queryAll(".o_kanban_record:not(.o_kanban_ghost)");
    const [first, , , , last] = cards;
    await contains(last).click();
    await contains(first).click({ shiftKey: true });
    expect(".o_kanban_record.o_record_selected").toHaveCount(5, {
        message: "the anchor stays selected, and so does everything between",
    });
});

test("the empty-folder help follows the folder shown", async () => {
    const serverData = getDocumentsTestServerModelsData([]);
    onRpc("/documents/touch/*", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView({ noContentHelp: markup`<p>Upload something</p>` });
    await contains(`.o_search_panel_label[data-tooltip="My Drive"] div`).click();
    await waitFor(".o_view_nocontent:contains('Your personal space')");
    await contains(`.o_search_panel_label[data-tooltip="Trash"] div`).click();
    await animationFrame();
    expect(".o_view_nocontent").toHaveText(
        /Documents moved to trash will show up here/,
    );
});

test("a drop on a folder's caret after hovering a refused folder moves the document", async () => {
    onRpc("document.document", "write", ({ args }) => {
        expect.step(`move ${args[0]} ${args[1].user_folder_id}`);
    });
    onRpc("/documents/touch/*", () => ({}));
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Dragged Doc", { user_permission: "edit" }),
        makeDocumentRecordData(3, "Child Folder", {
            type: "folder",
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await click(
        ".o_search_panel_category_value[data-value-id='COMPANY'] .o_toggle_fold",
    );
    await animationFrame();
    const { drop, moveTo } = await contains(
        ".o_kanban_record[data-value-id='2']",
    ).drag();
    await moveTo(
        ".o_search_panel_category_value[data-value-id='RECENT'] .o_search_panel_label_title",
    );
    await moveTo(".o_search_panel_category_value[data-value-id='1'] .o_toggle_fold");
    await drop();
    await animationFrame();
    expect.verifySteps(["move 2 1"]);
});

test("a shortcut is previewed as the document it points to", async () => {
    onRpc("/documents/touch/*", () => ({}));
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(4, "photo.webp", {
            mimetype: "image/webp",
            attachment_id: 1,
        }),
        makeDocumentRecordData(5, "Shortcut to photo", {
            folder_id: 1,
            shortcut_document_id: 4,
        }),
    ]);
    serverData["ir.attachment"] = [
        { id: 1, name: "photo.webp", mimetype: "image/webp" },
    ];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(
        `.o_search_panel_label[data-tooltip="Company"] .o_toggle_fold`,
    ).click();
    await contains(`.o_search_panel_label[data-tooltip="Folder 1"] div`).click();
    await waitFor(".o_kanban_record:contains('Shortcut to photo')");
    expect(
        ".o_kanban_record:contains('Shortcut to photo') .oe_kanban_previewer",
    ).toHaveCount(1, {
        message: "the image it points to is previewable",
    });
});
