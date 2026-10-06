import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
} from "@document/../tests/helpers/data";
import { makeDocumentsMockEnv } from "@document/../tests/helpers/model";
import { embeddedActionsServerData } from "@document/../tests/helpers/test_server_data";
import { basicDocumentsKanbanArch } from "@document/../tests/helpers/views/kanban";
import { basicDocumentsListArch } from "@document/../tests/helpers/views/list";
import { getEnrichedSearchArch } from "@document/../tests/helpers/views/search";
import { preferredDocumentsViewType } from "@document/core/document_client_action";
import { describe, expect, test } from "@odoo/hoot";
import { queryAllTexts, waitFor } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    defineActions,
    defineModels,
    getService,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

defineModels(DocumentsModels);
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
    {
        id: 2,
        xml_id: "document.document_action",
        name: "Documents",
        res_model: "document.document",
        views: [
            [false, "kanban"],
            [false, "list"],
        ],
    },
]);

describe.current.tags("desktop");

test("Keep showing actions on view switch", async function () {
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        list: basicDocumentsListArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);

    expect(`.o_kanban_view .o_content.o_component_with_search_panel`).toHaveCount(1);
    await contains(`.o_kanban_record:contains('Request 1')`).click();
    await waitFor(".o_control_panel_actions:contains('Action 1')");

    await getService("action").switchView("list");
    await waitFor(".o_data_row:contains('Request 1')");
    await waitFor(".o_control_panel_actions:contains('Action 1')");

    await getService("action").switchView("kanban");
    await waitFor(".o_kanban_record:contains('Request 1')");
    await waitFor(".o_control_panel_actions:contains('Action 1')");
});

test("a folder's actions keep the server's order, not their ids' order", async function () {
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        list: basicDocumentsListArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    const serverData = getDocumentsTestServerModelsData([
        {
            folder_id: 1,
            id: 2,
            name: "Request",
            available_embedded_actions_ids: [3, 1],
        },
    ]);
    serverData["ir.embedded.actions"] = [
        { id: 1, name: "Pinned second" },
        { id: 3, name: "Pinned first" },
    ];
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request')").click();
    await waitFor(".o_control_panel_actions:contains('Pinned first')");
    const labels = queryAllTexts(".o_control_panel_actions button");
    expect(labels.indexOf("Pinned first")).toBeLessThan(
        labels.indexOf("Pinned second"),
    );
});

test("the Documents app remembers the layout last shown, and only its own", async function () {
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        list: basicDocumentsListArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await getService("action").switchView("list");
    await waitFor(".o_data_row");
    expect(preferredDocumentsViewType()).toBe(null, {
        message: "another Documents action leaves the app's preference alone",
    });

    await getService("action").doAction(2);
    await waitFor(".o_kanban_record");
    expect(preferredDocumentsViewType()).toBe("kanban");
    await getService("action").switchView("list");
    await waitFor(".o_data_row");
    expect(preferredDocumentsViewType()).toBe("list");
});

test("switching views keeps the whole selection, even with one of them previewed", async function () {
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        list: basicDocumentsListArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    await makeDocumentsMockEnv({ serverData: embeddedActionsServerData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(".o_kanban_record:contains('Request 1') .o_record_selector").click();
    await contains(".o_kanban_record:contains('Request 2') .o_record_selector").click({
        ctrlKey: true,
    });
    expect(".o_kanban_record.o_record_selected").toHaveCount(2);
    const documentService = getService("document.document");
    documentService.setPreviewedDocument({ record: documentService.focusedRecord });
    await animationFrame();
    expect(".o_kanban_record.o_record_selected").toHaveCount(2);

    await getService("action").switchView("list");
    await waitFor(".o_data_row:contains('Request 1')");
    expect(".o_data_row.o_data_row_selected").toHaveCount(2);
});
