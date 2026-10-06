import {
    listedPageIds,
    makeFakePdf,
    mockPdfSplit,
    mountPdfManager,
    PdfManagerForTest,
    pdfTracker,
    SmallScreenPdfManager,
    usePdfManagerDoubles,
} from "@document/../tests/helpers/pdf_manager";
import { PdfManager } from "@document/owl/components/pdf_manager/pdf_manager";
import { defineMailModels } from "@mail/../tests/mail_test_helpers";
import { describe, destroy, expect, test } from "@odoo/hoot";
import { click, press, queryAll, queryOne } from "@odoo/hoot-dom";
import { animationFrame, Deferred, mockFetch } from "@odoo/hoot-mock";
import { onPatched } from "@odoo/owl";
import { contains } from "@web/../tests/web_test_helpers";

defineMailModels();

describe.current.tags("desktop");

usePdfManagerDoubles();

test(`Pdf Manager basic rendering`, async () => {
    await mountPdfManager();
    expect(".o_documents_pdf_manager_top_bar").toHaveCount(1, {
        message: "There should be one top bar",
    });
    expect(".o_documents_pdf_page_viewer").toHaveCount(1, {
        message: "There should be one page viewer",
    });
    expect(".o_pdf_manager_button:eq(0)").toHaveText("Split", {
        message: "There should be a split button",
    });
    expect(".o_pdf_manager_button:eq(2)").toHaveText("ADD FILE", {
        message: "There should be a ADD FILE button",
    });
    expect(".o_pdf_manager_button:eq(3)").toHaveText("ACTION1", {
        message: "There should be a ACTION1 button",
    });
    expect(".o_pdf_manager_button:eq(4)").toHaveText("ACTION2", {
        message: "There should be a ACTION2 button",
    });
    expect(".o_pdf_separator_selected").toHaveCount(1, {
        message: "There should be one active separator",
    });
    expect(".o_pdf_page").toHaveCount(12, { message: "There should be 12 pages" });
    expect(".o_documents_pdf_button_wrapper").toHaveCount(12, {
        message: "There should be 12 button wrappers",
    });
    expect(".o_pdf_group_name_wrapper").toHaveCount(2, {
        message: "There should be 2 name plates",
    });
});

test(`Pdf Manager: page interactions`, async () => {
    await mountPdfManager();

    expect(".o_pdf_separator_selected").toHaveCount(1, {
        message: "There should be one active separator",
    });

    await contains(".o_page_splitter_wrapper:eq(1)").click();
    expect(".o_pdf_separator_selected").toHaveCount(2, {
        message: "There should be 2 active separator",
    });
    expect(".o_pdf_page_selected").toHaveCount(12, {
        message: "There should be 12 selected pages",
    });

    await contains(".o_documents_pdf_page_selector:eq(3)").click();
    expect(".o_pdf_page_selected").toHaveCount(11, {
        mesage: "There should be 11 selected pages",
    });
});

test(`Pdf Manager: drag & drop`, async () => {
    await mountPdfManager();

    expect(".o_pdf_separator_selected").toHaveCount(1, {
        message: "There should be one active separator",
    });
    expect(".o_documents_pdf_page_frame:eq(6) .o_pdf_name_display").toHaveCount(1, {
        message: "The seventh page should have a name plate",
    });

    await contains(".o_documents_pdf_canvas_wrapper:eq(11)").dragAndDrop(
        ".o_documents_pdf_canvas_wrapper:eq(0)",
        null,
        {
            dataTransfer: new DataTransfer(),
        },
    );
    expect(".o_pdf_separator_selected").toHaveCount(1, {
        message: "There should be one active separator",
    });
    expect(".o_documents_pdf_page_frame:eq(6) .o_pdf_name_display").toHaveCount(0, {
        message: "The seventh page shouldn't have a name plate",
    });
    expect(".o_documents_pdf_page_frame:eq(7) .o_pdf_name_display").toHaveCount(1, {
        message: "The eight page should have a name plate",
    });
});

test(`Pdf Manager: select/Unselect all pages`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(12, {
        message: "There should be 12 pages selected",
    });

    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });
});

test(`Pdf Manager: Ctrl+S splits the selection page by page, then gathers it`, async () => {
    await mountPdfManager();
    await contains(".o_documents_pdf_page_viewer").click();
    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_separator_selected").toHaveCount(1);

    await press(["ctrl", "s"]);
    await animationFrame();
    expect(".o_pdf_separator_selected").toHaveCount(11, {
        message: "the one present separator is kept, the ten missing are added",
    });

    await press(["ctrl", "s"]);
    await animationFrame();
    expect(".o_pdf_separator_selected").toHaveCount(0, {
        message: "every separator was present: all are removed",
    });
});

