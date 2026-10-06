/** @odoo-module native */
import { CampaignTemplatePickerDialog } from "@marketing_automation/components/campaign_template_picker_dialog/campaign_template_picker_dialog";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form";

export class CampaignFormController extends FormController {
    setup() {
        super.setup();
        this.dialog = useService("dialog");
    }
    /**
     * @override
     */
    async create() {
        this.dialog.add(CampaignTemplatePickerDialog, {});
    }
}
