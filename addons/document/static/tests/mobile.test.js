import {
    mockPdfSplit,
    mountPdfManager,
    usePdfManagerDoubles,
} from "@document/../tests/helpers/pdf_manager";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { contains, defineModels } from "@web/../tests/web_test_helpers";

import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { mountDocumentsKanbanView } from "./helpers/views/kanban.js";

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