test(`Pdf Manager: select pages with mouse area selection`, async () => {
    await mountPdfManager();

    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    const viewer = queryOne(".o_documents_pdf_manager");
    const { top, left, width, height } = viewer.getBoundingClientRect();
    const { drop, moveTo } = await contains(".o_documents_pdf_manager").drag({
        position: { x: left, y: top },
    });
    const position = { x: left + width, y: top + height };
    await moveTo({ position });
    await drop({ position });
    expect(".o_pdf_page_selected").toHaveCount(12, {
        message: "There should be 12 pages selected",
    });
});

test("Pdf Manager: puts separators on active pages by pressing control+s", async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(12, {
        message: "There should be 12 pages selected",
    });

    await press(["ctrl", "s"]);
    await animationFrame();
    expect(".o_pdf_separator_selected").toHaveCount(11, {
        message: "There should be 11 active separators",
    });
});

test(`Pdf Manager: click on page bottom area selects the page`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await contains(".o_bottom_selection").click();
    expect(".o_pdf_page_selected").toHaveCount(1, {
        message: "There should be one page selected",
    });
});

test(`Pdf Manager: click on page selector selects the page`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await contains(".o_documents_pdf_page_selector").click();
    expect(".o_pdf_page_selected").toHaveCount(1, {
        message: "There should be one page selected",
    });
});

test(`Pdf Manager: arrow navigation`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press("arrowRight");
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(0) .o_pdf_page_focused").toHaveCount(1, {
        message: "The first page should be focused",
    });

    await press("arrowRight");
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(1) .o_pdf_page_focused").toHaveCount(1, {
        message: "The first page should be focused",
    });
});

test(`Pdf Manager: arrow navigation + shift page activation`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press(["shift", "arrowRight"]);
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(0) .o_pdf_page_focused").toHaveCount(1, {
        message: "The first page should be focused",
    });

    await press(["shift", "arrowRight"]);
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(1) .o_pdf_page_focused").toHaveCount(1, {
        message: "The second page should be focused",
    });

    await press(["shift", "arrowRight"]);
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(2) .o_pdf_page_focused").toHaveCount(1, {
        message: "The third page should be focused",
    });
    expect(".o_pdf_page_selected").toHaveCount(3, {
        message: "3 pages should be selected",
    });

    await press(["shift", "arrowLeft"]);
    await press(["shift", "arrowLeft"]);
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(0) .o_pdf_page_focused").toHaveCount(1, {
        message: "The first page should be focused",
    });
    expect(".o_pdf_page_selected").toHaveCount(1, {
        message: "One page should be selected",
    });
});

test(`Pdf Manager: ctrl+shift+arrow shortcut multiple activation`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press("arrowRight");
    await press(["shift", "ctrl", "arrowRight"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(6, {
        message: "There should be 6 pages selected",
    });
});

test(`Pdf Manager: ctrl+arrow shortcut navigation between groups`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await press("arrowRight");
    await press(["ctrl", "arrowRight"]);
    await animationFrame();
    expect(".o_documents_pdf_page_frame:eq(6) .o_pdf_page_focused").toHaveCount(1, {
        message: "The seventh page should be focused",
    });
});

test(`Pdf Manager: click on group name should select all the group`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await contains(".o_pdf_name_display").click();
    expect(".o_pdf_page_selected").toHaveCount(6, {
        message: "6 pages should be selected",
    });
});

test(`Pdf Manager: page preview behaviour`, async () => {
    await mountPdfManager();

    await contains(".o_documents_pdf_page_viewer").click();
    expect(".o_pdf_page_selected").toHaveCount(0, {
        message: "There should be no page selected",
    });

    await contains(".o_documents_pdf_canvas_wrapper").click();
    expect(".o_pdf_page_preview").toHaveCount(1, {
        message: "The previewer should be open",
    });
    expect(".o_page_index").toHaveText("1/12", {
        message: "Index of the first page should be displayed",
    });
    expect(".o_page_name").toHaveText("yop-p1", {
        message: "Name of the group should be displayed",
    });

    await press("arrowRight");
    await animationFrame();
    expect(".o_page_index").toHaveText("2/12", {
        message: "Index of the second page should be displayed",
    });
    expect(".o_page_name").toHaveText("yop-p2", {
        message: "Name of the group should be displayed",
    });
});

