/** @odoo-module native */
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { Domain } from "@web/core/domain";
import {
    compareDates,
    endOf,
    serializeDateTime,
    toDateTime,
    today as getToday,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";
import { GanttController } from "@web_gantt/gantt_controller";
import { localEndOf, localStartOf } from "@web_gantt/gantt_helpers";

import { usePlanningControllerActions } from "../planning_hooks.js";

export class PlanningGanttController extends GanttController {
    static components = {
        ...GanttController.components,
        Dropdown,
        DropdownItem,
    };
    /**
     * @override
     */
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.ui = useService("ui");
        this.planningControllerActions = usePlanningControllerActions({
            getAdditionalContext: () => this.model.getAdditionalContext(),
            getDomain: () => {
                const { dateStartField, dateStopField, scale } = this.model.metaData;
                const focusDate = this.getCurrentFocusDate();
                const start = localStartOf(focusDate, scale.unit);
                const stop = localEndOf(focusDate, scale.unit);
                const domain = Domain.and([
                    this.model.searchParams.domain,
                    [
                        "&",
                        [dateStartField, "<", serializeDateTime(stop)],
                        [dateStopField, ">", serializeDateTime(start)],
                    ],
                ]);
                return domain.toList();
            },
            getRecords: () => {
                if (this.model.useSampleModel) {
                    return [];
                }
                return this.model.data.records;
            },
            getResModel: () => this.model.metaData.resModel,
            getStartDate: () => {
                const { scale } = this.model.metaData;
                const focusDate = this.getCurrentFocusDate();
                return localStartOf(focusDate, scale.unit);
            },
            getStopDate: () => this.model.metaData.stopDate,
            toggleHighlightPlannedFilter: (highlightPlannedIds) =>
                this.searchModel.toggleHighlightPlannedFilter(highlightPlannedIds),
            reload: () => this.model.fetchData(),
        });
    }

    /**
     * @override
     */
    createAtFocusDate() {
        const { scale, globalStart, globalStop } = this.model.metaData;
        const today = toDateTime(getToday());
        if (
            scale.id !== "day" &&
            compareDates(globalStart, endOf(today, "day")) <= 0 &&
            compareDates(today, globalStop) <= 0
        ) {
            const start = today;
            const stop = endOf(today, scale.interval);
            const context = this.model.getDialogContext({
                start,
                stop,
                withDefault: true,
            });
            this.create(context);
            return;
        }
        super.createAtFocusDate(...arguments);
    }

    /**
     * @override
     */
    openDialog(props, options, dialogComponent) {
        const record = this.model.data.records.find((r) => r.id === props.resId);
        const title = record ? record.display_name : _t("Add Shift");
        const context = {
            ...props.context,
            my_planning_action: this.props.context.my_planning_action,
            is_record_created: !record,
            view_start_date: serializeDateTime(this.model.metaData.globalStart),
            view_end_date: serializeDateTime(this.model.metaData.globalStop),
        };
        super.openDialog({ ...props, title, context }, options, dialogComponent);
    }

    get previewTitle() {
        return _t("Preview");
    }
}
