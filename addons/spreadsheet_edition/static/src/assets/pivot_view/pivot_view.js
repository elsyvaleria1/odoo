/** @odoo-module native */
import { SpreadsheetSelectorDialog } from "@spreadsheet_edition/assets/components/spreadsheet_selector_dialog/spreadsheet_selector_dialog";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { intersection, unique } from "@web/core/utils/collections/arrays";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useSearchModel } from "@web/search/search_model";
import { session } from "@web/session";
import { PivotRenderer } from "@web/views/pivot";

const ALL_PERIODS = {
    quarter: _t("Quarter & Year"),
    month: _t("Month & Year"),
    week: _t("Week & Year"),
    day: _t("Day"),
    year: _t("Year"),
    quarter_number: _t("Quarter"),
    month_number: _t("Month"),
    iso_week_number: _t("Week"),
    day_of_month: _t("Day of Month"),
};

patch(PivotRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.canInsertPivot = session.can_insert_in_spreadsheet;
    },

    async onInsertInSpreadsheet() {
        let name = this.model.metaData.title;
        const groupBy =
            this.model.metaData.fullColGroupBys[0] ||
            this.model.metaData.fullRowGroupBys[0];
        if (groupBy) {
            let [field, period] = groupBy.split(":");
            period = ALL_PERIODS[period];
            if (period) {
                name = _t("%(pivot_title)s by %(group_by)s (%(granularity)s)", {
                    pivot_title: name,
                    group_by: this.model.metaData.fields[field].string,
                    granularity: period,
                });
            } else {
                name = _t("%(pivot_title)s by %(group_by)s", {
                    pivot_title: name,
                    group_by: this.model.metaData.fields[field].string,
                });
            }
        }
        const { actionId } = this.config;
        const { xml_id } = actionId
            ? await this.actionService.loadAction(actionId, this.searchModel.context)
            : {};

        const actionOptions = {
            preProcessingAsyncAction: "insertPivot",
            preProcessingAsyncActionData: {
                metaData: this.model.metaData,
                searchParams: {
                    ...this.model.searchParams,
                    domain: this.searchModel.domainString,
                    context: omit(
                        this.model.searchParams.context,
                        ...Object.keys(user.context),
                        "pivot_measures",
                        "pivot_row_groupby",
                        "pivot_column_groupby",
                    ),
                },
                colGroupTree: this.model.data.colGroupTree,
                name,
                actionXmlId: xml_id,
            },
        };
        const params = {
            type: "PIVOT",
            name,
            actionOptions,
        };
        this.dialog.add(SpreadsheetSelectorDialog, params);
    },

    hasDuplicatedGroupbys() {
        const fullColGroupBys = this.model.metaData.fullColGroupBys;
        const fullRowGroupBys = this.model.metaData.fullRowGroupBys;
        const colGroupBys = fullColGroupBys.map((el) => el.split(":")[0]);
        const rowGroupBys = fullRowGroupBys.map((el) => el.split(":")[0]);
        return (
            unique([...fullColGroupBys, ...fullRowGroupBys]).length <
                fullColGroupBys.length + fullRowGroupBys.length ||
            intersection(colGroupBys, rowGroupBys).length
        );
    },

    isInsertButtonDisabled() {
        return (
            !this.model.hasData() ||
            this.model.metaData.activeMeasures.length === 0 ||
            this.model.useSampleModel ||
            this.hasDuplicatedGroupbys()
        );
    },

    getInsertButtonTooltip() {
        return this.hasDuplicatedGroupbys()
            ? _t("Pivot contains duplicate groupbys")
            : undefined;
    },
});
