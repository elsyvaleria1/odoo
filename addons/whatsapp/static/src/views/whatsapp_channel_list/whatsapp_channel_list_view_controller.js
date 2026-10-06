/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

export class WhatsappChannelListController extends ListController {
    setup() {
        super.setup(...arguments);
        this.store = useService("mail.store");
    }

    async openRecord(record) {
        const thread = await this.store.Thread.getOrFetch({
            model: "discuss.channel",
            id: record.resId,
        });
        if (thread) {
            return thread.open();
        }
        return super.openRecord(record);
    }
}
