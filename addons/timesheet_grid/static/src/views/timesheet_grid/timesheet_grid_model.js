/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { compareDates, serializeDate } from "@web/core/l10n/dates";
import { GridModel } from "@web_grid/views/grid_model";

export class TimesheetGridModel extends GridModel {
    get workingHoursData() {
        return this.data.workingHours;
    }

    get employeeField() {
        return this.fieldsInfo.employee_id;
    }

    async loadData(metaData) {
        await super.loadData(metaData);
        if (!this.orm.isSample) {
            await Promise.all(this.getTimesheetWorkingHoursPromises(metaData));
        }
    }

    /**
     * Order the groups by the label of each grouping in turn, the section's
     * first: read_group orders by value, and a many2one's value is an id.
     * Labels are read the way the grid reads them -- a pair's second half
     * for a many2one or a date granularity, a selection's through its
     * (key, label) list, which used to be asked for the key with `in` and so
     * left selection rows ordered by key.
     *
     * @param {{rowFields: Object[], sectionField?: Object}} metaData
     * @param {Object[]} dataFetched the groups, sorted in place.
     */
    _sortGridRows({ rowFields, sectionField }, dataFetched) {
        const orderFields = sectionField ? [sectionField, ...rowFields] : rowFields;
        const labelOf = (group, field) => {
            const raw = group[this.getGroupBySpec(field)];
            if (this.isPairValued(field)) {
                return raw && raw[1];
            }
            const fieldInfo = this.fieldsInfo[field.name];
            if (fieldInfo.type === "selection") {
                return fieldInfo.selection.find(([key]) => key === raw)?.[1] ?? raw;
            }
            return raw;
        };
        dataFetched.sort((first, second) => {
            for (const field of orderFields) {
                const firstLabel = labelOf(first, field);
                const secondLabel = labelOf(second, field);
                if (firstLabel === secondLabel) {
                    continue;
                }
                if (!firstLabel) {
                    return -1;
                }
                if (!secondLabel) {
                    return 1;
                }
                return String(firstLabel)
                    .toLowerCase()
                    .localeCompare(String(secondLabel).toLowerCase());
            }
            return 0;
        });
    }

    async fetchData(metaData) {
        const dataFetched = await super.fetchData(metaData);
        this._sortGridRows(metaData, dataFetched);
        return dataFetched;
    }

    getTimesheetWorkingHoursPromises(metaData) {
        const result = [
            this._fetchWorkingHoursData(metaData, "task_id"),
            this._fetchWorkingHoursData(metaData, "project_id"),
            this._fetchAllTimesheetM2OAvatarData(metaData),
        ];

        if (
            metaData.sectionField?.name ||
            (metaData.searchParams.groupBy?.length === 1 &&
                metaData.searchParams.groupBy?.[0]) === this.employeeField.name
        ) {
            result.push(this._fetchDailyWorkingHours(metaData));
        }

        return result;
    }

    async _fetchDailyWorkingHours({ data, sectionField, rowFields }) {
        const employeeIds = this._getFieldValuesInSectionAndRows(
            this.employeeField,
            sectionField,
            rowFields,
            data,
        );

        if (!employeeIds.length) {
            return;
        }

        data.workingHours.dailyPerEmployee = await this.orm.call(
            this.employeeField.relation,
            "get_daily_working_hours",
            [
                employeeIds,
                serializeDate(this.navigationInfo.periodStart),
                serializeDate(this.navigationInfo.periodEnd),
            ],
        );
    }

    async _getInitialData(metaData) {
        const initialData = await super._getInitialData(metaData);
        initialData.data.workingHours = {};
        return initialData;
    }

    _getFavoriteTaskDomain(searchParams) {
        return [
            ["project_id", "!=", false],
            ["user_ids", "in", searchParams.context.uid],
            ["allow_timesheets", "=", true],
            ["date_start", "<=", serializeDate(this.navigationInfo.periodEnd)],
            ["date_end", ">=", serializeDate(this.navigationInfo.periodStart)],
        ];
    }

    _getPreviousWeekTimesheetDomain() {
        return [
            [
                this.columnFieldName,
                ">=",
                serializeDate(this.navigationInfo.periodStart.subtract({ weeks: 1 })),
            ],
            [this.columnFieldName, "<", serializeDate(this.navigationInfo.periodStart)],
        ];
    }

