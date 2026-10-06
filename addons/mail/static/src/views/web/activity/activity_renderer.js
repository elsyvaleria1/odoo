// @ts-check
/** @odoo-module native */
import { MailColumnProgress } from "@mail/core/web/mail_column_progress";
import {
    readLocalStorageItem,
    setLocalStorageItem,
} from "@mail/utils/common/local_storage";
import { ActivityCell } from "@mail/views/web/activity/activity_cell";
import { ActivityRecord } from "@mail/views/web/activity/activity_record";
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { browser } from "@web/core/browser/browser";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";

const log = makeLogger("mail.activity.view");
export class ActivityRenderer extends Component {
    static components = {
        ActivityCell,
        ActivityRecord,
        ColumnProgress: MailColumnProgress,
        Dropdown,
        DropdownItem,
        CheckBox,
    };
    static props = {
        activityTypes: t.array(),
        activityResIds: t.array(),
        fields: t.object(),
        resModel: t.string(),
        records: t.array(),
        archInfo: t.object(),
        groupedActivities: t.object(),
        scheduleActivity: t.function(),
        onReloadData: t.function(),
        onEmptyCell: t.function(),
        onSendMailTemplate: t.function(),
        openRecord: t.function(),
    };
    static template = "mail.ActivityRenderer";
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.activeFilter = proxy({
            progressValue: {
                active: null,
            },
            activityTypeId: null,
            resIds: new Set(),
        });
        onWillUpdateProps(
            /** @param {{groupedActivities: Object}} nextProps */ (nextProps) => {
                if (this.activeFilter.activityTypeId !== null) {
                    const typeId = this.activeFilter.activityTypeId;
                    const name = this.activeFilter.progressValue.active;
                    this.activeFilter.resIds = new Set(
                        Object.entries(nextProps.groupedActivities)
                            .filter(
                                ([, resIds]) =>
                                    typeId in resIds &&
                                    name in resIds[typeId].count_by_state,
                            )
                            .map(([key]) => parseInt(key)),
                    );
                }
            },
        );

