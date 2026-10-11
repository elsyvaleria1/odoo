import { defineDocumentsModels } from "@document/../tests/document_test_helpers";
import { PdfManager } from "@document/owl/components/pdf_manager/pdf_manager";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { contains, onRpc, patchWithCleanup } from "@web/../tests/web_test_helpers";

import {
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "./helpers/data.js";
import { makeDocumentsMockEnv } from "./helpers/model.js";
import { mountDocumentsKanbanView } from "./helpers/views/kanban.js";

describe.current.tags("desktop");

defineDocumentsModels();

async function openSplitter() {
    let managerProps;
    patchWithCleanup(PdfManager.prototype, {
        setup() {
            super.setup();
            managerProps = this.props;
        },
        async _loadAssets() {},
        _openPdf(url) {
            const loadingTask = { destroy() {} };
            const pdf = {
                url,
                getPage: (number) => ({ number }),
                numPages: 2,
                loadingTask,
            };
            return { promise: Promise.resolve(pdf), destroy() {} };
        },
        async _isBlankPage() {
            return false;
        },
        async _renderCanvas(page, { width, height }) {
            const canvas = document.createElement("canvas");
            canvas.width = width;
            canvas.height = height;
            return canvas;
        },
    });
    onRpc("document.document", "unlink", ({ args }) => {
        expect.step(`unlink:${args[0]}`);
        return true;
    });
    onRpc("document.document", "action_archive", ({ args }) => {
        expect.step(`action_archive:${args[0]}`);
        return true;
    });
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(2, "scan.pdf", {
            folder_id: 1,
            mimetype: "application/pdf",
        }),
    ]);
    await makeDocumentsMockEnv({ serverData });
    await mountDocumentsKanbanView();
    await contains(".o_kanban_record:contains('scan.pdf')").click();
    await contains(".o_cp_action_menus button").click();
    await contains(".o-dropdown--menu .o-dropdown-item:contains('Split PDF')").click();
    await animationFrame();
    return managerProps;
}

test("closing the splitter after a split purges no original", async () => {
    const props = await openSplitter();
    await props.onProcessDocuments({ documentIds: [99], exit: true });
    await props.close();
    await animationFrame();
    expect.verifySteps([]);
});

test("removing every page sends the original to the trash, not past it", async () => {
    const props = await openSplitter();
    await props.onProcessDocuments({ emptiedDocumentIds: [2] });
    await props.close();
    await animationFrame();
    expect.verifySteps(["action_archive:2"]);
});

test("while the splitter stays open, an action's notification is shown", async () => {
    onRpc("document.document", "action_execute_embedded_action", ({ kwargs }) => {
        expect.step(`execute ${kwargs.context.active_ids}`);
        return {
            type: "ir.actions.client",
            tag: "display_notification",
            params: { message: "Sent to Finance", type: "success" },
        };
    });
    const props = await openSplitter();
    await props.onProcessDocuments({ documentIds: [99], actionId: 5, exit: false });
    await animationFrame();
    expect.verifySteps(["execute 99"]);
    expect(".o_notification:contains(Sent to Finance)").toHaveCount(1);
    expect(".o_documents_pdf_manager").toHaveCount(1);
});

test("while the splitter stays open, an action that would navigate away is not run", async () => {
    onRpc("document.document", "action_execute_embedded_action", () => ({
        type: "ir.actions.act_window",
        res_model: "document.document",
        views: [[false, "form"]],
        res_id: 2,
    }));
    const props = await openSplitter();
    await props.onProcessDocuments({ documentIds: [99], actionId: 5, exit: false });
    await animationFrame();
    expect(".o_documents_pdf_manager").toHaveCount(1, {
        message: "the pages still to split are not lost",
    });
});