test(`Pdf Manager: a failed split does not duplicate the ignored pages`, async () => {
    const manager = await mountPdfManager();
    await contains(".o_pdf_name_display:eq(1)").click();
    expect(".o_pdf_page_selected").toHaveCount(6, {
        message: "only the first group should be selected",
    });

    mockPdfSplit({ status: 500 });
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:500"]);

    const pageIds = listedPageIds(manager);
    expect(pageIds).toHaveLength(12, { message: "the 12 pages are each listed once" });
    expect(new Set(pageIds).size).toBe(12, {
        message: "no page id appears in two groups",
    });
    expect(manager.store.numberOfPages).toBe(12, {
        message: "numberOfPages matches the real page count",
    });
    expect(".o_pdf_page").toHaveCount(12, {
        message: "no duplicated card is rendered",
    });

    mockPdfSplit({ status: 500 });
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:500"]);
    expect(listedPageIds(manager)).toHaveLength(12, {
        message: "retrying a failed split does not accumulate pages",
    });
    expect(manager.store.numberOfPages).toBe(12);
});

test(`Pdf Manager: deleting after a partial split does not crash`, async () => {
    const manager = await mountPdfManager();
    await press(["ctrl", "a"]);
    await animationFrame();
    for (const index of [0, 1, 2]) {
        await contains(`.o_documents_pdf_page_selector:eq(${index})`).click();
    }
    expect(".o_pdf_page_selected").toHaveCount(3);

    const committedPageId = listedPageIds(manager)[0];
    manager.store.focusedPage = committedPageId;

    mockPdfSplit();
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:200"]);

    expect(manager.store.pages[committedPageId]).toBeOfType("object", {
        message: "the committed page survives, its file is not fully consumed",
    });
    expect(manager.store.pages[committedPageId].groupId).toBe(false);
    expect(manager.store.focusedPage).toBe(undefined, {
        message: "the focus is released when the focused page is committed",
    });

    expect(() =>
        manager._removePage(committedPageId, { fromFile: true }),
    ).not.toThrow();
    expect(listedPageIds(manager)).toHaveLength(9, {
        message: "3 pages of yop + the 6 untouched pages of blip",
    });

    await press("delete");
    await animationFrame();
    expect(".o_dialog").toHaveCount(0, {
        message: "nothing is selected nor focused: no delete confirmation, no crash",
    });
});

test(`Pdf Manager: a PDF that fails to load releases the toolbar`, async () => {
    PdfManagerForTest.pdfError = Object.assign(new Error("404"), {
        name: "UnexpectedResponseException",
    });
    const manager = await mountPdfManager();
    await animationFrame();

    expect(manager.state.uploadingLock).toBe(false, {
        message: "the upload lock is released even though the PDF never loaded",
    });
    expect(".o_notification").toHaveCount(2, {
        message: "one notification per failed file",
    });
    expect(".o_notification_content:eq(0)").toHaveText("Could not open yop.");
    for (const button of queryAll(".o_pdf_manager_button")) {
        expect(button).toBeEnabled({
            message: `"${button.textContent.trim()}" stays usable after a load failure`,
        });
    }
    expect(() => manager._focusNextPage("right", false)).not.toThrow();
});

test(`Pdf Manager: an encrypted PDF gets a dedicated message`, async () => {
    PdfManagerForTest.pdfError = Object.assign(new Error("password"), {
        name: "PasswordException",
    });
    await mountPdfManager();
    await animationFrame();

    expect(".o_notification_content:eq(0)").toHaveText(
        "yop is password protected and cannot be split.",
    );
});

test(`Pdf Manager: forward drag inside a group lands on the target index`, async () => {
    const manager = await mountPdfManager();
    const [p1, p2, p3, p4, p5, p6] = listedPageIds(manager);

    await contains(".o_documents_pdf_canvas_wrapper:eq(0)").dragAndDrop(
        ".o_documents_pdf_canvas_wrapper:eq(3)",
        null,
        { dataTransfer: new DataTransfer() },
    );
    expect(listedPageIds(manager).slice(0, 6)).toEqual([p2, p3, p1, p4, p5, p6], {
        message: "the dragged page takes the target's place, it does not land after it",
    });

    await contains(".o_documents_pdf_canvas_wrapper:eq(2)").dragAndDrop(
        ".o_documents_pdf_canvas_wrapper:eq(0)",
        null,
        { dataTransfer: new DataTransfer() },
    );
    expect(listedPageIds(manager).slice(0, 6)).toEqual([p1, p2, p3, p4, p5, p6], {
        message: "dropping it back on the first page restores the original order",
    });
    expect(manager.store.numberOfPages).toBe(12, {
        message: "reordering never changes the page count",
    });
});

