/** @odoo-module native */
import { DocumentsRightPanel } from "@document/components/document_right_panel/document_right_panel";
import { DocumentsRendererMixin } from "@document/views/document_renderer_mixin";
import { DocumentsFileViewerHost } from "@document/views/helper/document_file_viewer";
import { ActivityRenderer } from "@mail/views/web/activity/activity_renderer";
import { t } from "@odoo/owl";

export class DocumentsActivityRenderer extends DocumentsRendererMixin(
    ActivityRenderer,
) {
    static props = { ...ActivityRenderer.props, previewStore: t.object() };
    static template = "document.DocumentsActivityRenderer";
    static components = {
        ...ActivityRenderer.components,
        DocumentsRightPanel,
        DocumentsFileViewerHost,
    };
}
