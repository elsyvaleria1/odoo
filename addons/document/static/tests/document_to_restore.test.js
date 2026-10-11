import { DocumentsKanbanModel } from "@document/views/kanban/document_kanban_model";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred } from "@odoo/hoot-mock";
import {
    defineModels,
    getService,
    mockService,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";

import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { mountDocumentsKanbanView } from "./helpers/views/kanban.js";

describe.current.tags("desktop");

defineModels(DocumentsModels);

/**
 * @returns {Promise<Object>}
 */
async function mountRestoring(restoreId, count = 4) {
    const records = [];
    for (let i = 1; i <= count; i++) {
        records.push(makeDocumentRecordData(i, `Doc ${i}`));
    }
    DocumentsModels.DocumentsDocument._records = records;
    await makeDocumentsMockEnv();
    getService("document.document").requestFocus(restoreId);
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await mountDocumentsKanbanView();
    return model;
}

test("the requested document is hoisted to the top and starts selected", async () => {
    const model = await mountRestoring(3);

    expect(model.root.records[0].resId).toBe(3, {
        message: "the target is moved to the head of the first page",
    });
    expect(model.root.records[0].selected).toBe(true);
    expect(model.root.selection.map((r) => r.resId)).toEqual([3]);
});

test("the one-shot request is settled by the load that shows it", async () => {
    await mountRestoring(2);
    expect(getService("document.document").focusRequest).toBe(null);
});

test("nothing is selected when no document was requested", async () => {
    DocumentsModels.DocumentsDocument._records = [
        makeDocumentRecordData(1, "Doc 1"),
        makeDocumentRecordData(2, "Doc 2"),
    ];
    await makeDocumentsMockEnv();
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await mountDocumentsKanbanView();

    expect(model.root.selection).toHaveLength(0);
    expect(model.root.records[0].resId).toBe(1, { message: "natural order is kept" });
});

test("an inaccessible document warns instead of selecting something else", async () => {
    const notifications = [];
    mockService("notification", {
        add: (message, options) => notifications.push({ message, options }),
    });
    const model = await mountRestoring(999);

    expect(model.root.selection).toHaveLength(0, {
        message: "no stand-in record is selected",
    });
    expect(notifications.map((n) => n.message)).toInclude(
        "Document not found or inaccessible.",
    );
});

test("a tab opened on a document keeps the search defaults of its later views", async () => {
    DocumentsModels.DocumentsDocument._records = [makeDocumentRecordData(2, "Doc 2")];
    await makeDocumentsMockEnv();
    const documentService = getService("document.document");
    documentService.requestFocus(2);

    await mountDocumentsKanbanView();
    expect(documentService.focusRequest).toBe(null, {
        message: "the first view took the document the tab was opened on",
    });

    await mountDocumentsKanbanView({ context: { search_default_activities_today: 1 } });
    expect(".o_searchview_facet:contains('Today Activities')").toHaveCount(1, {
        message: "a later view's default filter is not stripped",
    });
});

test("a picker opened first leaves the request to the view it was made for", async () => {
    DocumentsModels.DocumentsDocument._records = [1, 2, 3].map((i) =>
        makeDocumentRecordData(i, `Doc ${i}`),
    );
    await makeDocumentsMockEnv();
    const documentService = getService("document.document");
    documentService.requestFocus(3);
    const models = [];
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            models.push(this);
        },
    });

    await mountDocumentsKanbanView({ context: { documents_view_secondary: true } });
    expect(models[0].root.selection).toHaveLength(0);
    expect(documentService.focusRequest).not.toBe(null, {
        message: "the picker did not take the tab's request",
    });

    await mountDocumentsKanbanView();
    expect(models[1].root.records[0].resId).toBe(3);
    expect(models[1].root.selection.map((r) => r.resId)).toEqual([3]);
});

test("a document an action opens the app on is brought forward and selected", async () => {
    const records = [1, 2, 3].map((i) => makeDocumentRecordData(i, `Doc ${i}`));
    DocumentsModels.DocumentsDocument._records = records;
    await makeDocumentsMockEnv();
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });

    await mountDocumentsKanbanView({ context: { documents_init_document_id: 2 } });

    expect(model.root.records[0].resId).toBe(2);
    expect(model.root.selection.map((r) => r.resId)).toEqual([2]);
});

test("a preview asked with the document opens once it is rendered, once", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(5, "Doc 5"),
        makeDocumentRecordData(6, "Photo.png", {
            mimetype: "image/png",
            attachment_id: 1,
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "Photo.png" }];
    await makeDocumentsMockEnv({ serverData });
    const documentService = getService("document.document");
    documentService.requestFocus(6, { openPreview: true });
    patchWithCleanup(documentService, {
        setPreviewedDocument(document) {
            if (document) {
                expect.step(`preview ${document.record.resId}`);
            }
            return super.setPreviewedDocument(...arguments);
        },
    });

    await mountDocumentsKanbanView();
    await animationFrame();

    expect.verifySteps(["preview 6"]);
});

test("a load superseded while it fetches the requested document leaves the request to the next", async () => {
    DocumentsModels.DocumentsDocument._records = [1, 2, 3, 4].map((i) =>
        makeDocumentRecordData(i, `Doc ${i}`),
    );
    await makeDocumentsMockEnv();
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await mountDocumentsKanbanView();
    const documentService = getService("document.document");
    const fetched = new Deferred();
    onRpc("document.document", "web_search_read", async ({ kwargs }) => {
        if (JSON.stringify(kwargs.domain).includes('["id","=",3]')) {
            await fetched;
        }
    });
    documentService.requestFocus(3);

    const stale = model.load({ domain: [["id", "!=", 3]] }).catch(() => {});
    await animationFrame();
    await model.load();
    fetched.resolve();
    await stale;

    expect(model.root.records[0].resId).toBe(3, {
        message: "the load that published showed the document",
    });
    expect(model.root.selection.map((r) => r.resId)).toEqual([3]);
    expect(documentService.focusRequest).toBe(null);
});

test("the preview asked with the document is an ordinary one: a load replacing its records closes it", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(6, "Photo.png", {
            mimetype: "image/png",
            attachment_id: 1,
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 1, name: "Photo.png" }];
    await makeDocumentsMockEnv({ serverData });
    const documentService = getService("document.document");
    documentService.requestFocus(6, { openPreview: true });
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await mountDocumentsKanbanView();
    await animationFrame();
    expect(documentService.rightPanelReactive.previewedDocument?.record.resId).toBe(6);

    await model.load();

    expect(documentService.rightPanelReactive.previewedDocument).toBe(null, {
        message: "no preview is kept on a record of the replaced root",
    });
});