test(`Pdf Manager: pdf documents and object URLs are released`, async () => {
    const manager = await mountPdfManager();
    await manager._addFile("extra.pdf", { file: new File([""], "extra.pdf") });
    await animationFrame();
    expect(manager._pdfDocuments).toHaveLength(3);
    expect(manager._objectUrls).toEqual(["blob:mock/extra.pdf"]);

    const extraFileId = Object.keys(manager._newFiles).at(-1);
    for (const pageId of [...manager._newFiles[extraFileId].pageIds]) {
        manager._removePage(pageId, { fromFile: true });
    }
    expect(pdfTracker.destroyedPdfs).toHaveLength(1, {
        message: "the consumed file's pdf.js document is destroyed right away",
    });
    expect(pdfTracker.revokedUrls).toEqual(["blob:mock/extra.pdf"]);
    expect(manager._pdfDocuments).toHaveLength(2, {
        message: "the released document is dropped from the unmount cleanup list",
    });
    expect(manager._objectUrls).toEqual([]);

    manager.__owl__.app.destroy();
    expect(pdfTracker.destroyedPdfs).toHaveLength(3, {
        message: "every remaining pdf.js document is destroyed on unmount",
    });
    expect(pdfTracker.revokedUrls).toHaveLength(1, { message: "no double revoke" });
});

test(`Pdf Manager: splitting on blank pages asks before discarding groups`, async () => {
    PdfManagerForTest.blankPages = [3];
    const manager = await mountPdfManager();
    await animationFrame();
    expect(manager.store.groupIds).toHaveLength(2);
    // the user's own grouping, which the split would wipe
    const [firstPageId] = manager.store.sortedPageIds;
    manager.store.toggleSeparator(
        firstPageId,
        manager.store.getPage(firstPageId).groupId,
    );

    await press(["shift", "s"]);
    await animationFrame();
    expect(".o_dialog").toHaveCount(1, {
        message: "a confirmation is required before wiping the existing grouping",
    });

    await contains(".o_dialog .btn-primary").click();
    await animationFrame();
    expect(manager.store.groupIds.length).toBeGreaterThan(2, {
        message: "confirming does split on the blank pages",
    });
    expect(listedPageIds(manager)).toHaveLength(12, {
        message: "blank-page splitting neither loses nor duplicates a page",
    });
    expect(manager.store.numberOfPages).toBe(12);
});

test(`Pdf Manager: numpad Enter commits a group rename`, async () => {
    const manager = await mountPdfManager();
    await contains(".o_pdf_name_display").click();
    await contains(".o_pdf_name_input").click();

    const input = queryOne(".o_pdf_name_input");
    input.value = "renamed";
    await press("Enter", { code: "NumpadEnter" });
    await animationFrame();

    expect(manager.store.groupData[manager.store.groupIds[0]].name).toBe("renamed", {
        message: "the numpad Enter key commits the rename like the main one",
    });
});

/**
 * @param {PdfManager} manager
 * @returns {Object}
 */
function snapshotLayout(manager) {
    return {
        groups: manager.store.groupIds.map((groupId) => [
            ...manager.store.groupData[groupId].pageIds,
        ]),
        selected: [...manager.store.selectedPageIds].sort(),
    };
}

test(`Pdf Manager: a double click on Split sends one split`, async () => {
    await mountPdfManager();
    const response = new Deferred();
    mockFetch((input) => {
        if (String(input).includes("/documents/pdf_split")) {
            expect.step("pdf_split");
            return response;
        }
    });
    await contains(".o_pdf_name_display:eq(1)").click();
    await click(".o_pdf_manager_button:eq(0)");
    await click(".o_pdf_manager_button:eq(0)");
    response.resolve(
        new Response(JSON.stringify([101]), {
            headers: { "Content-Type": "application/json" },
        }),
    );
    await animationFrame();
    expect.verifySteps(["pdf_split"]);
});

