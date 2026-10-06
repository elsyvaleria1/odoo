import { isDownloadAllowed } from "@document/views/document_actions";
import { DocumentsSearchModel } from "@document/views/search/document_search_model";
import { describe, expect, test } from "@odoo/hoot";
import { press, queryAll, queryOne, waitFor, waitForNone } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineModels,
    getService,
    mockService,
    onRpc,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";
import { router } from "@web/core/browser/router";
import { user } from "@web/core/user";

import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { embeddedActionsServerData } from "./helpers/test_server_data.js";
import {
    basicDocumentsListArch,
    mountDocumentsListView,
} from "./helpers/views/list.js";

describe.current.tags("desktop");

defineModels(DocumentsModels);

/**
 * @return {`.o_documents_details_panel ${string}`}
 */
const dp = (selector) => `.o_documents_details_panel ${selector}`;

test("Open share with view user_permission", async function () {
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
    await mountDocumentsListView();
    await contains(
        `.o_data_row:contains(${folder1Name}) .o_list_record_selector`,
    ).click();
    await contains("button:contains(Share)").click();

    expect.verifySteps(["open_share"]);
});

test("Right panel shows and updates focused or container record only", async function () {
    onRpc("/documents/touch/<access_token>", () => ({}));

    const file2Id = 3;
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "File 1", { attachment_id: 1, folder_id: 1 }),
        makeDocumentRecordData(file2Id, "File 2", { attachment_id: 2, folder_id: 1 }),
        makeDocumentRecordData(4, "File 3", { attachment_id: 3, folder_id: 1 }),
    ]);
    serverData["ir.attachment"] = [
        { id: 1, name: "One" },
        { id: 2, name: "Two" },
        { id: 3, name: "Three" },
    ];
    const { name: folder1Name } = serverData["document.document"][0];
    onRpc("web_save", ({ args }) => {
        if (args[0].length === 1 && args[0][0] === file2Id) {
            expect.step("edit_request_2");
        }
    });
    onRpc("ir.model", "display_name_for", ({ args }) =>
        args[0].map((model) => ({ model, display_name: model })),
    );
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();

    await contains(".o_control_panel_navigation .o_documents_info_toggle").click();
    await waitFor(".documents_chatter_disabled_overlay");
    await contains(`.o_data_row td[name='name']:contains(${folder1Name})`).click();
    await animationFrame();
    expect(dp(".o_documents_details_panel_name input")).toHaveValue(folder1Name);
    await contains(`.o_list_renderer`).click();

    await waitFor(".documents_chatter_disabled_overlay");
    await contains(`.o_data_row:contains(${folder1Name}) .fa-folder`).click();
    await animationFrame();
    expect(`.o_data_row .o_list_record_selector`).toHaveCount(3);
    expect(dp(".o_documents_details_panel_name input")).toHaveValue(folder1Name);

    await contains(".o_data_row :contains('File 1')").click();
    expect(dp(".o_documents_details_panel_name input")).toHaveValue("File 1");
    await contains(`.o_list_renderer`).click();
    expect(dp(".o_documents_details_panel_name input")).toHaveValue(folder1Name);

    await contains(".o_data_row:contains('File 1') .o_list_record_selector").click();
    expect(dp(".o_documents_details_panel_name input")).toHaveValue("File 1");
    await contains(".o_data_row :contains('File 2')").click();
    expect(dp(".o_documents_details_panel_name input")).toHaveValue("File 2");
    await contains(dp(".o_documents_details_panel_name input")).edit("File 4");
    await waitFor(".o_data_row :contains('File 4')");
    await waitFor(".o_data_row :contains('File 1')");

    expect.verifySteps(["edit_request_2"]);
});

test("Document actions are hidden when focused record is not selected", async function () {
    onRpc("/documents/touch/<access_token>", () => ({}));
    onRpc("ir.model", "display_name_for", ({ args }) =>
        args[0].map((model) => ({ model, display_name: model })),
    );

    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "File 1", { attachment_id: 1, folder_id: 1 }),
        makeDocumentRecordData(3, "File 2", { attachment_id: 2, folder_id: 1 }),
    ]);
    serverData["ir.attachment"] = [
        { id: 1, name: "One" },
        { id: 2, name: "Two" },
    ];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    await contains(".o_data_row:contains('File 1') .o_list_record_selector").click();
    await waitFor(".o_control_panel_actions:contains('Download')");
    await contains(".o_data_row :contains('File 2')").click();
    await waitFor(".o_selection_container");
    await waitFor(".o_control_panel_actions:not(:contains('Download'))");
    await contains(".o_data_row:contains('File 2') .o_list_record_selector").click();
    await waitFor(".o_control_panel_actions:contains('Download')");
});

