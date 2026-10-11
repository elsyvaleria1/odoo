import { documentsClientThumbnailService } from "@document/views/helper/document_client_thumbnail_service";
import { getImageThumbnail } from "@document/views/helper/document_client_thumbnail_service_utils";
import { describe, expect, test } from "@odoo/hoot";
import {
    defineModels,
    getService,
    makeMockEnv,
    makeServerError,
    onRpc,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import { Deferred } from "@web/core/utils/concurrency";

import {
    DocumentsModels,
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
    mimetypeExamplesBase64,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { mountDocumentsKanbanView } from "./helpers/views/kanban.js";

describe.current.tags("desktop");

defineModels(DocumentsModels);

function drainThumbnailQueue() {
    return getService("documents_client_thumbnail").enqueueRecords([]);
}

async function mountWithPendingThumbnail() {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Test Document", {
            thumbnail_status: "client_generated",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "image/webp",
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 2, name: "binary" }];
    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(documentsClientThumbnailService, {
        _getLoadedImage() {
            const img = new Image();
            const imagePromise = new Deferred();
            img.onload = () => imagePromise.resolve(img);
            img.src = "data:image/webp;base64," + mimetypeExamplesBase64.WEBP;
            return imagePromise;
        },
    });
    await mountDocumentsKanbanView();
}

test("a failing update_thumbnail RPC does not surface to the user", async () => {
    onRpc("/documents/document/3/update_thumbnail", () => {
        expect.step("update_thumbnail attempted");
        throw makeServerError({ message: "thumbnail storage is unavailable" });
    });

    await mountWithPendingThumbnail();
    await drainThumbnailQueue();

    expect.verifySteps(["update_thumbnail attempted"]);
    expect(".o_kanban_record:contains('Test Document')").toHaveCount(1, {
        message: "the view is still usable after the thumbnail failed",
    });
});

test("a thumbnail the server is rendering is left to the server", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Report", {
            thumbnail_status: "pending",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "application/pdf",
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 2, name: "report.pdf" }];
    onRpc("/documents/document/3/update_thumbnail", () => {
        expect.step("update_thumbnail attempted");
        return true;
    });

    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await drainThumbnailQueue();

    expect.verifySteps([]);
});

test("a thumbnail failure does not stop the queue for later records", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Doc A", {
            thumbnail_status: "client_generated",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "image/webp",
        }),
        makeDocumentRecordData(4, "Doc B", {
            thumbnail_status: "client_generated",
            attachment_id: 3,
            folder_id: 1,
            mimetype: "image/webp",
        }),
    ]);
    serverData["ir.attachment"] = [
        { id: 2, name: "a" },
        { id: 3, name: "b" },
    ];
    onRpc("/documents/document/3/update_thumbnail", () => {
        expect.step("A failed");
        throw makeServerError({ message: "nope" });
    });
    onRpc("/documents/document/4/update_thumbnail", () => {
        expect.step("B stored");
        return true;
    });

    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(documentsClientThumbnailService, {
        _getLoadedImage() {
            const img = new Image();
            const imagePromise = new Deferred();
            img.onload = () => imagePromise.resolve(img);
            img.src = "data:image/webp;base64," + mimetypeExamplesBase64.WEBP;
            return imagePromise;
        },
    });
    await mountDocumentsKanbanView();
    await drainThumbnailQueue();

    expect.verifySteps(["A failed", "B stored"]);
});

test("a PDF the route refuses is marked failed, not retried forever", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Broken PDF", {
            thumbnail_status: "client_generated",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "application/pdf",
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 2, name: "broken" }];
    let stored;
    onRpc("/documents/document/3/update_thumbnail", async (request) => {
        stored = (await request.json()).params.thumbnail;
        expect.step("update_thumbnail");
        return true;
    });
    await makeDocumentsMockEnv({ serverData });
    patchWithCleanup(documentsClientThumbnailService, {
        _getPdfThumbnail() {
            return { thumbnail: undefined, isPdfValid: false, pdfEnabled: true };
        },
    });
    await mountDocumentsKanbanView();
    await drainThumbnailQueue();

    expect.verifySteps(["update_thumbnail"]);
    expect(stored).toBe(false, { message: "stored as a definitive failure" });
});

test("an image thumbnail is read without logging a view, blocked or not", async () => {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(3, "Blocked Image", {
            thumbnail_status: "client_generated",
            attachment_id: 2,
            folder_id: 1,
            mimetype: "image/webp",
            access_token: "accessTokenImage",
            is_download_blocked: true,
        }),
    ]);
    serverData["ir.attachment"] = [{ id: 2, name: "binary" }];
    onRpc("/web/content/document.document/3/raw", () => {
        expect.step("web/content");
        return new Response(Uint8Array.fromBase64(mimetypeExamplesBase64.WEBP), {
            headers: { "Content-Type": "image/webp" },
        });
    });
    onRpc("/documents/content/*", () => {
        expect.step("documents/content");
    });
    onRpc("/documents/document/3/update_thumbnail", async (request) => {
        const { params } = await request.json();
        expect.step(params.thumbnail ? "stored" : "not stored");
        return true;
    });

    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await drainThumbnailQueue();

    expect.verifySteps(["web/content", "stored"]);
});

test("a transparent image makes a white thumbnail, not a black one", async () => {
    const source = document.createElement("canvas");
    source.width = source.height = 4;
    const { thumbnail } = await getImageThumbnail(source, 200, 140);
    const img = new Image();
    img.src = `data:image/jpeg;base64,${thumbnail}`;
    await img.decode();
    const probe = document.createElement("canvas");
    probe.width = probe.height = 4;
    const context = probe.getContext("2d");
    context.drawImage(img, 0, 0);
    const [red, green, blue] = context.getImageData(1, 1, 1, 1).data;
    expect(Math.min(red, green, blue)).toBeGreaterThan(240);
});

test("an image without intrinsic size gives no thumbnail rather than an empty one", async () => {
    const { thumbnail } = await getImageThumbnail({ width: 0, height: 0 }, 200, 140);
    expect(thumbnail).toBe(false);
});

test("a pdf.js that failed to load marks no document as broken", async () => {
    onRpc("/documents/document/9/update_thumbnail", () => {
        expect.step("update_thumbnail");
    });
    await makeMockEnv();
    patchWithCleanup(documentsClientThumbnailService, {
        _getPdfThumbnail: async () => ({
            thumbnail: undefined,
            isPdfValid: false,
            pdfEnabled: false,
        }),
    });
    const record = {
        resId: 9,
        isPdf: () => true,
        data: {
            thumbnail_status: "client_generated",
            user_permission: "edit",
            mimetype: "application/pdf",
        },
    };
    await getService("documents_client_thumbnail").enqueueRecords([record]);
    expect.verifySteps([]);
    expect(record.data.thumbnail_status).toBe("client_generated", {
        message: "left to be generated once pdf.js loads",
    });
});