test(`Pdf Manager: a failed split leaves the groups and the selection as they were`, async () => {
    const manager = await mountPdfManager();
    await contains(".o_pdf_name_display:eq(1)").click();
    await contains(".o_documents_pdf_page_selector:eq(0)").click();
    const before = snapshotLayout(manager);
    expect(before.selected).toHaveLength(5);

    mockPdfSplit({ status: 500 });
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:500"]);
    expect(snapshotLayout(manager)).toEqual(before, {
        message: "a retry splits exactly what the user had chosen",
    });
});

test(`Pdf Manager: an action failing after the split does not leave the split pages behind`, async () => {
    const manager = await mountPdfManager({
        onProcessDocuments: async ({ actionId }) => {
            if (actionId) {
                throw new Error("action failed");
            }
        },
    });
    await contains(".o_pdf_name_display:eq(1)").click();
    const committed = [...manager.store.selectedPageIds];
    expect(committed).toHaveLength(6);

    mockPdfSplit();
    await contains(".o_pdf_manager_button:contains(ACTION1)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:200"]);
    const listed = listedPageIds(manager);
    expect(listed).toHaveLength(6);
    expect(committed.some((pageId) => listed.includes(pageId))).toBe(false, {
        message: "the server already made documents of them: a retry would duplicate",
    });
    expect(".o_notification:contains(action failed)").toHaveCount(1);
});

test(`Pdf Manager: new documents follow the groups' order on screen`, async () => {
    const manager = await mountPdfManager();
    const [firstGroupId] = manager.store.groupIds;
    const firstPageId = manager.store.groupData[firstGroupId].pageIds[0];
    manager.store.toggleSeparator(firstPageId, firstGroupId);
    manager.store.selectAll(true);
    await animationFrame();
    const screenOrder = manager.store.groupIds.map(
        (groupId) => manager.store.groupData[groupId].name,
    );
    expect(screenOrder).toEqual(["yop", "New Group", "blip"]);

    mockFetch((input, init) => {
        if (String(input).includes("/documents/pdf_split")) {
            const newFiles = JSON.parse(init.body.get("new_files"));
            expect.step(newFiles.map((file) => file.name).join(","));
            return new Response(JSON.stringify([101, 102, 103]), {
                headers: { "Content-Type": "application/json" },
            });
        }
    });
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["blip,New Group,yop"]);
});

test(`Pdf Manager: on a small screen, Split from the Action menu splits`, async () => {
    await mountPdfManager({}, SmallScreenPdfManager);
    await contains(".o_pdf_name_display:eq(1)").click();
    mockPdfSplit();
    await contains(".o_documents_pdf_manager_top_bar .dropdown-toggle").click();
    await contains(".o_pdf_manager_menu .dropdown-item:contains(Split)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:200"]);
    expect(".modal:contains(Stay here)").toHaveCount(0, {
        message: "the manager's own menu is not a way out of it",
    });
});

test(`Pdf Manager: answering a dialog opened over the manager keeps the selection`, async () => {
    const manager = await mountPdfManager();
    await contains(".o_pdf_name_display:eq(1)").click();
    const selected = [...manager.store.selectedPageIds];
    expect(selected).toHaveLength(6);

    await contains(".o_pdf_manager_button:contains(Close)").click();
    await contains(".modal button:contains(Stay here)").click();
    await press("Shift");
    await animationFrame();
    expect(manager.store.selectedPageIds).toEqual(selected);
});

test(`Pdf Manager: a file whose pages fail to render is dropped whole`, async () => {
    PdfManagerForTest.renderError = new Error("render failed");
    const manager = await mountPdfManager();
    await animationFrame();
    expect(listedPageIds(manager)).toHaveLength(0, {
        message: "no half-loaded page is left to split",
    });
    expect(pdfTracker.destroyedPdfs).toHaveLength(2);
    expect(".o_notification:contains(Could not open)").toHaveCount(2);
});

test(`Pdf Manager: closing while a pdf loads cancels the load quietly`, async () => {
    let cancelled = 0;
    PdfManagerForTest.pendingLoad = () => {
        const load = new Deferred();
        return {
            promise: load,
            destroy() {
                cancelled++;
                load.reject(new Error("Worker was destroyed"));
            },
        };
    };
    const manager = await mountPdfManager();
    destroy(manager);
    await animationFrame();
    expect(cancelled).toBe(2, { message: "both pending loads are cancelled" });
    expect(".o_notification").toHaveCount(0, {
        message: "a closed splitter reports nothing",
    });
});