test("only show common available actions", async function () {
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountDocumentsListView();

    await contains(`.o_data_row:contains('Request 1') .o_list_record_selector`).click();
    await waitFor(".o_control_panel_actions:contains('Action 1')");
    await contains(`.o_data_row:contains('Request 1') .o_list_record_selector`).click();

    await contains(`.o_data_row:contains('Request 2') .o_list_record_selector`).click();
    await waitForNone(".o_control_panel_actions:contains('Action 1')");
    await waitFor(".o_control_panel_actions:contains('Action 2 only')");
    await waitFor(".o_control_panel_actions:contains('Action 2 and 3')");

    await contains(`.o_data_row:contains('Request 3') .o_list_record_selector`).click();
    await waitForNone(".o_control_panel_actions:contains('Action 2 only')");
    await waitFor(".o_control_panel_actions:contains('Action 2 and 3')");
});

test("Required document name", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Testing file", { folder_id: 1 }),
        makeDocumentRecordData(3, "Testing folder", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    const lr = (documentName, selector) =>
        `.o_data_row:contains('${documentName}') ${selector}`;
    for (const documentName of ["Testing folder", "Testing file"]) {
        await contains(lr(documentName, ".o_list_record_selector")).click();
        await contains(lr(documentName, ".o_data_cell[name='name']")).click();
        await expect(lr(documentName, ".o_data_cell[name='name'] input")).toHaveCount(
            1,
        );
        await expect(lr(documentName, ".o_data_cell[name='name'] input")).toHaveValue(
            documentName,
        );
        await contains(lr(documentName, ".o_data_cell[name='name'] input")).edit("");
        await animationFrame();
        expect(".o_notification").toHaveCount(1);
        expect(".o_notification").toHaveText("Name cannot be empty.");
        // closing the notification is a click outside the row: it leaves edit mode
        await contains(".o_notification .o_notification_close").click();
        await animationFrame();
        expect(lr(documentName, ".o_data_cell[name='name']")).toHaveText(documentName, {
            message: "the refused empty name gives the old one back",
        });
    }
});

test("documents list: don't unselect all when interacting with the headers", async () => {
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountDocumentsListView();

    await contains(".o_data_row:eq(0) .o_list_record_selector input").click();
    await contains(".o_data_row:eq(1) .o_list_record_selector input").click();

    expect(".o_data_row_selected").toHaveCount(2);

    await contains("th:eq(2) .o_resize", { visible: false }).dragAndDrop("th:eq(3)");

    expect(".o_data_row_selected").toHaveCount(2);
});

test("company_id field visibility for internal in multicompany", async function () {
    serverState.companies = [
        { id: 1, name: "Company 1", sequence: 1, parent_id: false, child_ids: [] },
        { id: 2, name: "Company 2", sequence: 2, parent_id: false, child_ids: [] },
    ];
    const serverData = getDocumentsTestServerModelsData();
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView({
        context: {
            allowed_company_ids: [1, 2],
        },
    });
    expect("thead th[data-name='company_id']").toHaveCount(1);
});

test("company_id field visibility for portal in multicompany", async function () {
    serverState.companies = [
        { id: 1, name: "Company 1", sequence: 1, parent_id: false, child_ids: [] },
        { id: 2, name: "Company 2", sequence: 2, parent_id: false, child_ids: [] },
    ];
    const testUserGroups = ["base.group_portal", "base.group_multi_company"];
    patchWithCleanup(user, {
        hasGroup: (group) => testUserGroups.includes(group),
        isInternalUser: false,
    });
    const serverData = getDocumentsTestServerModelsData();
    const currentUser = serverData["res.users"].find(
        (u) => u.id === serverState.userId,
    );
    Object.assign(currentUser, { group_ids: [], share: true });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView({
        context: {
            allowed_company_ids: [1, 2],
        },
    });
    expect("thead th[data-name='company_id']").toHaveCount(0);
});

