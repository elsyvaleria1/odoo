import { DocumentFile } from "@document/attachments/document_file";
import { DocumentsFileViewer } from "@document/attachments/document_file_viewer";
import { describe, expect, test } from "@odoo/hoot";
import { press, waitFor, waitForNone } from "@odoo/hoot-dom";
import { animationFrame } from "@odoo/hoot-mock";
import { Component, proxy, xml } from "@odoo/owl";
import {
    contains,
    defineActions,
    defineModels,
    getService,
    mockService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { WebClient } from "@web/webclient/webclient";

import { DocumentsModels, getDocumentsTestServerModelsData } from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { basicDocumentsKanbanArch } from "./helpers/views/kanban.js";
import { getEnrichedSearchArch } from "./helpers/views/search.js";

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

async function mountWithPreviewableDocument({ mimetype = "image/webp" } = {}) {
    const serverData = getDocumentsTestServerModelsData([
        {
            attachment_id: 1,
            id: 2,
            name: "text_file.txt",
            user_permission: "edit",
            mimetype,
        },
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "text_file.txt", mimetype }];
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    return getService("document.document");
}

test("the preview releases documentList when it closes", async () => {
    const documentService = await mountWithPreviewableDocument();

    expect(documentService.documentList).toBe(undefined, {
        message: "nothing is published before a preview is opened",
    });

    await contains(
        ".o_kanban_record:contains('text_file.txt') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");
    expect(documentService.documentList).not.toBe(null);
    expect(documentService.documentList.documents.length).toBeGreaterThan(0);

    await press("escape");
    await waitForNone(".o-FileViewer");

    expect(documentService.documentList).toBe(null, {
        message:
            "closing the preview releases the controller closures and the previewed records",
    });
});

test("closing twice is a no-op", async () => {
    const documentService = await mountWithPreviewableDocument();

    await contains(
        ".o_kanban_record:contains('text_file.txt') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");
    await press("escape");
    await waitForNone(".o-FileViewer");

    await getService("action").currentController.props.resModel;
    expect(documentService.documentList).toBe(null);
    expect(() => documentService.bus.trigger("DOCUMENT_RELOAD")).not.toThrow();
});

test("a text preview fetches its content once, and not again on close", async () => {
    onRpc("/web/content/2", () => {
        expect.step("content");
        return "plain <text>";
    });
    await mountWithPreviewableDocument({ mimetype: "text/plain" });
    await contains(
        ".o_kanban_record:contains('text_file.txt') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer pre.o_text");
    expect.verifySteps(["content"]);
    expect(".o-FileViewer pre.o_text").toHaveText("plain <text>", {
        message: "shown as text, escaped by the template",
    });

    await press("escape");
    await waitForNone(".o-FileViewer");
    expect.verifySteps([]);
});

test("a preview reopened on another list shows the file asked for", async () => {
    const file = (id, name) => ({
        id,
        name,
        mimetype: "image/png",
        isImage: true,
        defaultSource: `/img/${id}`,
    });
    const [a, b, c] = [file(1, "a.png"), file(2, "b.png"), file(3, "c.png")];
    mockService("document.document", () => ({
        documentList: {
            documents: [{ record: {} }, { record: {} }, { record: {} }],
            folderId: false,
            onDeleteCallback() {},
        },
        selectionActions: { provider: null },
        rightPanelReactive: { visible: false },
        setPreviewedDocument() {},
        userIsInternal: true,
    }));
    class Parent extends Component {
        static components = { DocumentsFileViewer };
        static props = {};
        static template = xml`<DocumentsFileViewer files="this.state.files" startIndex="this.state.startIndex" modal="false"/>`;
        setup() {
            this.state = proxy({ files: [a, b], startIndex: 0 });
        }
    }
    const parent = await mountWithCleanup(Parent);
    expect(".o-FileViewer-header").toHaveText(/a\.png/);
    parent.state.files = [c, a, b];
    parent.state.startIndex = 2;
    await animationFrame();
    expect(".o-FileViewer-header").toHaveText(/b\.png/, {
        message: "index 2 of the new list: the old list has no index 2",
    });
    parent.state.files = [b, c];
    parent.state.startIndex = 1;
    await animationFrame();
    expect(".o-FileViewer-header").toHaveText(/c\.png/, {
        message: "the file asked for in a list that shrank",
    });
    parent.state.files = [c, b];
    parent.state.startIndex = 1;
    await animationFrame();
    expect(".o-FileViewer-header").toHaveText(/b\.png/, {
        message: "same start index as before, another file: the one asked for",
    });
});

test("a preview adds nothing to the mail store's attachments", async () => {
    await mountWithPreviewableDocument();
    const attachments = getService("mail.store")["ir.attachment"].records;
    const before = Object.keys(attachments).length;
    await contains(
        ".o_kanban_record:contains('text_file.txt') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");
    expect(Object.keys(attachments)).toHaveLength(before, {
        message: "a chatter upload's temporary negative id cannot meet a preview",
    });
});

/** @param {Object} data */
function makeFile(data) {
    return new DocumentFile({ id: 7, name: "f", access_token: "tok", ...data });
}

test("DocumentFile routes: content through the document, PDF through its token", () => {
    expect(makeFile({ mimetype: "image/png" }).defaultSource).toMatch(
        /\/web\/image\/7\?.*model=document\.document/,
    );
    expect(makeFile({ mimetype: "text/plain" }).defaultSource).toMatch(
        /\/web\/content\/7\?/,
    );
    expect(makeFile({ mimetype: "application/pdf" }).defaultSource).toBe(
        `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(
            "/documents/content/tok?download=0",
        )}#pagemode=none`,
    );
    expect(makeFile({ attachment_id: { id: 12 } }).subtitlesUrl).toBe(
        "/speech/attachment/12/subtitles.vtt",
    );
    expect(makeFile({}).subtitlesUrl).toBe("");
});

test("DocumentFile shows code and plain text as text, HTML and JSON as pages", () => {
    const textual = (mimetype) => makeFile({ mimetype }).isTextual;
    expect(textual("text/plain")).toBe(true);
    expect(textual("application/javascript")).toBe(true, {
        message: "previewable, and was a blank pane",
    });
    expect(textual("application/xml")).toBe(true);
    expect(textual("text/html")).toBe(false);
    expect(textual("text/csv")).toBe(false);
    expect(makeFile({ mimetype: "application/json" }).isJson).toBe(true);
    expect(makeFile({ mimetype: "application/documents-email" }).isEmail).toBe(true);
});

test("Escape inside a PDF reached by Next closes the preview", async () => {
    const serverData = getDocumentsTestServerModelsData([
        { attachment_id: 1, id: 2, name: "a_image.webp", mimetype: "image/webp" },
        { attachment_id: 3, id: 3, name: "b_doc.pdf", mimetype: "application/pdf" },
    ]);
    serverData["ir.attachment"] = [
        { id: 1, name: "a_image.webp", mimetype: "image/webp" },
        { id: 3, name: "b_doc.pdf", mimetype: "application/pdf" },
    ];
    DocumentsModels.DocumentsDocument._views = {
        kanban: basicDocumentsKanbanArch,
        [["search", false]]: getEnrichedSearchArch(),
    };
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(WebClient);
    await getService("action").doAction(1);
    await contains(
        ".o_kanban_record:contains('a_image.webp') [name='document_preview']",
    ).click();
    await waitFor(".o-FileViewer");
    const pdfShown = () =>
        document.querySelector(".o-FileViewer iframe.o-FileViewer-view");
    if (!pdfShown()) {
        await press("arrowright");
    }
    const iframe = await waitFor(".o-FileViewer iframe.o-FileViewer-view");
    await new Promise((resolve) =>
        iframe.contentDocument?.readyState === "complete"
            ? resolve()
            : iframe.addEventListener("load", resolve, { once: true }),
    );
    await animationFrame();
    iframe.contentDocument.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Escape" }),
    );
    await waitForNone(".o-FileViewer");
});
