/** @odoo-module native */
import { DocumentsDetailsPanel } from "@document/components/document_details_panel/document_details_panel";
import { DocumentsChatter } from "@document/views/chatter/document_chatter";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DocumentsRightPanel extends Component {
    static template = "document.DocumentsViews.RightPanel";
    static props = { nbViewItems: t.number() };
    static components = {
        Chatter: DocumentsChatter,
        DocumentsDetailsPanel,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.documentService = useService("document.document");
        this.ui = useService("ui");
        this.state = proxy(this.documentService.rightPanelReactive);
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get panelDisabled() {
        return (
            !this.state.focusedRecord ||
            !this.state.focusedRecord.data ||
            typeof this.state.focusedRecord.data.id !== "number"
        );
    }
}
