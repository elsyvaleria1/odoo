import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "@document/../tests/helpers/data";
import { makeDocumentsMockEnv } from "@document/../tests/helpers/model";
import { basicDocumentsOperationFormArch } from "@document/../tests/helpers/views/form";
import { basicDocumentsKanbanArch } from "@document/../tests/helpers/views/kanban";
import { basicDocumentsListArch } from "@document/../tests/helpers/views/list";
import { getEnrichedSearchArch } from "@document/../tests/helpers/views/search";
import { MOVE_ACCESS_CHECK } from "@document/core/document_service";
import {
    openDocumentsPicker,
    SelectAddDocumentCreateDialog,
} from "@document/views/view_dialogs/select_add_document_create_dialog";
import { composerActionsRegistry } from "@mail/core/common/composer_actions";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, press, waitFor } from "@odoo/hoot-dom";
import {
    contains,
    defineActions,
    defineModels,
    fields,
    getService,
    makeKwArgs,
    makeServerError,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
    serverState,
} from "@web/../tests/web_test_helpers";
import { router } from "@web/core/browser/router";
import { user } from "@web/core/user";
import { WebClient } from "@web/webclient/webclient";

describe.current.tags("desktop");

defineModels(DocumentsModels);

defineActions([
    {
        id: 1,
        name: "Documents",
        res_model: "document.document",
        views: [[false, "kanban"]],
    },
]);
DocumentsModels.DocumentsDocument._views = {
    kanban: basicDocumentsKanbanArch,
    list: basicDocumentsListArch,
    [["search", false]]: getEnrichedSearchArch(),
    form: `<form>
        <field name="type" invisible="1" force_save="1"/>
        <field name="active" string="Active" invisible="1"/>
        <field name="access_internal" invisible="1"/>
        <field name="access_via_link" invisible="1"/>
        <field name="user_permission" invisible="1"/>
        <sheet>
            <div class="oe_title">
                <label for="name"/>
                <h1><field name="name" required="True"/></h1>
            </div>
        </sheet>
    </form>`,
};
DocumentsModels.DocumentsOperation._views = { form: basicDocumentsOperationFormArch };
onRpc("/documents/touch/accessTokenRequest", () => ({}));
onRpc("/documents/touch/accessTokenDuplicateTestDoc", () => ({}));
onRpc("action_confirm", () => ({}));

test("Duplicate a document in a Newly made folder", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Duplicate Test Doc", {
            owner_id: serverState.userId,
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(
        ".o_kanban_record:contains('Duplicate Test Doc') .o_record_selector",
    ).click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-clone").click();
    await animationFrame();

    expect(".btn-primary:contains('Duplicate in My Drive')").toHaveCount(1);
    expect(".btn-secondary:contains('Create a folder in My Drive')").toHaveCount(1);

    await contains(".o_widget_documents_operation_new_folder .btn-secondary").click();
    await contains(".o_input").edit("New Folder");
    await contains(".o_form_button_save").click();
    await animationFrame();

    expect(".btn-primary:contains('Duplicate in New Folder')").toHaveCount(1);
    expect(".btn-secondary:contains('Create a folder in New Folder')").toHaveCount(1);

    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();

    await waitFor(".o_notification");
    expect(".o_notification_content").toHaveText(
        "Done. Document created in New Folder!",
    );
});

test('Internal users can always move to "My Drive"', async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { owner_id: serverState.userId }),
        makeDocumentRecordData(3, "Folder 2", {
            owner_id: serverState.userId,
            type: "folder",
        }),
    ]);
    serverData["document.document"][0].user_permission = "view";
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();

    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await animationFrame();
    expect(".btn-primary:contains('Move to My Drive')").not.toHaveAttribute("disabled");
    expect(".btn-secondary:contains('Create a folder in My Drive')").toHaveCount(1);

    await contains(".modal-content li div span:contains('Folder 1')").click();
    await animationFrame();
    expect(".btn-primary:contains('Insufficient access to Folder 1')").toHaveAttribute(
        "disabled",
    );
    expect(".btn-secondary:contains('Create a folder in Folder 1')").toHaveCount(0);

    await contains(".modal-content li div span:contains('Folder 2')").click();
    await animationFrame();
    expect(".btn-primary:contains('Move to Folder 2')").not.toHaveAttribute("disabled");
    expect(".btn-secondary:contains('Create a folder in Folder 2')").toHaveCount(1);
});

test("Portal user without edit folder has no Move button", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", {
            folder_id: 1,
            owner_id: serverState.userId,
        }),
    ]);
    serverData["document.document"][0].user_permission = "view";
    patchWithCleanup(user, {
        hasGroup: (group) => group === "base.group_portal",
        isInternalUser: false,
    });
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await waitFor(".o-dropdown-item");
    expect(".o-dropdown-item .fa-right-to-bracket").toHaveCount(0);
});