test(`Pdf Manager: deleting every page releases the pdfs and closes`, async () => {
    const manager = await mountPdfManager({
        onProcessDocuments: async ({ emptiedDocumentIds }) => {
            expect.step(`process emptied ${emptiedDocumentIds}`);
        },
        close: () => expect.step("close"),
    });
    manager.store.selectAll(true);
    await animationFrame();
    await contains("button[title='Move to trash']").click();
    await contains(".modal-footer .btn-primary:contains(Ok)").click();
    await animationFrame();
    expect.verifySteps(["process emptied 1,2", "close"]);
    expect(pdfTracker.destroyedPdfs).toHaveLength(2, {
        message: "each emptied file's pdf.js document is released",
    });
});

test(`Pdf Manager: thumbnails arriving do not re-render the whole manager`, async () => {
    let managerRenders = 0;
    class CountingPdfManager extends PdfManagerForTest {
        setup() {
            super.setup();
            onPatched(() => managerRenders++);
        }
        // pdf.js renders a page over several frames, not in the same tick
        async _renderCanvas() {
            await animationFrame();
            return super._renderCanvas(...arguments);
        }
    }
    await mountPdfManager({}, CountingPdfManager);
    for (let frame = 0; frame < 14; frame++) {
        await animationFrame();
    }
    expect(".o_pdf_page canvas").toHaveCount(12, {
        message: "every thumbnail is shown",
    });
    expect(managerRenders).toBeLessThan(3, {
        message: `${managerRenders} manager renders for 12 thumbnails`,
    });
});

test(`Pdf Manager: blank pages are measured when the split asks, once each`, async () => {
    let measured = 0;
    class MeasuringPdfManager extends PdfManagerForTest {
        async _isBlankPage(page) {
            measured++;
            return super._isBlankPage(page);
        }
    }
    PdfManagerForTest.blankPages = [3];
    await mountPdfManager({}, MeasuringPdfManager);
    await animationFrame();
    expect(measured).toBe(0, { message: "loading measures nothing" });

    // the groups the files came in are not asked about; the split is
    await press(["shift", "s"]);
    await animationFrame();
    expect(measured).toBe(12);

    await press(["shift", "s"]);
    await contains(".o_dialog .btn-primary").click();
    await animationFrame();
    expect(measured).toBe(12, { message: "a page is measured once" });
});

test(`Pdf Manager: a file dropped from the desktop on a page does not leave the splitter`, async () => {
    await mountPdfManager();
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(
        new File(["%PDF"], "other.pdf", { type: "application/pdf" }),
    );
    const ev = new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer });
    queryOne(".o_pdf_page:first .o_documents_pdf_canvas_wrapper").dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true, {
        message: "the browser would open the dropped file in place of the splitter",
    });
});

test(`Pdf Manager: a gather that fails keeps the grouping and does not leave`, async () => {
    const manager = await mountPdfManager();
    const before = snapshotLayout(manager);
    manager._exitSplitTools(() => expect.step("left"));
    await animationFrame();
    mockPdfSplit({ status: 500 });
    await contains(".modal button:contains('Gather in one document')").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:500"]);
    expect(snapshotLayout(manager)).toEqual(before, {
        message: "the groups the user made are still there to retry",
    });
});

test(`Pdf Manager: splitting on blank pages asks first only when the user has grouped pages`, async () => {
    const manager = await mountPdfManager();
    await contains(".o_documents_pdf_page_viewer").click();
    await press(["shift", "s"]);
    await animationFrame();
    expect(".modal:contains('Split on blank pages')").toHaveCount(0, {
        message: "the groups the files came in are nobody's work to lose",
    });

    const [firstPageId] = manager.store.sortedPageIds;
    manager.store.toggleSeparator(
        firstPageId,
        manager.store.getPage(firstPageId).groupId,
    );
    await press(["shift", "s"]);
    await animationFrame();
    expect(".modal:contains('Split on blank pages')").toHaveCount(1);
});

test(`Pdf Manager: holding a toggle shortcut toggles once`, async () => {
    await mountPdfManager();
    await contains(".o_documents_pdf_page_viewer").click();
    await press(["ctrl", "a"]);
    await animationFrame();
    await press(["ctrl", "s"]);
    await animationFrame();
    const separators = queryAll(".o_pdf_separator_selected").length;
    for (let i = 0; i < 3; i++) {
        window.dispatchEvent(
            new KeyboardEvent("keydown", {
                key: "s",
                ctrlKey: true,
                repeat: true,
                bubbles: true,
            }),
        );
    }
    await animationFrame();
    expect(".o_pdf_separator_selected").toHaveCount(separators, {
        message: "the key held down after the split undoes nothing",
    });
});

