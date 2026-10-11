/** @odoo-module native */
import { openDocumentsPicker } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { _t } from "@web/core/translation";

registerComposerAction("add-documents", {
    icon: { template: "document.DocumentsIcon" },
    name: _t("Add from Documents"),
    onSelected: ({ composer, owner, store }) => {
        openDocumentsPicker(store.env.services.dialog, {
            onAddAttachments: owner.allowUpload
                ? (attachments) => composer.attachments.push(...attachments)
                : undefined,
            onPasteLinks: (links) => {
                const lines = links.map(
                    ({ display_name, access_url }) => `${display_name}: ${access_url}`,
                );
                composer.composerText += `\n${lines.join("\n")}`;
            },
        });
    },
    sequence: 10,
});