test("file sharing via link with multiple subfolders", async function () {
    let accessFolder1 = false;
    let accessFolder2 = false;
    let addFolder4 = false;
    onRpc("/documents/touch/accessTokenFolder1", () => {
        expect.step("touch 1");
        accessFolder1 = true;
        return { reload: true };
    });
    onRpc("/documents/touch/accessTokenFolder2", () => {
        expect.step("touch 2");
        accessFolder2 = true;
        return { reload: true };
    });
    onRpc("/documents/touch/accessTokenFolder3", () => ({ reload: true }));
    onRpc("/documents/touch/accessTokenFolder4", () => ({ reload: true }));

    const folder2 = makeDocumentRecordData(2, "Folder 2", {
        type: "folder",
        is_folder: true,
        folder_id: 1,
        access_token: "accessTokenFolder2",
        active: false,
    });
    const folder3 = makeDocumentRecordData(3, "Folder 3", {
        type: "folder",
        is_folder: true,
        folder_id: 2,
        access_token: "accessTokenFolder3",
        active: false,
    });
    const folder4 = makeDocumentRecordData(4, "Folder 4", {
        type: "folder",
        is_folder: true,
        folder_id: 2,
        access_token: "accessTokenFolder4",
        active: false,
    });
    const serverData = getDocumentsTestServerModelsData([folder2, folder3, folder4]);

    const docEnv = await makeDocumentsMockEnv({ serverData });
    const activateFolders = () => {
        folder2.active = accessFolder1;
        folder3.active = accessFolder2;
        if (addFolder4) {
            folder4.active = accessFolder2;
            folder3.active = false;
        }
    };
    onRpc("search_panel_select_range", activateFolders);
    onRpc("web_search_read", activateFolders);

    const docService = docEnv.services["document.document"];
    patchWithCleanup(docService, {
        logAccess: (token) => docService._logAccess(token),
        focusRecord: () => false,
    });
    await mountDocumentsListView();

    await contains(
        `.o_search_panel_label[data-tooltip="Company"] .o_toggle_fold`,
    ).click();
    expect(`.o_data_row .o_field_cell[name="name"]:contains("Folder 1")`).toHaveCount(
        1,
    );
    await contains(`.o_data_row .o_field_cell .o_field_documents_type_icon`).click();
    expect(`.o_data_row .o_field_cell[name="name"]:contains("Folder 2")`).toHaveCount(
        1,
    );
    await contains(`.o_data_row .o_field_cell .o_field_documents_type_icon`).click();
    expect(`.o_data_row .o_field_cell[name="name"]:contains("Folder 3")`).toHaveCount(
        1,
    );
    await contains(`.o_data_row .o_field_cell .o_field_documents_type_icon`).click();

    expect.verifySteps(["touch 1", "touch 2"]);

    expect(`.o_search_panel_label[data-tooltip="Folder 4"]`).toHaveCount(0);
    addFolder4 = true;
    await contains(`.o_search_panel_label_title:contains("Folder 2")`).click();
    expect(`.o_search_panel_label[data-tooltip="Folder 4"]`).toHaveCount(0);
    expect(`.o_data_row .o_field_cell[name="name"]:contains("Folder 4")`).toHaveCount(
        1,
    );
    await contains(`.o_data_row .o_field_cell .o_field_documents_type_icon`).click();
    expect(`.o_search_panel_label[data-tooltip="Folder 4"]`).toHaveCount(1);
    expect.verifySteps(["touch 2"]);
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
    await mountDocumentsListView();
    await contains(
        `.o_search_panel_label[data-tooltip="Company"] .o_toggle_fold`,
    ).click();

    await contains(`.o_search_panel_label[data-tooltip="Folder 1"] div`).click();
    expect(".o_data_row").toHaveCount(1);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_data_row_selected").toHaveCount(1);

    await contains(`.o_search_panel_label[data-tooltip="Empty Folder"] div`).click();
    expect(".o_data_row").toHaveCount(0);
    expect(".o_list_renderer").toHaveCount(1);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_error_dialog").toHaveCount(0);
    expect(".o_data_row_selected").toHaveCount(0);

    await contains(`.o_search_panel_label[data-tooltip="My Drive"] div`).click();
    expect(".o_data_row").toHaveCount(0);
    await press(["control", "a"]);
    await animationFrame();
    expect(".o_error_dialog").toHaveCount(0);
});

