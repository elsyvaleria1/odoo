import { DocumentsSearchPanelUserFolderId } from "@document/views/fields/document_user_folder_id_char/document_search_panel_user_folder_id";
import { mailModels } from "@mail/../tests/mail_test_helpers";
import { expect, test } from "@odoo/hoot";
import { animationFrame, queryAllTexts } from "@odoo/hoot-dom";
import {
    contains,
    defineModels,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";

defineModels(mailModels);

const FOLDERS = [
    { id: "COMPANY", display_name: "Company" },
    { id: "MY", display_name: "My Drive" },
    { id: 1, display_name: "Finance", user_folder_id: "COMPANY" },
    { id: 2, display_name: "Invoices", user_folder_id: 1 },
    { id: 3, display_name: "Legal", user_folder_id: "COMPANY" },
];

async function mountPicker() {
    onRpc("document.document", "search_panel_select_range", () => ({
        values: FOLDERS,
    }));
    await mountWithCleanup(DocumentsSearchPanelUserFolderId, {
        props: { value: "COMPANY", onChange: () => {} },
    });
}

const labels = () => queryAllTexts(".o_search_panel_label_title");

test("the folder picker filters as the user types, keeping a match's parents", async () => {
    await mountPicker();
    expect(labels()).toInclude("Legal");

    await contains("input[placeholder='Search...']").edit("invo", { confirm: false });
    await animationFrame();
    expect(labels()).toInclude("Invoices");
    expect(labels()).toInclude("Finance", { message: "the match's parent stays" });
    expect(labels()).not.toInclude("Legal");

    await contains(".btn-outline-secondary").click();
    await animationFrame();
    expect(labels()).toInclude("Legal", {
        message: "clearing shows every folder again",
    });
});
