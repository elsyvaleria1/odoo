/** @odoo-module native */
import { DocumentsBusEvent } from "@document/core/document_service";
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { useService } from "@web/core/utils/hooks";

export class DocumentsChatter extends WebChatter {
    setup() {
        super.setup();
        this.documentService = useService("document.document");
    }

    /**
     * @override
     */
    onActivityChanged(thread) {
        super.onActivityChanged(thread);
        this.documentService.bus.trigger(DocumentsBusEvent.ACTIVITY_CHANGED, {
            recordId: thread.id,
        });
    }
}