        this.store = useService("mail.store");
        this.storageKey = ["activity_columns", this.props.resModel, this.config.viewId];
        this.hiddenColumnsKey = [
            "activity_hidden_columns",
            ...this.storageKey.slice(1),
        ].join(",");
        this.migrateLegacyActiveColumns();
    }

    /** @returns {Object} */
    getActivityStateTypes() {
        const types = {
            done: {
                color: "secondary",
                inProgressBar: false,
                label: _t("done"),
                value: 0,
            },
            planned: {
                color: "success",
                inProgressBar: true,
                value: 0,
            },
            today: {
                color: "warning",
                inProgressBar: true,
                value: 0,
            },
            overdue: {
                color: "danger",
                inProgressBar: true,
                value: 0,
            },
        };
        for (const [type, label] of this.props.fields.activity_state.selection) {
            types[type].label = label;
        }
        return types;
    }

    /**
     * @param {Object} types
     * @param {number} typeId
     * @returns {number}
     */
    countActivityStates(types, typeId) {
        let totalCountWithoutDone = 0;
        for (const activities of Object.values(this.props.groupedActivities)) {
            if (!(typeId in activities)) {
                continue;
            }
            for (const [state, stateCount] of Object.entries(
                activities[typeId].count_by_state,
            )) {
                types[state].value += stateCount;
                if (state !== "done") {
                    totalCountWithoutDone += stateCount;
                }
            }
        }
        return totalCountWithoutDone;
    }

    /**
     * @param {Object} types
     * @param {string|null} activeBar
     * @returns {Object}
     */
    getStateProgressBar(types, activeBar) {
        const bars = [];
        for (const [value, type] of Object.entries(types)) {
            if (type.inProgressBar) {
                bars.push({
                    count: type.value,
                    value,
                    string: type.label,
                    color: type.color,
                });
            }
        }
        return { bars, activeBar, isReady: true };
    }

    /**
     * @param {{id: number, name: string}} activityType
     * @returns {Object}
     */
    getGroupInfo(activityType) {
        const types = this.getActivityStateTypes();
        const typeId = activityType.id;
        const isColumnFiltered = this.activeFilter.activityTypeId === typeId;
        const progressValue = isColumnFiltered
            ? this.activeFilter.progressValue
            : { active: null };
        const totalCountWithoutDone = this.countActivityStates(types, typeId);

        const ongoingActivityCount =
            types.overdue.value + types.today.value + types.planned.value;
        const ongoingAndDoneCount = ongoingActivityCount + types.done.value;
        const labelAggregate = `${types.overdue.label} + ${types.today.label} + ${types.planned.label}`;
        return {
            aggregate: {
                title: labelAggregate,
                value: isColumnFiltered
                    ? types[progressValue.active].value
                    : ongoingActivityCount,
            },
            aggregateOn: ongoingAndDoneCount
                ? {
                      title: `${types.done.label} + ${labelAggregate}`,
                      value: ongoingAndDoneCount,
                  }
                : undefined,
            data: {
                count: totalCountWithoutDone,
                /** @param {string} name */
                filterProgressValue: (name) => this.onSetProgressBarState(typeId, name),
                progressBar: this.getStateProgressBar(types, progressValue.active),
                progressValue,
            },
        };
    }

    /**
     * @param {number} templateId
     * @param {number} typeId
     */
    onSendMailTemplate(templateId, typeId) {
        const isColumnFiltered = this.activeFilter.activityTypeId === typeId;
        log.logic("onSendMailTemplate", () => ({
            templateId,
            typeId,
            filter: isColumnFiltered ? this.activeFilter.progressValue.active : null,
        }));
        this.props.onSendMailTemplate(
            templateId,
            typeId,
            isColumnFiltered ? [...this.activeFilter.resIds] : undefined,
        );
    }

    /**
     * @param {number} resId
     * @returns {import("@web/model/relational_model/record").RelationalRecord|undefined}
     */
    getRecord(resId) {
        return this.props.records.find((r) => r.resId === resId);
    }

    /**
     * @param {number} typeId
     * @param {{value: string}|string} bar
     */
    onSetProgressBarState(typeId, bar) {
        const name = typeof bar === "string" ? bar : bar.value;
        log.logic("onSetProgressBarState", () => ({
            typeId,
            name,
            clear: this.activeFilter.progressValue.active === name,
        }));
        if (this.activeFilter.progressValue.active === name) {
            this.activeFilter.progressValue.active = null;
            this.activeFilter.activityTypeId = null;
            this.activeFilter.resIds = new Set();
        } else {
            this.activeFilter.progressValue.active = name;
            this.activeFilter.activityTypeId = typeId;
            this.activeFilter.resIds = new Set(
                Object.entries(this.props.groupedActivities)
                    .filter(
                        ([, resIds]) =>
                            typeId in resIds && name in resIds[typeId].count_by_state,
                    )
                    .map(([key]) => parseInt(key)),
            );
        }
    }

    get activeColumns() {
        const hiddenColumnIds = this.hiddenColumnIds;
        return this.props.activityTypes.filter(
            (activityType) => !hiddenColumnIds.has(String(activityType.id)),
        );
    }

    /** @returns {Set<string>} */
    get hiddenColumnIds() {
        const stored = readLocalStorageItem(this.store, this.hiddenColumnsKey);
        return new Set(stored ? stored.split(",") : []);
    }

    /** @param {number} typeId */
    isColumnActive(typeId) {
        return !this.hiddenColumnIds.has(String(typeId));
    }

    migrateLegacyActiveColumns() {
        const legacyKey = this.storageKey.join(",");
        const legacyActiveIds = browser.localStorage.getItem(legacyKey);
        if (legacyActiveIds === null) {
            return;
        }
        if (readLocalStorageItem(this.store, this.hiddenColumnsKey) === null) {
            const activeIds = new Set(legacyActiveIds.split(","));
            const hiddenIds = this.props.activityTypes
                .map((activityType) => String(activityType.id))
                .filter((id) => !activeIds.has(id));
            log.logic("migrateLegacyActiveColumns", () => ({ hiddenIds }));
            setLocalStorageItem(this.store, this.hiddenColumnsKey, hiddenIds.join(","));
        }
        browser.localStorage.removeItem(legacyKey);
    }

    /** @param {number} typeId */
    toggleDisplayColumn(typeId) {
        const hiddenColumnIds = this.hiddenColumnIds;
        const id = String(typeId);
        if (hiddenColumnIds.has(id)) {
            hiddenColumnIds.delete(id);
        } else {
            hiddenColumnIds.add(id);
        }
        log.logic("toggleDisplayColumn", () => ({
            typeId,
            active: !hiddenColumnIds.has(id),
        }));
        setLocalStorageItem(
            this.store,
            this.hiddenColumnsKey,
            [...hiddenColumnIds].join(","),
        );
    }
}
