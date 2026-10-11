/** @odoo-module native */
import { DocumentsFileViewer } from "@document/attachments/document_file_viewer";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";

export class DocumentsFileViewerHost extends Component {
    static template = "document.DocumentsFileViewer";
    static components = {
        DocumentsFileViewer,
    };
    static props = { previewStore: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.documentService = useService("document.document");
        this.root = elementRef();
        this.rightPanelState = proxy(this.documentService.rightPanelReactive);
    }

    get isRightPanelVisible() {
        return this.rightPanelState.visible && !this.ui.isSmall;
    }

    onGlobalKeydown(ev) {
        const cancelledKeys = ["ArrowUp", "ArrowDown"];
        if (cancelledKeys.includes(ev.key)) {
            ev.stopPropagation();
        }
    }
}
