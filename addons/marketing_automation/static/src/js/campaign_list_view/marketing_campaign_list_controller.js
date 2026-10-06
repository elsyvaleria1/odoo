/** @odoo-module native */
import { CampaignTemplatePickerDialog } from "@marketing_automation/components/campaign_template_picker_dialog/campaign_template_picker_dialog";
import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list";

export class CampaignListController extends ListController {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
    }
    /**
     * @override
     */
    async createRecord() {
        this.dialog.add(CampaignTemplatePickerDialog, {});
    }
}