test("clicking outside the list saves the edited name and leaves edit mode", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Testing file", { folder_id: 1 }),
    ]);
    onRpc("document.document", "web_save", ({ args }) => {
        expect.step(`save ${args[1].name}`);
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    const row = ".o_data_row:contains('Testing file')";
    await contains(`${row} .o_list_record_selector`).click();
    await contains(`${row} .o_data_cell[name='name']`).click();
    await contains(`${row} .o_data_cell[name='name'] input`).edit("Renamed file", {
        confirm: false,
    });

    await contains(".o_control_panel").click();
    await animationFrame();
    expect.verifySteps(["save Renamed file"]);
    expect(".o_data_row .o_data_cell[name='name'] input").toHaveCount(0, {
        message: "the row is back to readonly",
    });
});

test("isDownloadAllowed mirrors the server's download gate", () => {
    const cases = [
        [{}, true],
        [{ is_download_blocked: true, user_permission: "view" }, false],
        [{ is_download_blocked: true, user_permission: "edit" }, true],
        [
            {
                is_download_blocked: true,
                user_permission: "view",
                access_via_link: "edit",
            },
            true,
        ],
        [{ is_download_blocked: true, shortcut_document_id: { id: 9 } }, true],
    ];
    for (const [data, allowed] of cases) {
        expect(isDownloadAllowed(data)).toBe(allowed, {
            message: JSON.stringify(data),
        });
    }
});

test("a blocked document a viewer cannot download is not offered for duplication", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Blocked.pdf", {
            folder_id: 1,
            is_download_blocked: true,
            user_permission: "view",
            attachment_id: 1,
        }),
        makeDocumentRecordData(3, "Editable.pdf", {
            folder_id: 1,
            is_download_blocked: true,
            user_permission: "edit",
            attachment_id: 1,
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "x.pdf" }];
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();

    await contains(
        ".o_data_row:contains('Blocked.pdf') .o_list_record_selector",
    ).click();
    await contains(".o_cp_action_menus button").click();
    expect(".o-dropdown-item:contains('Duplicate')").toHaveCount(0);
    expect(".o_control_panel_actions button:contains('Download')").toHaveCount(0);

    await contains(
        ".o_data_row:contains('Blocked.pdf') .o_list_record_selector",
    ).click();
    await contains(
        ".o_data_row:contains('Editable.pdf') .o_list_record_selector",
    ).click();
    await contains(".o_cp_action_menus button").click();
    expect(".o-dropdown-item:contains('Duplicate')").toHaveCount(1, {
        message: "an editor downloads, so duplicates, a blocked document",
    });
    expect(".o_control_panel_actions button:contains('Download')").toHaveCount(1);
});

test("a row offers its document's actions as icons, and runs them", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Contract.pdf", {
            folder_id: 1,
            user_permission: "edit",
            attachment_id: 1,
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "Contract.pdf" }];
    serverData["document.document"][0].user_permission = "edit";
    onRpc("ir.model", "display_name_for", () => []);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView({
        arch: basicDocumentsListArch.replace(
            "</list>",
            '<widget name="documents_list_actions"/></list>',
        ),
    });
    const actionsOf = (name) =>
        queryAll(
            `.o_data_row:has(.o_data_cell[name='name']:contains('${name}')) .o_documents_list_actions i`,
        ).map((icon) => icon.dataset.action);
    expect(actionsOf("Folder 1")).toEqual([
        "share",
        "download",
        "rename",
        "details",
        "open",
    ]);
    expect(actionsOf("Contract.pdf")).toEqual([
        "share",
        "download",
        "rename",
        "details",
    ]);

    await contains(".o_data_row:contains('Contract.pdf') [data-action='details']", {
        visible: false,
    }).click();
    expect(getService("document.document").focusedRecord.resId).toBe(2);
    expect(getService("document.document").rightPanelReactive.visible).toBe(true);

    await contains(
        ".o_data_row:has(.o_data_cell[name='name']:contains('Folder 1')) [data-action='open']",
        { visible: false },
    ).click();
    await waitFor(".o_last_breadcrumb_item:contains('Folder 1')");
});