test("Portal user with any edit folder has the Move button", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { folder_id: 1, user_permission: "edit" }),
    ]);
    serverData["document.document"][0].user_permission = "edit";
    patchWithCleanup(user, {
        hasGroup: (group) => group === "base.group_portal",
        isInternalUser: false,
    });
    patchWithCleanup(DocumentsModels.DocumentsOperation._fields, {
        destination: fields.Char({ default: "1" }),
        display_name: fields.Char({ default: "Folder 1" }),
    });
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await waitFor(".btn-primary:contains('Move to Folder 1')");
    expect(".btn-secondary:contains('Create a folder')").toHaveCount(0);
});

test("a move cancelled at the access warning confirms the destination picked next", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", {
            owner_id: serverState.userId,
            access_internal: "none",
        }),
        makeDocumentRecordData(3, "Folder 2", {
            owner_id: serverState.userId,
            type: "folder",
            user_permission: "edit",
            access_internal: "edit",
        }),
        makeDocumentRecordData(4, "Folder 3", {
            owner_id: serverState.userId,
            type: "folder",
            user_permission: "edit",
            access_internal: "edit",
        }),
    ]);
    onRpc("wizard.document.document.place.folder", "web_save", ({ args }) => {
        expect.step(`save ${args[1].destination}`);
    });
    onRpc(
        "wizard.document.document.place.folder",
        "action_confirm",
        function ({ args, kwargs }) {
            const Wizard = this.env["wizard.document.document.place.folder"];
            const [wizard] = Wizard.browse(args[0]);
            Wizard.action_confirm(args[0], makeKwArgs(kwargs));
            expect.step(`confirm ${wizard.destination}`);
            return true;
        },
    );
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();

    await contains(".modal-content li div span:contains('Folder 2')").click();
    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();
    await contains(
        ".modal:has(.o_documents_access_rights_update_dialog) .btn-secondary",
    ).click();

    await contains(".modal-content li div span:contains('Folder 3')").click();
    await contains(".btn-primary:contains('Move to Folder 3')").click();
    await contains(
        ".modal:has(.o_documents_access_rights_update_dialog) .btn-primary",
    ).click();
    await waitFor(".o_notification");

    expect.verifySteps(["save 3", "save 4", "confirm 4"]);
});

test("a folder is picked from the keyboard in the move dialog", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { owner_id: serverState.userId }),
        makeDocumentRecordData(3, "Folder 2", {
            owner_id: serverState.userId,
            type: "folder",
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await contains(".modal-content li[data-value-id='3'] header").focus();
    await press("Enter");
    await animationFrame();
    expect(".btn-primary:contains('Move to Folder 2')").toHaveCount(1);
});

test("Add from Documents copies the documents and hands the caller the attachments", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Contract.pdf", {
            owner_id: serverState.userId,
            mimetype: "application/pdf",
        }),
    ]);
    onRpc("document.document", "add_documents_attachment", ({ args }) => {
        expect.step(`copy ${args[0]} for ${args[1]}`);
        return [{ id: 7, name: "Contract.pdf", mimetype: "application/pdf" }];
    });
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    const threadsBefore = Object.keys(getService("mail.store").Thread.records).length;
    getService("dialog").add(SelectAddDocumentCreateDialog, {
        resModel: "document.document",
        title: "Search: Documents",
        noCreate: true,
        context: { documents_view_secondary: true },
        onAddAttachments: async (attachments) =>
            expect.step(`link ${attachments.map(({ id }) => id)}`),
        onPasteLinks: () => {},
    });
    await contains(
        ".modal .o_data_row:contains('Contract.pdf') .o_list_record_selector",
    ).click();
    await contains(".modal button:contains('Add from Documents')").click();
    await animationFrame();

    expect.verifySteps(["copy 2 for wizard.mail.message.send", "link 7"]);
    expect(Object.keys(getService("mail.store").Thread.records)).toHaveLength(
        threadsBefore,
        {
            message: "no chatter thread is made up from the wizard's ids",
        },
    );
});

