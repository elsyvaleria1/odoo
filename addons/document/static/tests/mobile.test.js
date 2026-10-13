import {
    mockPdfSplit,
    mountPdfManager,
    usePdfManagerDoubles,
} from "@document/../tests/helpers/pdf_manager";
import { DocumentsKanbanModel } from "@document/views/kanban/document_kanban_model";
import { describe, expect, test } from "@odoo/hoot";
import { isVisible, queryAllTexts } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineActions,
    defineModels,
    getService,
    mountWithCleanup,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import {
    basicDocumentsKanbanArch,
    mountDocumentsKanbanView,
} from "./helpers/views/kanban.js";
import { basicDocumentsListArch } from "./helpers/views/list.js";
import { getEnrichedSearchArch } from "./helpers/views/search.js";

describe.current.tags("mobile");

defineModels(DocumentsModels);
usePdfManagerDoubles();

test("the splitter's Action menu splits, it is not a way out of the splitter", async () => {
    await mountPdfManager();
    await contains(".o_pdf_name_display:eq(1)").click();
    mockPdfSplit();
    await contains(".o_documents_pdf_manager_top_bar .dropdown-toggle").click();
    await contains(".o_pdf_manager_menu .dropdown-item:contains(Split)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:200"]);
    expect(".modal:contains(Stay here)").toHaveCount(0);
});

test("the folder panel opens as a menu and picking a folder shows its documents", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "In Folder 1", { folder_id: 1 }),
        makeDocumentRecordData(3, "Elsewhere", { user_folder_id: "MY" }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_search_panel .dropdown-toggle").click();
    await contains(
        ".o_search_panel_category_value[data-value-id='COMPANY'] .o_toggle_fold",
    ).click();
    await contains(".o_search_panel_label_title:contains('Folder 1')").click();
    await animationFrame();
    expect(".o_kanban_record:contains('In Folder 1')").toHaveCount(1);
    expect(".o_kanban_record:contains('Elsewhere')").toHaveCount(0);
});

test("picking a folder with no subfolder closes the folder menu", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "In Folder 1", { folder_id: 1 }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_search_panel .dropdown-toggle").click();
    await contains(
        ".o_search_panel_category_value[data-value-id='COMPANY'] .o_toggle_fold",
    ).click();
    await contains(".o_search_panel_label_title:contains('Folder 1')").click();
    await animationFrame();
    expect(".o_search_panel_category_value").toHaveCount(0, {
        message: "a leaf has nothing left to show in the menu",
    });
});

test("on a small screen the cog acts on the open folder too", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "In Folder 1", { folder_id: 1 }),
    ]);
    onRpc("/documents/touch/*", () => ({}));
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_search_panel .dropdown-toggle").click();
    await contains(
        ".o_search_panel_category_value[data-value-id='COMPANY'] .o_toggle_fold",
    ).click();
    await contains(".o_search_panel_label_title:contains('Folder 1')").click();
    await animationFrame();
    await contains(".o_cog_menu_toggler").click();
    const items = queryAllTexts(".o-dropdown--menu .o-dropdown-item");
    expect(items).toInclude("Rename…", {
        message: "the folder's actions, not only the view's",
    });
    expect(items).toInclude("Share…");
});

/** @returns {Promise<Object>} */
async function mountKanbanCapturingModel(serverData) {
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await makeDocumentsMockEnv({ serverData });
    return { getModel: () => model };
}

const folderMenuHidden = () => !isVisible(".o_content > .o_search_panel");

test("the folder menu steps aside while documents are selected", async () => {
    const { getModel } = await mountKanbanCapturingModel(
        getDocumentsTestServerModelsData([makeDocumentRecordData(2, "Doc A")]),
    );
    await mountDocumentsKanbanView();
    const record = getModel().root.records.find((r) => r.resId === 2);
    expect(folderMenuHidden()).toBe(false);
    record.toggleSelection(true);
    await animationFrame();
    expect(folderMenuHidden()).toBe(true, {
        message: "the selection bar takes its room",
    });
    record.toggleSelection(false);
    await animationFrame();
    expect(folderMenuHidden()).toBe(false);
});

test("a view switch keeping the selection keeps the folder menu aside", async () => {
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        list: basicDocumentsListArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    defineActions([
        {
            id: 1,
            name: "Documents",
            res_model: "document.document",
            views: [
                [false, "kanban"],
                [false, "list"],
            ],
        },
    ]);
    const { getModel } = await mountKanbanCapturingModel(
        getDocumentsTestServerModelsData([makeDocumentRecordData(2, "Doc A")]),
    );
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    getModel()
        .root.records.find((r) => r.resId === 2)
        .toggleSelection(true);
    await animationFrame();
    await getService("action").switchView("list");
    await animationFrame();
    expect(".o_data_row_selected").toHaveCount(1);
    expect(folderMenuHidden()).toBe(true, {
        message: "the list mounts with the selection: no patch needed to hide it",
    });
});
