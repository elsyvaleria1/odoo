import { DocumentsKanbanModel } from "@document/views/kanban/document_kanban_model";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame, Deferred } from "@odoo/hoot-mock";
import { defineModels, onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";

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
 * @returns {Promise<{contexts: Object[], getModel: () => Object}>}
 */
async function mountWithSearchReadSpy(serverData) {
    await makeDocumentsMockEnv({ serverData });
    const contexts = [];
    onRpc("document.document", "web_search_read", ({ kwargs }) => {
        contexts.push(kwargs.context || {});
    });
    let model;
    patchWithCleanup(DocumentsKanbanModel.prototype, {
        setup() {
            super.setup(...arguments);
            model = this;
        },
    });
    await mountDocumentsKanbanView();
    return { contexts, getModel: () => model };
}

test("the initial load carries skip_res_field_check", async () => {
    const { contexts } = await mountWithSearchReadSpy();

    expect(contexts.length).toBeGreaterThan(0, {
        message: "the view issued at least one search_read",
    });
    expect(contexts.at(0).skip_res_field_check).toBe(true);
});

test("an argument-less reload still carries skip_res_field_check", async () => {
    const { contexts, getModel } = await mountWithSearchReadSpy();
    const initialCount = contexts.length;

    await getModel().load();

    expect(contexts.length).toBeGreaterThan(initialCount, {
        message: "the bare reload hit the server",
    });
    expect(contexts.at(-1).skip_res_field_check).toBe(true, {
        message: "every document.document read is flagged, not just the mount one",
    });
});

test("the flag survives a load whose params carry their own context", async () => {
    const { contexts, getModel } = await mountWithSearchReadSpy();

    await getModel().load({ context: { lang: "en_US" } });

    expect(contexts.at(-1).skip_res_field_check).toBe(true);
    expect(contexts.at(-1).lang).toBe("en_US", {
        message: "the caller's own context keys are preserved",
    });
});

test("load() does not write into the object it is given", async () => {
    const { getModel } = await mountWithSearchReadSpy();
    const callerOwned = { context: { some_key: 1 } };

    await getModel().load(callerOwned);

    expect(callerOwned.context).toEqual(
        { some_key: 1 },
        { message: "the caller's context object is left untouched" },
    );
});

test("a change reloads the documents once", async () => {
    const { contexts, getModel } = await mountWithSearchReadSpy();
    const before = contexts.length;

    await getModel()._notifyChange();
    await animationFrame();

    expect(contexts.length - before).toBe(1, {
        message: "one search_read per change, not one per reload trigger",
    });
});

test("a load overtaken by a newer one leaves the newer one's state alone", async () => {
    const { getModel } = await mountWithSearchReadSpy();
    const model = getModel();
    const slow = new Deferred();
    let calls = 0;
    onRpc("document.document", "web_search_read", async () => {
        if (++calls === 1) {
            await slow;
        }
    });
    let closedPreviews = 0;
    model.viewContext.documentsView.bus.addEventListener(
        "documents-close-preview",
        () => closedPreviews++,
    );

    const older = model.load();
    await model.load();
    expect(closedPreviews).toBe(1);
    const root = model.root;
    slow.resolve();
    await older;

    expect(model.root).toBe(root);
    expect(closedPreviews).toBe(1, {
        message: "the superseded load does not act as if it had loaded",
    });
});

test("a changed version reloads that document alone", async () => {
    const { contexts, getModel } = await mountWithSearchReadSpy(
        getDocumentsTestServerModelsData([
            makeDocumentRecordData(2, "Contract.pdf", { file_size: 1000000 }),
            makeDocumentRecordData(3, "Other.pdf"),
        ]),
    );
    const model = getModel();
    const record = model.root.records.find((r) => r.resId === 2);
    record.selected = true;
    const reads = [];
    onRpc("document.document", "web_read", ({ args }) => {
        reads.push(args[0]);
    });
    let onVersionsChanged;
    patchWithCleanup(model.documentService, {
        openDialogManageVersions(documentId, callback) {
            expect.step(`dialog ${documentId}`);
            onVersionsChanged = callback;
        },
    });
    const searchReads = contexts.length;

    model.onManageVersions();
    await onVersionsChanged();

    expect.verifySteps([`dialog ${record.resId}`]);
    expect(reads).toEqual([[record.resId]]);
    expect(contexts.length).toBe(searchReads, {
        message: "neither the page nor the folder tree is fetched again",
    });
});
