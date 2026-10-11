/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { formatDate, toDateTime, today } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { pick } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { onWillRender } from "@web/core/utils/render_hooks";
import { useDebounced } from "@web/core/utils/timing";
import { useReactiveModel } from "@web/model/model";

import { addDuration, diffColumn } from "./gantt_helpers.js";
import { GanttScaleSelector } from "./gantt_scale_selector.js";

const KEYS = ["startDate", "stopDate", "rangeId", "focusDate", "rescheduleMethod"];

export class GanttRendererControls extends Component {
    static template = "web_gantt.GanttRendererControls";
    static components = {
        Dropdown,
        DropdownItem,
        GanttScaleSelector,
    };
    static props = {
        model: t.any(),
        displayExpandCollapseButtons: t.any(),
        focusToday: t.any(),
        getCurrentFocusDate: t.any(),
        multiSelection: t.any().optional(),
        slots: t.any().optional(),
    };
    static toolbarContentTemplate = "web_gantt.GanttRendererControls.ToolbarContent";
    static rangeMenuTemplate = "web_gantt.GanttRendererControls.RangeMenu";
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.model = useReactiveModel(this.props.model);
        this.updateMetaData = useDebounced(() => this.requestFetch(), 500);
        this.state = proxy(pick(this.model.metaData, ...KEYS));
        this.syncedMetaData = this.model.metaData;
        this.pendingRequests = 0;
        onWillRender(() => this.syncStateFromModel());
    }

    async requestFetch() {
        this.pendingRequests++;
        try {
            await this.model.fetchData(this.makeParams());
        } finally {
            this.pendingRequests--;
            this.syncedMetaData = this.model.metaData;
        }
    }

    syncStateFromModel() {
        const { metaData } = this.model;
        if (metaData === this.syncedMetaData || this.pendingRequests) {
            return;
        }
        Object.assign(this.state, pick(metaData, ...KEYS));
        delete this.state.keepCurrentFocusDate;
        this.syncedMetaData = metaData;
    }

    getGanttScaleSelectorProps() {
        return {
            scales: {
                ...this.model.metaData.ranges,
                custom: {
                    from_date: formatDate(this.state.startDate),
                    to_date: formatDate(this.state.stopDate),
                },
            },
            currentScale: this.state.rangeId,
            setScale: this.selectRangeId.bind(this),
            selectCustomRange: this.selectCustomRange.bind(this),
            startDate: this.state.startDate,
            stopDate: this.state.stopDate,
        };
    }

    makeParams() {
        const params = pick(this.state, ...KEYS);
        if (this.state.keepCurrentFocusDate) {
            params.currentFocusDate = this.props.getCurrentFocusDate();
        }
        return params;
    }

    onTodayClicked() {
        const success = this.props.focusToday();
        if (success) {
            return;
        }
        this.state.focusDate = toDateTime(today());
        if (this.state.rangeId === "custom") {
            const diff = diffColumn(this.state.startDate, this.state.stopDate, "day");
            if (diff === 0) {
                this.state.startDate = this.state.stopDate = this.state.focusDate;
            } else {
                const n = Math.floor(diff / 2);
                const m = diff - n;
                this.state.startDate = this.state.focusDate.subtract({ days: n });
                this.state.stopDate = this.state.focusDate.add({ days: m - 1 });
            }
        } else {
            Object.assign(
                this.state,
                this.model.rangeAround(this.state.rangeId, this.state.focusDate),
            );
        }
        delete this.state.keepCurrentFocusDate;
        this.updateMetaData();
    }

    selectRange(direction) {
        const sign = direction === "next" ? 1 : -1;
        const { focusDate, rangeId, startDate, stopDate } = this.state;
        if (rangeId === "custom") {
            const diff = diffColumn(startDate, stopDate, "day") + 1;
            this.state.focusDate = focusDate.add({ days: sign * diff });
            this.state.startDate = startDate.add({ days: sign * diff });
            this.state.stopDate = stopDate.add({ days: sign * diff });
        } else {
            Object.assign(
                this.state,
                this.model.rangeAround(
                    rangeId,
                    addDuration(focusDate, { [rangeId]: sign }),
                ),
            );
        }
        delete this.state.keepCurrentFocusDate;
        this.updateMetaData();
    }

    selectRangeId(rangeId) {
        Object.assign(this.state, this.model.rangeAround(rangeId, toDateTime(today())));
        delete this.state.keepCurrentFocusDate;
        this.updateMetaData();
    }

    selectCustomRange(startDate, stopDate) {
        this.state.rangeId = "custom";
        this.state.startDate = startDate;
        this.state.stopDate = stopDate;
        this.state.keepCurrentFocusDate = true;
        this.updateMetaData();
    }

    get displayModeToggleTitle() {
        return this.model.displayParams.displayMode === "dense"
            ? _t("Activate sparse mode")
            : _t("Activate dense mode");
    }

    get displayRescheduleMethods() {
        return (
            this.model.metaData.dependencyEnabled &&
            !this.model.useSampleModel &&
            !this.ui.isSmall
        );
    }

    selectRescheduleMethod(method) {
        Object.assign(this.state, { rescheduleMethod: method });
        this.updateMetaData();
    }
}
