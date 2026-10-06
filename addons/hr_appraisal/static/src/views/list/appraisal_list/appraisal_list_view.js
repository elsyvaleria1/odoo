/** @odoo-module native */
import { AppraisalActionHelper } from "@hr_appraisal/views/helper/appraisal_helper_view/appraisal_helper_view";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { ListRenderer, listView } from "@web/views/list";

export class AppraisalListRenderer extends ListRenderer {
    static template = "hr_appraisal.AppraisalListRenderer";
    static components = {
        ...AppraisalListRenderer.components,
        AppraisalActionHelper,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }
}

export const AppraisalListView = {
    ...listView,
    Renderer: AppraisalListRenderer,
};

registry.category("views").add("appraisal_list_view", AppraisalListView);