    /**
     * @override
     */
    _fetchAdditionalData(metaData) {
        const additionalPromises = super._fetchAdditionalData(metaData);
        const { searchParams, sectionField, rowFields } = metaData;

        if (
            !searchParams.context.group_expand ||
            compareDates(this.navigationInfo.periodEnd, this.today) < 0
        ) {
            return additionalPromises;
        }

        const previousWeekTimesheetPromise = this.orm
            .formattedReadGroup(
                this.resModel,
                Domain.and([
                    searchParams.domain,
                    this._getPreviousWeekTimesheetDomain(),
                ]).toList({}),
                this._getGroupByFields(metaData),
                this.aggregates,
            )
            .then((additionalDataFetched) => {
                const additionalData = {};
                this._sortGridRows(metaData, additionalDataFetched);
                for (const readGroupResult of additionalDataFetched) {
                    let sectionKey = false;
                    let sectionValue = null;
                    if (sectionField) {
                        sectionKey = this._generateSectionKey(
                            readGroupResult,
                            sectionField,
                        );
                        sectionValue = readGroupResult[sectionField.name];
                    }
                    const rowKey = this._generateRowKey(readGroupResult, metaData);
                    const { domain, values } = this._generateRowDomainAndValues(
                        readGroupResult,
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
            });

        additionalPromises.push(previousWeekTimesheetPromise);
        return additionalPromises;
    }

    get usesUnavailability() {
        return true;
    }

    _fetchUnavailabilityDays(metaData, args = {}) {
        const { data, sectionField, rowFields } = metaData;
        const employeeField = this.employeeField.name;
        const employeeIds = [];
        let groupByEmployee = false;
        if (this.columnFieldIsDate) {
            if (sectionField && sectionField.name === employeeField) {
                groupByEmployee = true;
                for (const section of Object.values(data.sections)) {
                    const sectionValue = section.valuePerFieldName[sectionField.name];
                    if (sectionValue) {
                        employeeIds.push(sectionValue[0]);
                    }
                }
            } else if (rowFields.some((r) => r.name === employeeField)) {
                groupByEmployee = true;
                for (const row of Object.values(data.rows)) {
                    const fieldValue = row.valuePerFieldName?.employee_id;
                    if (fieldValue) {
                        employeeIds.push(fieldValue[0]);
                    }
                }
            }
        }
        return super._fetchUnavailabilityDays(metaData, {
            res_ids: employeeIds,
            groupby: groupByEmployee ? "employee_id" : "",
        });
    }

    _processUnavailabilityDays(result, metaData) {
        metaData.unavailabilityDaysPerEmployeeId = result;
    }

    /**
     *
     * @override
     */
    _postFetchAdditionalData(metaData) {
        const additionalGroups = super._postFetchAdditionalData(metaData);
        const { data, searchParams, rowFields, sectionField } = metaData;

        if (!searchParams.context.group_expand) {
            return additionalGroups;
        }

        const domainFieldsToNeutralize = [];
        let isProjectIdInDomainFields = false;
        let isTaskIdInDomainFields = false;
        let searchParamsDomain = [];
        for (const domainLeaf of new Domain(searchParams.domain).toList({})) {
            if (domainLeaf.length === 3) {
                const [fieldName, operator, value] = domainLeaf;
                if (fieldName === "project_id") {
                    if (!(operator === "!=" && value === false)) {
                        isProjectIdInDomainFields = true;
                    }
                } else if (fieldName === "task_id") {
                    isTaskIdInDomainFields = true;
                } else {
                    domainFieldsToNeutralize.push(fieldName);
                }
            }
            searchParamsDomain.push(domainLeaf);
        }
        searchParamsDomain = new Domain(searchParamsDomain);

        const fieldsToConsider = ["project_id", "task_id"];
        const isProjectOrTaskAsSectionField =
            sectionField && fieldsToConsider.includes(sectionField.name);
        const isProjectOrTaskInRows = rowFields.some((field) =>
            fieldsToConsider.includes(field.name),
        );
        if (
            !(
                rowFields.some((field) => field.name === "task_id") ||
                ((isProjectOrTaskAsSectionField || isProjectOrTaskInRows) &&
                    (isProjectIdInDomainFields || isTaskIdInDomainFields))
            )
        ) {
            return additionalGroups;
        }

        const neutralizedDomain = Domain.removeDomainLeaves(
            searchParamsDomain,
            domainFieldsToNeutralize,
        );

        let taskDomain = [];
        let projectDomain = [];
        const getIdOrName = (fieldName, operator, value) => {
            if (
                ["ilike", "not ilike"].includes(operator) ||
                (["=", "!="].includes(operator) && typeof value === "string")
            ) {
                return "name";
            }
            return "id";
        };
        const getFieldDomain = (expectedFieldName, fieldName, operator, value) => [
            fieldName === expectedFieldName
                ? getIdOrName(fieldName, operator, value)
                : fieldName,
            operator,
            value,
        ];
        let previousOperator = "&";
        for (const domainLeaf of neutralizedDomain.toList({})) {
            if (domainLeaf.length === 3) {
                const [fieldName, operator, value] = domainLeaf;
                if (fieldName === "project_id") {
                    if (operator === "!=" && value === false) {
                        projectDomain.push(
                            previousOperator === "&"
                                ? Domain.TRUE.toList({})[0]
                                : Domain.FALSE.toList({})[0],
                        );
                    } else {
                        projectDomain.push(
                            getFieldDomain("project_id", fieldName, operator, value),
                        );
                    }
                    taskDomain.push(domainLeaf);
                    continue;
                } else if (fieldName === "task_id") {
                    taskDomain.push(
                        getFieldDomain("task_id", fieldName, operator, value),
                    );
                    projectDomain.push(
                        previousOperator === "&"
                            ? Domain.TRUE.toList({})[0]
                            : Domain.FALSE.toList({})[0],
                    );
                    continue;
                }
            } else {
                previousOperator = domainLeaf;
            }
            taskDomain.push(domainLeaf);
            projectDomain.push(domainLeaf);
        }

        taskDomain = new Domain(taskDomain);
        projectDomain = new Domain(projectDomain);

        const domainIds = [];
        if (sectionField && fieldsToConsider.includes(sectionField.name)) {
            for (const sectionInfo of Object.values(data.sections)) {
                if (!sectionInfo.isFake) {
                    domainIds.push(sectionInfo.value[0]);
                }
            }
        }

        const prepareAdditionalData = (records, fieldName) => {
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

        if (isProjectIdInDomainFields) {
            if (sectionField && sectionField.name === "project_id") {
                projectDomain = Domain.and([
                    projectDomain,
                    [["id", "in", domainIds]],
                    [["allow_timesheets", "=", true]],
                ]);
            }
            if (!sectionField || sectionField.name === "project_id") {
                additionalGroups.push(
                    this.orm
                        .webSearchRead("project.project", projectDomain.toList({}), {
                            specification: { display_name: {} },
                        })
                        .then((data) => {
                            const timesheet_data = data.records.map((r) => ({
                                project_id: [r.id, r.display_name],
                            }));
                            return prepareAdditionalData(timesheet_data);
                        }),
                );
            }
        }
        const addTaskData = (taskDomain, limit) => {
            additionalGroups.push(
                this.orm
                    .webSearchRead("project.task", taskDomain.toList({}), {
                        specification: {
                            display_name: {},
                            project_id: {
                                fields: { display_name: {} },
                            },
                        },
                        limit: limit,
                    })
                    .then((data) => {
                        const records = data.records.map(
                            ({ id, display_name, project_id }) => ({
                                task_id: [id, display_name],
                                project_id: project_id && [
                                    project_id.id,
                                    project_id.display_name,
                                ],
                            }),
                        );
                        return prepareAdditionalData(records);
                    }),
            );
        };
        if (isProjectIdInDomainFields || isTaskIdInDomainFields) {
            if (sectionField?.name === "task_id") {
                taskDomain = Domain.and([
                    taskDomain,
                    [["id", "in", domainIds]],
                    [["allow_timesheets", "=", true]],
                ]);
            }
            if (!sectionField || isProjectOrTaskAsSectionField) {
                addTaskData(taskDomain, 15);
            }
        } else if (
            compareDates(this.navigationInfo.periodEnd, this.today) >= 0 &&
            !sectionField
        ) {
            addTaskData(
                Domain.and([taskDomain, this._getFavoriteTaskDomain(searchParams)]),
                5,
            );
        }

        return additionalGroups;
    }

    _getFieldValuesInSectionAndRows(field, sectionField, rowFields, data) {
        const fieldName = field.name;
        const isMany2oneField = field.type === "many2one";
        const values = new Set();
        if (sectionField && sectionField.name === fieldName) {
            for (const section of Object.values(data.sections)) {
                const sectionValue = section.valuePerFieldName[sectionField.name];
                values.add(
                    sectionValue && isMany2oneField ? sectionValue[0] : sectionValue,
                );
            }
        } else if (rowFields.some((row) => row.name === fieldName)) {
            for (const row of Object.values(data.rows)) {
                if (!row.isSection) {
                    const value =
                        row.valuePerFieldName[fieldName] && isMany2oneField
                            ? row.valuePerFieldName[fieldName][0]
                            : row.valuePerFieldName[fieldName];
                    values.add(value);
                }
            }
        }
        return [...values];
    }

    async _fetchWorkingHoursData({ data, sectionField, rowFields }, fieldName) {
        const field = this.fieldsInfo[fieldName];
        if (!field) {
            return [];
        }
        const fieldValues = this._getFieldValuesInSectionAndRows(
            field,
            sectionField,
            rowFields,
            data,
        );
        if (!fieldValues.length) {
            return fieldValues;
        }
        const result = await this.orm.call(
            field.relation,
            "get_planned_and_worked_hours",
            [fieldValues],
        );
        data.workingHours[fieldName] = result;
    }

    async _fetchAllTimesheetM2OAvatarData({ data, sectionField, rowFields }) {
        if (
            !this.employeeField ||
            this.navigationInfo.contains(this.today) ||
            compareDates(this.navigationInfo.periodStart, this.today) > 0
        ) {
            return {};
        }
        const fieldValues = this._getFieldValuesInSectionAndRows(
            this.employeeField,
            sectionField,
            rowFields,
            data,
        );
        const nonEmptyValues = fieldValues.filter((v) => v !== false);
        if (!nonEmptyValues.length) {
            return {};
        }
        const result = await this.orm.call(
            this.employeeField.relation,
            "get_timesheet_and_working_hours_for_employees",
            [
                nonEmptyValues,
                serializeDate(this.navigationInfo.periodStart),
                serializeDate(this.navigationInfo.periodEnd),
            ],
        );
        data.workingHours.employee_id = result;
    }
}
