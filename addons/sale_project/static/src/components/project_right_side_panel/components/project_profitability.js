/** @odoo-module native */
import { t } from "@odoo/owl";
import {
    ProjectProfitability,
    projectProfitabilityProps,
} from "@project/components/project_right_side_panel/components/project_profitability";
import { ProjectProfitabilitySection } from "@sale_project/components/project_right_side_panel/components/project_profitability_section";
import { patch } from "@web/core/utils/patch";

patch(ProjectProfitability, {
    components: {
        ...ProjectProfitability.components,
        ProjectProfitabilitySection,
    },
});
Object.assign(projectProfitabilityProps, {
    projectId: t.number(),
    context: t.object(),
});