test("focusing the open folder again is the same focus", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
    ]);
    onRpc("/documents/touch/*", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    const documentService = getService("document.document");
    patchWithCleanup(documentService, {
        updateDocumentURL() {
            expect.step("url");
            return super.updateDocumentURL(...arguments);
        },
    });
    // mounting focused the folder already: clicking its empty area changes nothing
    await contains(".o_list_renderer").click();
    await contains(".o_list_renderer").click();
    expect.verifySteps([]);
});

test("Move to Trash is offered only when something would move", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Locked", {
            folder_id: 1,
            user_permission: "edit",
            lock_uid: serverState.userId,
        }),
        makeDocumentRecordData(3, "Unlocked", {
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    await contains(".o_data_row:contains('Locked') .o_list_record_selector").click();
    await contains(".o_cp_action_menus button").click();
    expect(".o-dropdown-item:contains('Move to Trash')").toHaveCount(0, {
        message: "a locked document is not trashed: nothing would move",
    });
    await contains(".o_data_row:contains('Unlocked') .o_list_record_selector").click();
    await contains(".o_cp_action_menus button").click();
    expect(".o-dropdown-item:contains('Move to Trash')").toHaveCount(1);
});

test("the folder tree is fetched without narrowing it to the open folder", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Doc A", { folder_id: 1 }),
    ]);
    let searchModel;
    patchWithCleanup(DocumentsSearchModel.prototype, {
        setup() {
            super.setup(...arguments);
            searchModel = this;
        },
    });
    onRpc("search_panel_select_range", ({ kwargs }) => {
        expect.step(JSON.stringify(kwargs.category_domain));
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    searchModel.toggleCategoryValue(searchModel.folderCategory.id, 1);
    expect(searchModel.getSelectedFolderId()).toBe(1);
    await searchModel._reloadSearchPanel();
    expect.verifySteps(["[]", "[]"]);
});

test("moving a row into a folder of the same access asks for no confirmation", async function () {
    const access = { access_internal: "view", access_via_link: "none" };
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Same Access Folder", {
            folder_id: 1,
            type: "folder",
            user_permission: "edit",
            ...access,
        }),
        makeDocumentRecordData(3, "Row Doc", {
            folder_id: 1,
            user_permission: "edit",
            ...access,
        }),
    ]);
    onRpc("document.document", "write", ({ args }) => {
        expect.step(`write ${args[1].user_folder_id}`);
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    const { drop, moveTo } = await contains(".o_data_row:contains('Row Doc')").drag();
    await moveTo(".o_data_row:contains('Same Access Folder')");
    await drop();
    await animationFrame();
    expect(".modal").toHaveCount(0);
    expect.verifySteps(["write 2"]);
});

test("an embedded action answering with a notification reloads the view once", async function () {
    onRpc("document.document", "action_execute_embedded_action", () => ({
        type: "ir.actions.client",
        tag: "display_notification",
        params: { message: "Done", type: "success" },
    }));
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountDocumentsListView();
    expect.verifySteps(["reload"]);
    await contains(".o_data_row:contains('Request 1') .o_list_record_selector").click();
    await contains(".o_control_panel_actions button:contains('Action 1')").click();
    await animationFrame();
    expect.verifySteps(["reload"]);
});

test("deleting from the trash reloads the view once", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Trashed Doc", {
            folder_id: 1,
            active: false,
            user_permission: "edit",
        }),
    ]);
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    onRpc("document.document", "unlink", ({ args }) => {
        expect.step(`unlink ${args[0]}`);
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    await contains(`.o_search_panel_label[data-tooltip="Trash"] div`).click();
    expect.verifySteps(["reload", "reload"]);
    await contains(
        ".o_data_row:contains('Trashed Doc') .o_list_record_selector",
    ).click();
    await press(["control", "d"]);
    await contains(".modal .btn-primary:contains('Delete permanently')").click();
    await animationFrame();
    expect.verifySteps(["unlink 2", "reload"]);
});

