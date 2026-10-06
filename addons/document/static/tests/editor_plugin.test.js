import { AddDocumentsAttachmentPlugin } from "@document/editor/plugins/add_document_attachment_plugin";
import { setupEditor } from "@html_editor/../tests/_helpers/editor";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { describe, expect, test } from "@odoo/hoot";

describe.current.tags("desktop");

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