test("dismissing the access warning with Escape leaves the wizard usable", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", {
            owner_id: serverState.userId,
            access_internal: "none",
        }),
        makeDocumentRecordData(3, "Folder 2", {
            owner_id: serverState.userId,
            type: "folder",
            user_permission: "edit",
            access_internal: "edit",
        }),
    ]);
    onRpc(
        "wizard.document.document.place.folder",
        "action_confirm",
        function ({ args, kwargs }) {
            this.env["wizard.document.document.place.folder"].action_confirm(
                args[0],
                makeKwArgs(kwargs),
            );
            expect.step("confirm");
            return true;
        },
    );
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await contains(".modal-content li div span:contains('Folder 2')").click();
    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();
    await waitFor(".o_documents_access_rights_update_dialog");
    await press("Escape");
    await animationFrame();
    expect(
        ".o_widget_documents_operation_confirmation .btn-primary",
    ).not.toHaveAttribute("disabled");
    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();
    await contains(
        ".modal:has(.o_documents_access_rights_update_dialog) .btn-primary",
    ).click();
    await waitFor(".o_notification");
    expect.verifySteps(["confirm"]);
});

test("a documents picker opened over the view leaves the view its action menus", async function () {
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    const selectionActions = getService("document.document").selectionActions;
    const mainProvider = selectionActions.provider;
    expect(mainProvider).not.toBe(null);

    getService("dialog").add(SelectAddDocumentCreateDialog, {
        resModel: "document.document",
        title: "Search: Documents",
        noCreate: true,
        context: { documents_view_secondary: true },
        onPasteLinks: () => {},
    });
    await waitFor(".modal .o_list_renderer");
    expect(selectionActions.provider).toBe(mainProvider);
    await contains(".modal .o_form_button_cancel, .modal .btn-close").click();
    await animationFrame();
    expect(selectionActions.provider).toBe(mainProvider, {
        message: "closing the picker does not leave the view without menus",
    });
});

test("the documents picker pastes links through its caller, and offers no Add without a target", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Contract.pdf", {
            owner_id: serverState.userId,
            mimetype: "application/pdf",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    openDocumentsPicker(getService("dialog"), {
        onPasteLinks: (links) =>
            expect.step(`paste ${links.map(({ display_name }) => display_name)}`),
    });
    await contains(
        ".modal .o_data_row:contains('Contract.pdf') .o_list_record_selector",
    ).click();
    expect(".modal button:contains('Add from Documents')").toHaveCount(0);
    await contains(".modal button:contains('Paste Link(s)')").click();
    await waitFor(".o_notification:contains('Link(s) pasted!')");
    expect.verifySteps(["paste Contract.pdf"]);
});

test("moving into a folder just made asks no confirmation when its access matches", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Movable Doc", {
            owner_id: serverState.userId,
            user_permission: "edit",
            access_internal: "edit",
            access_via_link: "none",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    await contains(
        ".o_kanban_record:contains('Movable Doc') .o_record_selector",
    ).click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await contains(".o_widget_documents_operation_new_folder .btn-secondary").click();
    await contains(".o_input").edit("Same Access");
    await contains(".o_form_button_save").click();
    await animationFrame();
    // one refresh: the reopened wizard adds none of its own, and the folder
    // tree is not served stale from the cache first
    onRpc("search_panel_select_range", () => {
        expect.step("folders");
    });
    onRpc("document.document", "web_search_read", () => {
        expect.step("records");
    });
    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();
    await animationFrame();
    expect(".modal:contains('Moving to:')").toHaveCount(0, {
        message: "the new folder grants what the document already has",
    });
    expect.verifySteps(["folders", "records"]);
});

test('"Shared with me" is browsed, never picked as a destination', async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", {
            owner_id: serverState.userId,
            user_permission: "edit",
        }),
        makeDocumentRecordData(4, "Shared Folder", {
            type: "folder",
            user_folder_id: "SHARED",
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await animationFrame();
    await contains(".modal-content li div span:contains('Shared with me')").click();
    await animationFrame();
    expect(".btn-primary:contains('Move to My Drive')").toHaveCount(1, {
        message: "a move into Shared with me is refused by the server",
    });
});

test("clearing the folder filter keeps the chosen folder's path open", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", {
            owner_id: serverState.userId,
            user_permission: "edit",
        }),
        makeDocumentRecordData(3, "Nested Target", {
            type: "folder",
            folder_id: 1,
            user_permission: "edit",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await animationFrame();
    await contains(
        ".modal .o_documents_operation_search_panel input, .modal .input-group input",
    ).edit("Nested");
    await contains(".modal-content li div span:contains('Nested Target')").click();
    await animationFrame();
    await contains(".modal .input-group button").click();
    await animationFrame();
    expect(".modal-content li div span:contains('Nested Target')").toHaveCount(1, {
        message: "the path down to the destination stays unfolded",
    });
});

