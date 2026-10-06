/** @odoo-module native */
import { onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer, kanbanView } from "@web/views/kanban";

export class ReferralKanbanRenderer extends KanbanRenderer {
    static template = "hr_referral.KanbanRenderer";

    setup() {
        super.setup();
        this.ui = useService("ui");

        this.orm = useService("orm");
        this.showGrass = true;

        onWillStart(async () => {
            const referralData = await this.orm.call(
                "hr.applicant",
                "get_referral_data",
            );
            this.showGrass = referralData.show_grass || true;
        });
    }

    get companyId() {
        return user.activeCompany.id;
    }
}

registry.category("views").add("referral_kanban", {
    ...kanbanView,
    Renderer: ReferralKanbanRenderer,
});
