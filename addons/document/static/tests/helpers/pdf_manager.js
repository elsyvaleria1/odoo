import { PdfManager } from "@document/owl/components/pdf_manager/pdf_manager";
import { beforeEach, expect } from "@odoo/hoot";
import { animationFrame, mockFetch } from "@odoo/hoot-mock";
import { mountWithCleanup, patchWithCleanup } from "@web/../tests/web_test_helpers";

/** What the doubles released during the current test. */
export const pdfTracker = { destroyedPdfs: [], revokedUrls: [] };

/** Resets the doubles before each test of the calling file. */
export function usePdfManagerDoubles() {
    beforeEach(() => {
        pdfTracker.destroyedPdfs = [];
        pdfTracker.revokedUrls = [];
        PdfManagerForTest.pdfError = null;
        PdfManagerForTest.pendingLoad = null;
        PdfManagerForTest.renderError = null;
        PdfManagerForTest.numPages = 6;
        PdfManagerForTest.blankPages = [];
        patchWithCleanup(URL, {
            createObjectURL(file) {
                return `blob:mock/${file?.name || "anonymous"}`;
            },
            revokeObjectURL(url) {
                pdfTracker.revokedUrls.push(url);
            },
        });
    });
}

/** Shaped like pdf.js 6's PDFDocumentProxy: no destroy() of its own. */
export function makeFakePdf(url) {
    const pdf = {
        url,
        getPage: (number) => ({ number }),
        numPages: PdfManagerForTest.numPages,
        loadingTask: { destroy: () => pdfTracker.destroyedPdfs.push(pdf) },
    };
    return pdf;
}

export class PdfManagerForTest extends PdfManager {
    static pendingLoad = null;
    static renderError = null;
    static pdfError = null;
    static numPages = 6;
    static blankPages = [];

    async _loadAssets() {}
    _openPdf(url) {
        if (this.constructor.pendingLoad) {
            return this.constructor.pendingLoad();
        }
        if (this.constructor.pdfError) {
            return { promise: Promise.reject(this.constructor.pdfError), destroy() {} };
        }
        return { promise: Promise.resolve(makeFakePdf(url)), destroy() {} };
    }
    async _isBlankPage(page) {
        return this.constructor.blankPages.includes(page.number);
    }
    async _renderCanvas(page, { width, height }) {
        if (this.constructor.renderError && page.number === 3) {
            throw this.constructor.renderError;
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        return canvas;
    }
}

export class SmallScreenPdfManager extends PdfManagerForTest {
    setup() {
        super.setup();
        this.ui = Object.create(this.ui, { isSmall: { value: true } });
    }
}

export async function mountPdfManager(props = {}, ManagerClass = PdfManagerForTest) {
    const manager = await mountWithCleanup(ManagerClass, {
        props: {
            documents: [
                {
                    id: 1,
                    name: "yop",
                    mimetype: "application/pdf",
                    available_embedded_actions_ids: [1, 2],
                },
                {
                    id: 2,
                    name: "blip",
                    mimetype: "application/pdf",
                    available_embedded_actions_ids: [1],
                },
            ],
            embeddedActions: [
                { id: 1, name: "action1" },
                { id: 2, name: "action2" },
            ],
            onProcessDocuments: async () => {},
            close: () => {},
            ...props,
        },
    });
    // the documents' pages are added from the mount effect, a frame later
    await animationFrame();
    return manager;
}

/**
 * @param {PdfManager} manager
 * @returns {String[]}
 */
export function listedPageIds(manager) {
    return manager.store.groupIds.flatMap((groupId) => [
        ...manager.store.groupData[groupId].pageIds,
    ]);
}

export function mockPdfSplit({ status = 200, documentIds = [101] } = {}) {
    mockFetch((input) => {
        if (String(input).includes("/documents/pdf_split")) {
            expect.step(`pdf_split:${status}`);
            if (status !== 200) {
                return new Response(null, { status });
            }
            return new Response(JSON.stringify(documentIds), {
                status,
                headers: { "Content-Type": "application/json" },
            });
        }
    });
}
