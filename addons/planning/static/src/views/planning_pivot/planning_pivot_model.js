/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { PivotModel } from "@web/views/pivot";

import { usePlanningModelActions } from "../planning_hooks.js";

export class PlanningPivotModel extends PivotModel {
    /** @override **/
    setup() {
        super.setup(...arguments);
        this.getHighlightIds = usePlanningModelActions({
            getHighlightPlannedIds: () =>
                this.viewContext.searchModel.highlightPlannedIds,
            getContext: () => this.viewContext.searchModel._context,
        }).getHighlightIds;
    }

    /** @override **/
    async load(searchParams) {
        const highlightIds = await this.getHighlightIds();
        if (highlightIds) {
            searchParams.domain = Domain.and([
                searchParams.domain,
                [["id", "in", highlightIds]],
            ]).toList();
        }
        return await super.load(searchParams);
    }
}
