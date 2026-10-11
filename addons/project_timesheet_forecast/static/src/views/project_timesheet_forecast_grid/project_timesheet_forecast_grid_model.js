/** @odoo-module native */
import { TimesheetGridModel } from "@timesheet_grid/views/timesheet_grid/timesheet_grid_model";
import { Domain } from "@web/core/domain";
import { compareDates, serializeDate } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(TimesheetGridModel.prototype, {
    /**
     * @override
     */
    _postFetchAdditionalData(metaData) {
        const additionalGroups = super._postFetchAdditionalData(metaData);
        const { searchParams, sectionField, rowFields } = metaData;

        if (
            !searchParams.context.group_expand ||
            compareDates(this.navigationInfo.periodEnd, this.today) < 0
        ) {
            return additionalGroups;
        }

        const validPlanningFields = ["project_id", "employee_id"];
        const validRowFields = [];
        if (sectionField && validPlanningFields.includes(sectionField.name)) {
            validRowFields.push(sectionField.name);
        }
        for (const rowField of rowFields) {
            if (validPlanningFields.includes(rowField.name)) {
                validRowFields.push(rowField.name);
            }
        }

        if (!validRowFields.length) {
            return additionalGroups;
        }

        const domain = new Domain([
            ["employee_id", "!=", false],
            ["employee_id.user_id", "in", [false, searchParams.context.uid]],
            ["state", "!=", "1_draft"],
            ["project_id.allow_timesheets", "=", true],
            ["start_datetime", "<", serializeDate(this.navigationInfo.periodEnd)],
            ["end_datetime", ">", serializeDate(this.navigationInfo.periodStart)],
        ]);

        const fieldsToRemove = [];
        const searchDomain = new Domain(searchParams.domain);
        let additionalDomain = searchDomain;
        for (const tuple of searchDomain.ast.value) {
            if (
                tuple.type === 10 &&
                !["project_id", "employee_id", "user_id"].includes(tuple.value[0].value)
            ) {
                fieldsToRemove.push(tuple.value[0].value);
            }
        }
        if (fieldsToRemove.length) {
            additionalDomain = Domain.removeDomainLeaves(
                additionalDomain,
                fieldsToRemove,
            );
        }
        const previousWeekSlotsInfo = this.orm.formattedReadGroup(
            "planning.slot",
            Domain.and([additionalDomain, domain]).toList({}),
            validRowFields,
            [],
        );

        const prepareAdditionalData = (records) => {
            const additionalData = {};
            for (const record of records) {
                let sectionKey = false;
                let sectionValue = null;
                if (sectionField) {
                    sectionKey = this._generateSectionKey(record, sectionField);
                    sectionValue = record[sectionField.name];
                }
                const rowKey = this._generateRowKey(record, metaData);
                const { domain, values } = this._generateRowDomainAndValues(
                    record,
                    rowFields,
                );
                if (!(sectionKey in additionalData)) {
                    additionalData[sectionKey] = {
                        value: sectionValue,
                        rows: {},
                    };
                }
                if (!(rowKey in additionalData[sectionKey].rows)) {
                    additionalData[sectionKey].rows[rowKey] = {
                        domain: domain,
                        values,
                    };
                }
            }

            return additionalData;
        };

        additionalGroups.push(
            previousWeekSlotsInfo.then((groups) => {
                const timesheet_data = groups.map((r) => {
                    const d = {};
                    for (const validRowField of validRowFields) {
                        d[validRowField] = r[validRowField];
                    }
                    return d;
                });
                return prepareAdditionalData(timesheet_data);
            }),
        );

        return additionalGroups;
    },
});