test(`Pdf Manager: a split uploads only the local files it takes pages from`, async () => {
    const manager = await mountPdfManager();
    await manager._addFile("extra.pdf", { file: new File(["x"], "extra.pdf") });
    await animationFrame();
    mockFetch((input, init) => {
        if (String(input).includes("/documents/pdf_split")) {
            expect.step(`files: ${init.body.getAll("ufile").length}`);
            return new Response(JSON.stringify([101]), {
                headers: { "Content-Type": "application/json" },
            });
        }
    });
    const [firstPageId] = manager.store.sortedPageIds;
    manager.store.selectAll(false);
    manager.store.setSelected(firstPageId, true);
    await animationFrame();
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["files: 0"]);
});

test(`Pdf Manager: documents are listed in the order given, whichever loads first`, async () => {
    const firstLoaded = new Deferred();
    let calls = 0;
    class SlowFirstPdfManager extends PdfManagerForTest {
        _openPdf(url) {
            calls++;
            if (calls === 1) {
                return {
                    promise: firstLoaded.then(() => makeFakePdf(url)),
                    destroy() {},
                };
            }
            return super._openPdf(url);
        }
    }
    const manager = await mountPdfManager({}, SlowFirstPdfManager);
    await animationFrame();
    firstLoaded.resolve();
    await animationFrame();
    await animationFrame();
    expect(manager.store.groupIds.map((id) => manager.store.getGroup(id).name)).toEqual(
        ["yop", "blip"],
        { message: "a small second document does not jump above a large first one" },
    );
});

test(`Pdf Manager: a file added after the splitter closed opens nothing`, async () => {
    const manager = await mountPdfManager();
    await animationFrame();
    manager.__owl__.app.destroy();
    const opened = manager._pdfDocuments.length;
    await manager._addFile("late.pdf", { file: new File(["x"], "late.pdf") });
    expect(manager._objectUrls).toEqual([], {
        message: "no object URL left unrevoked",
    });
    expect(manager._pdfDocuments).toHaveLength(opened, {
        message: "no pdf.js document left undestroyed",
    });
});

test(`Pdf Manager: deleting a file while its pages render leaves nothing behind`, async () => {
    const rendering = new Deferred();
    class SlowRenderPdfManager extends PdfManagerForTest {
        async _renderCanvas(page, size) {
            await rendering;
            return super._renderCanvas(page, size);
        }
    }
    const manager = await mountPdfManager({}, SlowRenderPdfManager);
    await animationFrame();
    const [firstFileId] = Object.keys(manager._newFiles);
    const pageIds = [...manager._newFiles[firstFileId].pageIds];
    for (const pageId of pageIds) {
        manager._removePage(pageId, { fromFile: true });
    }
    rendering.resolve();
    await animationFrame();
    await animationFrame();
    expect(pageIds.filter((pageId) => pageId in manager.state.pageCanvases)).toEqual(
        [],
        {
            message: "no canvas is kept for a page that is gone",
        },
    );
    expect(".o_notification").toHaveCount(0, {
        message: "a file the user removed is not reported as unreadable",
    });
});

test(`Pdf Manager: a blank-page split asked twice at once measures each page once`, async () => {
    let measured = 0;
    class SlowMeasuringPdfManager extends PdfManagerForTest {
        async _isBlankPage(page) {
            measured++;
            await animationFrame();
            return super._isBlankPage(page);
        }
    }
    const manager = await mountPdfManager({}, SlowMeasuringPdfManager);
    await animationFrame();
    await Promise.all([manager._splitWhitePages(), manager._splitWhitePages()]);
    expect(measured).toBe(12);
});

test(`Pdf Manager: a page with ink is not asked for its text`, async () => {
    const page = {
        getTextContent: async () => {
            expect.step("text extracted");
            return { items: [] };
        },
    };
    const inked = { _hasBlankGraphics: () => false };
    expect(await PdfManager.prototype._isBlankPage.call(inked, page, {})).toBe(false);
    expect.verifySteps([]);
    const white = { _hasBlankGraphics: () => true };
    expect(await PdfManager.prototype._isBlankPage.call(white, page, {})).toBe(true);
    expect.verifySteps(["text extracted"]);
});