test("a discarded rename reloads nothing, a saved one reloads the view", async function () {
    patchWithCleanup(DocumentsModels.DocumentsDocument._views, {
        form: `<form>
            <field name="name"/>
            <footer>
                <button special="save" string="Rename" class="btn-primary"/>
                <button special="cancel" string="Discard" class="btn-secondary"/>
            </footer>
        </form>`,
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Old Name", {
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    expect.verifySteps(["reload"]);
    const rename = async () => {
        await contains(".o_data_row:contains('Name') .o_list_record_selector").click();
        await contains(".o_cp_action_menus button").click();
        await contains(".o-dropdown-item:contains('Rename')").click();
        await waitFor(".modal .o_form_view");
    };

    await rename();
    await contains(".modal .btn-secondary:contains('Discard')").click();
    await animationFrame();
    expect.verifySteps([]);

    await contains(".o_data_row:contains('Name') .o_list_record_selector").click();
    await rename();
    await contains(".modal .o_field_widget[name='name'] input").edit("New Name");
    await contains(".modal .btn-primary:contains('Rename')").click();
    await animationFrame();
    expect.verifySteps(["reload"]);
});

test("locking a document reloads that document only", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Lockable", {
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    onRpc("document.document", "toggle_lock", function ({ args }) {
        this.env["document.document"].write([args[0]], {
            lock_uid: serverState.userId,
        });
        expect.step("toggle_lock");
        return true;
    });
    onRpc("document.document", "web_search_read", () => {
        expect.step("reload");
    });
    onRpc("search_panel_select_range", () => {
        expect.step("folders");
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    expect.verifySteps(["folders", "reload"]);
    await contains(".o_data_row:contains('Lockable') .o_list_record_selector").click();
    await contains(".o_cp_action_menus button").click();
    await contains(".o-dropdown-item:contains('Lock')").click();
    await animationFrame();
    expect.verifySteps(["toggle_lock"]);
    await contains(".o_cp_action_menus button").click();
    expect(".o-dropdown-item:contains('Unlock')").toHaveCount(1, {
        message: "the record itself was reloaded",
    });
});

test("Alt+T stars the selected rows in list view too", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Star Me", { folder_id: 1 }),
        makeDocumentRecordData(3, "And Me", { folder_id: 1 }),
    ]);
    onRpc("document.document", "action_toggle_user_favorite", ({ args }) => {
        expect.step(`star ${args[0]}`);
        return true;
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    await contains(".o_data_row:contains('Star Me') .o_list_record_selector").click();
    await contains(".o_data_row:contains('And Me') .o_list_record_selector").click();
    await press(["alt", "t"]);
    await animationFrame();
    expect.verifySteps(["star 2,3"]);
});

test("a shortcut to a folder outside the panel does not open a trash it lacks", async function () {
    patchWithCleanup(user, {
        hasGroup: (group) => group === "base.group_portal",
        isInternalUser: false,
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(6, "Target Out Of View", {
            type: "folder",
            folder_id: 1,
            active: false,
        }),
        makeDocumentRecordData(5, "Dangling Shortcut", {
            type: "folder",
            folder_id: 1,
            shortcut_document_id: 6,
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    let searchModel;
    patchWithCleanup(DocumentsSearchModel.prototype, {
        setup() {
            super.setup(...arguments);
            searchModel = this;
        },
    });
    await mountDocumentsListView();
    expect(searchModel.getFolderById("TRASH")).toBe(false);
    const before = searchModel.getSelectedFolderId();
    await contains(
        ".o_search_panel_category_value[data-value-id='1'] .o_toggle_fold",
    ).click();
    await contains(".o_search_panel_label_title:contains('Dangling Shortcut')").click();
    expect(searchModel.getSelectedFolderId()).toBe(before);
    await waitFor(".o_notification");
});

test("a download with nothing to zip sends no request", async function () {
    onRpc("/documents/zip", () => {
        expect.step("zip");
        return "";
    });
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    // a domain selection of links and requests only
    await getService("document.document").downloadDocuments([], []);
    expect.verifySteps([]);
});

test("a portal user's URL keeps a token when the view shows All", async function () {
    patchWithCleanup(user, {
        hasGroup: (group) => group === "base.group_portal",
        isInternalUser: false,
    });
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    const pushed = [];
    patchWithCleanup(router, {
        pushState(state) {
            if ("access_token" in state) {
                pushed.push(state.access_token);
            }
            return super.pushState(...arguments);
        },
    });
    await mountDocumentsListView();
    await contains(".o_search_panel_label_title:contains('Folder 1')").click();
    await contains(
        ".o_search_panel_category_value:not([data-value-id]) .o_search_panel_label_title",
    ).click();
    expect(pushed.filter((token) => !token)).toEqual([], {
        message: "a bare /odoo/documents sends a portal user out of Documents",
    });
});

test("a folder starred in its row is starred in the menu once opened", async function () {
    onRpc("/documents/touch/*", () => ({}));
    onRpc("document.document", "action_toggle_user_favorite", function ({ args }) {
        for (const record of this.env["document.document"].browse(args[0])) {
            this.env["document.document"].write([record.id], {
                is_user_favorite: !record.is_user_favorite,
            });
        }
        return true;
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Star Folder", {
            type: "folder",
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    let searchModel;
    patchWithCleanup(DocumentsSearchModel.prototype, {
        setup() {
            super.setup(...arguments);
            searchModel = this;
        },
    });
    await mountDocumentsListView({
        arch: basicDocumentsListArch.replace(
            '<field name="name"',
            '<field name="is_user_favorite" widget="document_favorite"/><field name="name"',
        ),
    });
    await contains(
        `.o_search_panel_label[data-tooltip="Company"] .o_toggle_fold`,
    ).click();
    await contains(`.o_search_panel_label[data-tooltip="Folder 1"] div`).click();
    await contains(
        ".o_data_row:contains('Star Folder') .o_field_document_favorite a, .o_data_row:contains('Star Folder') [name='is_user_favorite'] a",
    ).click();
    await animationFrame();
    searchModel.toggleCategoryValue(searchModel.folderCategory.id, 3);
    await animationFrame();
    await contains(
        ".o_cp_action_menus .o_cog_menu_toggler, .o_cp_action_menus button",
    ).click();
    expect(".o-dropdown-item:contains('Remove Star')").toHaveCount(1);
});

test("the menu of a folder whose download is blocked offers no Download to a viewer", async function () {
    onRpc("/documents/touch/*", () => ({}));
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Blocked Folder", {
            type: "folder",
            folder_id: 1,
            user_permission: "view",
            is_download_blocked: true,
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    let searchModel;
    patchWithCleanup(DocumentsSearchModel.prototype, {
        setup() {
            super.setup(...arguments);
            searchModel = this;
        },
    });
    await mountDocumentsListView();
    searchModel.toggleCategoryValue(searchModel.folderCategory.id, 3);
    await animationFrame();
    await contains(
        ".o_cp_action_menus .o_cog_menu_toggler, .o_cp_action_menus button",
    ).click();
    expect(".o-dropdown-item:contains('Download')").toHaveCount(0);
});

test("Enter on a request row opens its file picker", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Awaited File", {
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView();
    const row = queryOne(".o_data_row:contains('Awaited File')");
    row.querySelector("input.o_input_file").addEventListener("click", (ev) => {
        ev.preventDefault();
        expect.step("file picker");
    });
    row.querySelector(".o_data_cell").dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
    );
    await animationFrame();
    expect.verifySteps(["file picker"]);
});

test("renaming a file from its row reloads that row only", async function () {
    patchWithCleanup(DocumentsModels.DocumentsDocument._views, {
        form: `<form>
            <field name="name"/>
            <footer><button special="save" string="Rename" class="btn-primary"/></footer>
        </form>`,
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Contract.pdf", {
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsListView({
        arch: basicDocumentsListArch.replace(
            "</list>",
            '<widget name="documents_list_actions"/></list>',
        ),
    });
    onRpc("document.document", "web_search_read", () => {
        expect.step("records");
    });
    onRpc("search_panel_select_range", () => {
        expect.step("folders");
    });
    onRpc("document.document", "web_read", () => {
        expect.step("row");
    });
    await contains(".o_data_row:contains('Contract.pdf') [data-action='rename']", {
        visible: false,
    }).click();
    await waitFor(".modal .o_form_view");
    expect.verifySteps(["row"]);
    await contains(".modal .o_field_widget[name='name'] input").edit("Signed.pdf");
    await contains(".modal .btn-primary:contains('Rename')").click();
    await animationFrame();
    expect.verifySteps(["row"]);
    expect(".o_data_row:contains('Signed.pdf')").toHaveCount(1);
});
