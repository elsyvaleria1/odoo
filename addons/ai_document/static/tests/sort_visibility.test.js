import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
} from "@document/../tests/helpers/data";
import { makeDocumentsMockEnv } from "@document/../tests/helpers/model";
import { mountDocumentsKanbanView } from "@document/../tests/helpers/views/kanban";
import { describe, expect, test } from "@odoo/hoot";
import { waitFor } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { user } from "@web/core/user";

describe.current.tags("desktop");

defineModels(DocumentsModels);

test("Admin user should be able to see the Auto-sort item under the cog menu", async function () {
    const serverData = getDocumentsTestServerModelsData();
    const { name: folder1Name } = serverData["document.document"][0];
    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(user, {
        hasGroup: async () => true,
        isSystem: true,
    });
    await mountDocumentsKanbanView();
    await waitFor(".o_kanban_renderer");

    await contains(`.o_kanban_record:contains(${folder1Name})`).click();
    await waitFor(`.o_last_breadcrumb_item:contains('${folder1Name}')`);
    await contains(".o_cp_action_menus .fa-cog").click();
    await waitFor(`.o-dropdown-item`);
    expect(".o-dropdown-item:contains('Auto-Sort…')").toHaveCount(1);
});

test("Basic user shouldn't be able to see the Auto-sort item under the cog menu", async function () {
    const serverData = getDocumentsTestServerModelsData();
    const { name: folder1Name } = serverData["document.document"][0];
    patchWithCleanup(user, {
        hasGroup: async (group) => group === "base.group_user",
        isSystem: false,
    });
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await waitFor(".o_kanban_renderer");

    await contains(`.o_kanban_record:contains(${folder1Name})`).click();
    await waitFor(`.o_last_breadcrumb_item:contains('${folder1Name}')`);
    await contains(".o_cp_action_menus .fa-cog").click();
    await waitFor(`.o-dropdown-item`);
    expect(".o-dropdown-item:contains('Auto-Sort…')").toHaveCount(0);
});