test(`Pdf Manager: Escape while a preview renders cancels the preview`, async () => {
    const previewRendered = new Deferred();
    class SlowPreviewPdfManager extends PdfManagerForTest {
        async _renderCanvas(page, size) {
            if (size.width > 160) {
                await previewRendered;
            }
            return super._renderCanvas(page, size);
        }
    }
    const manager = await mountPdfManager({}, SlowPreviewPdfManager);
    await animationFrame();
    const [pageId] = manager.store.sortedPageIds;
    const selectedBefore = manager.store.selectedPageIds.length;
    manager.onClickPage(pageId);
    await press("escape");
    previewRendered.resolve();
    await animationFrame();
    expect(manager.state.viewedPage).toBe(undefined, {
        message: "the preview Escape closed does not open when its page arrives",
    });
    expect(manager.store.selectedPageIds).toHaveLength(selectedBefore, {
        message: "Escape closed the preview, it did not unselect everything",
    });
    expect(manager.store.focusedPage).toBe(pageId, {
        message: "the page asked stays focused",
    });
});

test(`Pdf Manager: a rendered page releases what pdf.js kept to draw it`, async () => {
    const page = {
        getViewport: () => ({ width: 100, height: 140, rotation: 0 }),
        render: () => ({ promise: Promise.resolve() }),
        cleanup: () => expect.step("cleanup"),
    };
    await PdfManager.prototype._renderCanvas.call({}, page, {
        width: 160,
        height: 230,
    });
    expect.verifySteps(["cleanup"]);
});

test(`Pdf Manager: deleting the last pages trashes only the documents none of whose pages were split`, async () => {
    const manager = await mountPdfManager({
        onProcessDocuments: async ({ emptiedDocumentIds }) => {
            if (emptiedDocumentIds) {
                expect.step(`emptied ${emptiedDocumentIds}`);
            }
        },
    });
    const yopFileId = Object.keys(manager._newFiles).find(
        (fileId) => manager._newFiles[fileId].documentId === 1,
    );
    manager.store.selectAll(false);
    for (const pageId of manager._newFiles[yopFileId].pageIds) {
        manager.store.setSelected(pageId, true);
    }
    mockPdfSplit();
    await contains(".o_pdf_manager_button:eq(0)").click();
    await animationFrame();
    expect.verifySteps(["pdf_split:200"]);
    manager.store.selectAll(true);
    await animationFrame();
    await contains("button[title='Move to trash']").click();
    await contains(".modal-footer .btn-primary:contains(Ok)").click();
    await animationFrame();
    expect.verifySteps(["emptied 2"]);
});

test(`Pdf Manager: the area selection takes a page on the move that reaches it`, async () => {
    await mountPdfManager();
    await press(["ctrl", "a"]);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(0);

    const viewer = queryOne(".o_documents_pdf_page_viewer");
    // short enough for pages to wait below the fold
    Object.assign(viewer.style, { flex: "none", height: "300px", width: "400px" });
    await animationFrame();
    const bounds = viewer.getBoundingClientRect();
    const page = queryAll(".o_pdf_page")[0].getBoundingClientRect();
    const mouse = (type, x, y) =>
        viewer.dispatchEvent(
            new MouseEvent(type, { bubbles: true, button: 0, clientX: x, clientY: y }),
        );
    mouse("mousedown", bounds.left + 2, bounds.top + 2);
    await animationFrame();
    // one move, as a quick drag sends: nothing rendered in between
    mouse("mousemove", page.left + page.width / 2, page.top + page.height / 2);
    await animationFrame();
    expect(".o_pdf_page_selected").toHaveCount(1, {
        message:
            "the rectangle is the pointer's, not the box rendered one move earlier",
    });

    const below = queryAll(".o_pdf_page").find(
        (card) => card.getBoundingClientRect().top > bounds.bottom,
    );
    expect(below).not.toBe(undefined, { message: "some page starts below the fold" });
    viewer.scrollTop += below.getBoundingClientRect().bottom - bounds.bottom + 10;
    viewer.dispatchEvent(new Event("scroll"));
    await animationFrame();
    expect(`.o_pdf_page[data-id='${below.dataset.id}']`).toHaveClass(
        "o_pdf_page_selected",
        {
            message: "the held selection follows the pages scrolled under the pointer",
        },
    );
    mouse("mouseup", 0, 0);
});
