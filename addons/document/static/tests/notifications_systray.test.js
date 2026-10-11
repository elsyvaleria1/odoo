import { click, openMessagingMenu, start } from "@mail/../tests/mail_test_helpers";
import { describe, expect, test, waitFor } from "@odoo/hoot";
import {
    contains,
    defineActions,
    getService,
    serverState,
} from "@web/../tests/web_test_helpers";

import { defineDocumentsModels } from "./document_test_helpers.js";
import { DocumentsModels, getDocumentsTestServerModelsData } from "./helpers/data.js";
import { setDocumentsServerData } from "./helpers/model.js";
import { basicDocumentsKanbanArch } from "./helpers/views/kanban.js";
import { basicDocumentsListArch } from "./helpers/views/list.js";
import { getEnrichedSearchArch } from "./helpers/views/search.js";

describe.current.tags("desktop");

defineDocumentsModels();
const ACTION_1_ID = "document.document_action";

const getServerData = () => {
    const serverData = getDocumentsTestServerModelsData([
        {
            res_model: "document.document",
            folder_id: 1,
            id: 2,
            name: "Test Doc With Notification",
        },
    ]);

    Object.assign(
        serverData["res.users"].find((user) => user.id === serverState.userId),
        { login: "admin", password: "admin", notification_type: "inbox" },
    );
    serverData["mail.message"] = [
        {
            author_id: serverState.partnerId,
            body: "Howdy Neighbor",
            needaction: true,
            model: "document.document",
            res_id: 2,
            id: 1000,
        },
    ];
    serverData["mail.notification"] = [
        {
            mail_message_id: 1000,
            notification_status: "sent",
            notification_type: "inbox",
            res_partner_id: serverState.partnerId,
        },
    ];

    defineActions([
        {
            xml_id: ACTION_1_ID,
            id: 99,
            type: "ir.actions.act_window",
            name: "Document",
            res_model: "document.document",
            search_view_id: [false, "search"],
            views: [
                [false, "kanban"],
                [false, "list"],
                [false, "form"],
            ],
        },
    ]);

    DocumentsModels["DocumentsDocument"]._views = {
        kanban: basicDocumentsKanbanArch,
        form: `<form>`,
        list: basicDocumentsListArch,
        search: getEnrichedSearchArch(),
    };
    return serverData;
};

const openNotificationToDocument = async () => {
    await openMessagingMenu("notification");
    await click(".o-mail-NotificationItem");
    await waitFor('.o_search_panel_category_value header.active:contains("All")');
    expect(
        ".o_kanban_record.o_record_selected:contains('Test Doc With Notification')",
    ).toHaveCount(1);
};

test("Systray Open switches to All and selects the document", async function () {
    setDocumentsServerData(getServerData());
    await start();
    await getService("action").doAction(ACTION_1_ID);
    await contains('.o_search_panel_label_title:contains("My Drive")').click();
    await waitFor('.o_search_panel_category_value header.active:contains("My Drive")');
    await openNotificationToDocument();
});

test("Systray Open opens documents on All and selects the document", async function () {
    setDocumentsServerData(getServerData());
    await start();
    await openNotificationToDocument();
});