test("the documents picker opened outside Documents writes no document token in the URL", async function () {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Contract.pdf", {
            owner_id: serverState.userId,
            mimetype: "application/pdf",
            access_token: "secretToken",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction({
        type: "ir.actions.act_window",
        res_model: "res.partner",
        res_id: serverState.partnerId,
        views: [[false, "form"]],
    });
    patchWithCleanup(router, {
        pushState(state) {
            if (state?.access_token) {
                expect.step(`token ${state.access_token}`);
            }
            return super.pushState(...arguments);
        },
    });
    openDocumentsPicker(getService("dialog"), { onPasteLinks: () => {} });
    await contains(
        ".modal .o_data_row:contains('Contract.pdf') .o_list_record_selector",
    ).click();
    await animationFrame();
    expect.verifySteps([]);
});

test("a composer that forbids uploads gets the documents picker without Add", async function () {
    await makeDocumentsMockEnv({ serverData: getDocumentsTestServerModelsData() });
    const action = composerActionsRegistry.get("add-documents");
    const opened = [];
    const dialog = { add: (Component, props) => opened.push(props) };
    const params = (allowUpload) => ({
        composer: { attachments: [] },
        owner: { allowUpload },
        store: { env: { services: { dialog } } },
    });
    action.onSelected(params(false));
    action.onSelected(params(true));
    expect(opened.map((props) => Boolean(props.onAddAttachments))).toEqual([
        false,
        true,
    ]);
    expect(opened.every((props) => props.onPasteLinks)).toBe(true, {
        message: "pasting a link uploads nothing",
    });
});

/**
 * Opens the move wizard on "Request" and confirms a move into "Folder 2",
 * which the server refuses with `changes` when checked, if given.
 *
 * @param {Object|null} changes
 */
async function moveRequestToFolder2(changes) {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "Request", { owner_id: serverState.userId }),
        makeDocumentRecordData(3, "Folder 2", {
            owner_id: serverState.userId,
            type: "folder",
            user_permission: "edit",
        }),
    ]);
    onRpc("wizard.document.document.place.folder", "action_confirm", ({ kwargs }) => {
        const checked = Boolean(kwargs.context?.[MOVE_ACCESS_CHECK]);
        expect.step(checked ? "checked move" : "move");
        if (checked && changes) {
            throw makeServerError({
                errorName: "odoo.addons.document.tools.MoveChangesAccess",
                args: ["changes access", changes],
            });
        }
        return true;
    });
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request') .o_record_selector").click();
    await contains(".o_dropdown_title").click();
    await contains(".o-dropdown-item .fa-right-to-bracket").click();
    await contains(".modal-content li div span:contains('Folder 2')").click();
    await contains(".o_widget_documents_operation_confirmation .btn-primary").click();
}

test("a move changing no access is made in one call, unasked", async function () {
    await moveRequestToFolder2(null);
    await waitFor(".o_notification");
    expect(".o_documents_access_rights_update_dialog").toHaveCount(0);
    expect.verifySteps(["checked move"]);
});

test("the access warning shows only what the move changes, and a cancel moves nothing", async function () {
    await moveRequestToFolder2({
        access_internal: [],
        access_via_link: "view",
        documents: 1,
        contents: 0,
    });
    await waitFor(".o_documents_access_rights_update_dialog");
    expect("#o_documents_access_update_confirmation_access_internal").toHaveCount(0, {
        message:
            "a restricted document keeps its internal access: no row claims otherwise",
    });
    expect(
        "[aria-labelledby='o_documents_access_update_confirmation_access_via_link']",
    ).toHaveText("Viewer");
    await contains(
        ".modal:has(.o_documents_access_rights_update_dialog) .btn-secondary",
    ).click();
    expect.verifySteps(["checked move"]);
});

test("documents landing on different internal levels are told so, and moved once accepted", async function () {
    await moveRequestToFolder2({
        access_internal: ["none", "view"],
        access_via_link: false,
        documents: 2,
        contents: 0,
    });
    await waitFor(".o_documents_access_rights_update_dialog");
    expect(
        "[aria-labelledby='o_documents_access_update_confirmation_access_internal']",
    ).toHaveText("None / Viewer");
    expect(".o_documents_access_rights_update_dialog").toHaveText(
        /Each document keeps the higher access set on it/,
    );
    expect("#o_documents_access_update_confirmation_access_via_link").toHaveCount(0);
    await contains(
        ".modal:has(.o_documents_access_rights_update_dialog) .btn-primary",
    ).click();
    await waitFor(".o_notification");
    expect.verifySteps(["checked move", "move"]);
});

test("the access warning counts what the moved folders contain", async function () {
    await moveRequestToFolder2({
        access_internal: ["edit"],
        access_via_link: false,
        documents: 0,
        contents: 3,
    });
    await waitFor(".o_documents_access_rights_update_dialog");
    expect(".o_documents_access_rights_update_dialog").toHaveText(
        /change the access rights of 3 item\(s\) the moved folder\(s\) contain/,
    );
    expect.verifySteps(["checked move"]);
});
