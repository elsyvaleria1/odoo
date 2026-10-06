import { defineDocumentsModels } from "@document/../tests/document_test_helpers";
import {
    getDocumentsTestServerModelsData,
    makeDocumentRecordData,
} from "@document/../tests/helpers/data";
import { makeDocumentsMockEnv } from "@document/../tests/helpers/model";
import { AddDocumentsAttachmentPlugin } from "@document/editor/plugins/add_document_attachment_plugin";
import { openDocumentsPicker } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { setupEditor } from "@html_editor/../tests/_helpers/editor";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import {
    contains,
    getService,
    mountWithCleanup,
    onRpc,
} from "@web/../tests/web_test_helpers";
import { MainComponentsContainer } from "@web/ui/main_components_container";

describe.current.tags("desktop");

defineDocumentsModels();

test("a file box inserted from Documents carries its attachment id", async () => {
    const { editor } = await setupEditor("<p>[]</p>", {
        config: { Plugins: MAIN_PLUGINS },
    });
    const plugin = editor.plugins.find(
        (p) => p instanceof AddDocumentsAttachmentPlugin,
    );
    const box = plugin.renderDownloadBox({
        id: 7,
        name: "contract.pdf",
        mimetype: "application/pdf",
        access_token: "tok",
    });
    expect(box.dataset.attachmentId).toBe("7", {
        message: "a composer removing the attachment finds its box by this id",
    });
});

/**
 * Opens the picker on three files: one shared by link, one the user may share,
 * one they may not, and pastes all three.
 *
 * @param {Object} props what the picker is opened with
 * @param {"confirm"|"cancel"|null} answer to the sharing question, if asked
 */
async function pasteThreeLinks(props, answer) {
    const serverData = getDocumentsTestServerModelsData([
        makeDocumentRecordData(11, "Shared", {
            access_via_link: "view",
            access_url: "/documents/shared",
        }),
        makeDocumentRecordData(12, "Private", { access_url: "/documents/private" }),
        makeDocumentRecordData(13, "Theirs", {
            access_url: "/documents/theirs",
            user_can_manage: false,
        }),
    ]);
    onRpc("document.document", "action_update_access_rights", ({ args, kwargs }) => {
        expect.step(`share:${args[0]}:${kwargs.access_via_link}`);
        return [];
    });
    await makeDocumentsMockEnv({ serverData });
    await mountWithCleanup(MainComponentsContainer);
    openDocumentsPicker(getService("dialog"), {
        onPasteLinks: (links) =>
            expect.step(`pasted:${links.map((link) => link.display_name)}`),
        ...props,
    });
    await animationFrame();
    await contains(".o_select_create_dialog_content thead .o-checkbox input").click();
    await contains(".modal-footer button:contains('Paste Link(s)')").click();
    if (answer) {
        await contains(
            `.modal-footer button:contains('${answer === "confirm" ? "Share and paste" : "Cancel"}')`,
        ).click();
    }
    await animationFrame();
}

test("in a web page, a document shared once the user agrees is pasted with the shared ones", async () => {
    await pasteThreeLinks({ linksArePublic: true }, "confirm");
    expect.verifySteps(["share:12:view", "pasted:Shared,Private"]);
    expect(".o_notification:contains(Theirs)").toHaveCount(1, {
        message: "the one they cannot share is left out, and they are told",
    });
});

test("in a web page, a document the user declines to share is left out", async () => {
    await pasteThreeLinks({ linksArePublic: true }, "cancel");
    expect.verifySteps(["pasted:Shared"]);
});

test("in a private record, links are pasted as they are, nothing is shared", async () => {
    await pasteThreeLinks({}, null);
    expect.verifySteps(["pasted:Shared,Private,Theirs"]);
});
