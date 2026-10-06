/** @odoo-module native */
import { compareDates, toDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { usePopover } from "@web/ui/popover";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { MilestonesPopover } from "./milestones_popover.js";

/**
 * @param {Temporal.ZonedDateTime} boundary a column boundary on the time axis
 * @param {Temporal.PlainDate | false} [day]
 */
function isAfter(boundary, day) {
    return !day || compareDates(boundary, toDateTime(day)) > 0;
}

/**
 * @param {Temporal.ZonedDateTime} boundary a column boundary on the time axis
 * @param {Temporal.PlainDate | false} [day]
 */
function isBefore(boundary, day) {
    return Boolean(day) && compareDates(boundary, toDateTime(day)) < 0;
}

function projectEntry(info, { id, name }) {
    if (!info.projects[id]) {
        info.projects[id] = { milestones: [], id, name };
    }
    return info.projects[id];
}

export class TaskGanttRendererCommon extends GanttRenderer {
    static headerTemplate = "project_gantt.TaskGanttRenderer.Header";
    static rowContentTemplate = "project_gantt.TaskGanttRenderer.RowContent";
    static totalRowTemplate = "project_gantt.TaskGanttRenderer.TotalRow";
    static pillTemplate = "project_gantt.TaskGanttRenderer.Pill";

    setup() {
        super.setup(...arguments);
        useLayoutEffect(
            (el) => el.classList.add("o_project_gantt"),
            () => [this.gridRef.el],
        );
        const position = localization.direction === "rtl" ? "bottom" : "right";
        this.milestonePopover = usePopover(MilestonesPopover, { position });
    }

    /**
     * @override
     */
    enrichPill(pill) {
        const enrichedPill = super.enrichPill(pill);
        if (enrichedPill.record.is_closed) {
            pill.className += " opacity-50";
        }
        return enrichedPill;
    }

    computeVisibleColumns() {
        super.computeVisibleColumns();
        this.columnMilestones = {}; // deadlines and milestones by project
        for (const column of this.columns) {
            this.columnMilestones[column.index] = {
                hasDeadLineExceeded: false,
                allReached: true,
                projects: {},
                hasMilestone: false,
                hasDeadline: false,
                hasStartDate: false,
            };
        }
        // Handle start date at the beginning of the current period
        this.columnMilestones[this.columns[0].index].edge = {
            projects: {},
            hasStartDate: false,
        };
        const projectStartDates = [...this.model.data.projectStartDates];
        const projectDeadlines = [...this.model.data.projectDeadlines];
        const milestones = [...this.model.data.milestones];

        let project = projectStartDates.shift();
        let projectDeadline = projectDeadlines.shift();
        let milestone = milestones.shift();
        let i = 0;
        while (i < this.columns.length && (project || projectDeadline || milestone)) {
            const column = this.columns[i];
            const nextColumn = this.columns[i + 1];
            const info = this.columnMilestones[column.index];

            if (i === 0 && project && column && isAfter(column.stop, project.date)) {
                // For the first column, start dates have to be displayed at the start of the period
                projectEntry(info.edge, project).isStartDate = true;
                info.edge.hasStartDate = true;
                project = projectStartDates.shift();
            } else if (
                project &&
                nextColumn &&
                isAfter(nextColumn.stop, project.date)
            ) {
                projectEntry(info, project).isStartDate = true;
                info.hasStartDate = true;
                project = projectStartDates.shift();
            }
            if (projectDeadline && isAfter(column.stop, projectDeadline.date)) {
                projectEntry(info, projectDeadline).isDeadline = true;
                info.hasDeadline = true;
                projectDeadline = projectDeadlines.shift();
            }
            if (milestone && isAfter(column.stop, milestone.date_deadline)) {
                const [id, name] = milestone.project_id;
                projectEntry(info, { id, name }).milestones.push(milestone);
                info.hasMilestone = true;
                info.hasDeadLineExceeded ||= Boolean(milestone.is_deadline_exceeded);
                info.allReached &&= Boolean(milestone.is_reached);
                milestone = milestones.shift();
            }
            if (
                (!project || !nextColumn || isBefore(nextColumn.stop, project.date)) &&
                (!projectDeadline || isBefore(column.stop, projectDeadline.date)) &&
                (!milestone || isBefore(column.stop, milestone.date_deadline))
            ) {
                i++;
            }
        }
    }

    async getPopoverProps() {
        const props = await super.getPopoverProps(...arguments);
        props.actionContext.is_form_gantt = true;
        return props;
    }

    shouldRenderRecordConnectors(record) {
        if (record.allow_dependencies) {
            return super.shouldRenderRecordConnectors(...arguments);
        }
        return false;
    }

    //--------------------------------------------------------------------------
    // Handlers
    //--------------------------------------------------------------------------

    onMilestoneMouseEnter(ev, projects) {
        this.milestonePopover.open(ev.target, {
            displayMilestoneDates: this.model.metaData.scale.id === "year",
            displayProjectName: !this.model.searchParams.context.default_project_id,
            projects,
        });
    }

    onMilestoneMouseLeave() {
        this.milestonePopover.close();
    }

    //--------------------------------------------------------------------------
    //Task Connectors
    //--------------------------------------------------------------------------

    shouldConnectorBeDashed(sourcePill) {
        if (sourcePill.record.is_closed) {
            return true;
        }
        return super.shouldConnectorBeDashed(sourcePill);
    }
}
