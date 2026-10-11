/** @odoo-module native */
import { Component, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { useSetupAction } from "@web/core/action_hook";
import { browser } from "@web/core/browser/browser";
import { deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useModelWithSampleData } from "@web/model/model";
import { standardViewProps } from "@web/views/standard_view_props";
import { useViewButtons, ViewButton } from "@web/views/view_button";
import { useViewChassis, ViewLayout } from "@web/views/view_components";
import { FormViewDialog } from "@web/views/view_dialogs";

export class GridController extends Component {
    static components = { ViewLayout, ViewButton };

    static props = {
        ...standardViewProps,
        archInfo: t.object(),
        buttonTemplate: t.string(),
        Model: t.function(),
        Renderer: t.function(),
    };

    static template = "web_grid.GridView";
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        const state = this.props.state || {};
        let activeRangeName = this.props.archInfo.activeRangeName;
        let defaultAnchor;
        if (state.activeRangeName) {
            activeRangeName = state.activeRangeName;
        } else if (this.isMobile && "day" in this.props.archInfo.ranges) {
            activeRangeName = "day";
        }
        if (state.anchor) {
            defaultAnchor = state.anchor;
        } else if (this.props.context.grid_anchor) {
            defaultAnchor = deserializeDate(this.props.context.grid_anchor);
        }
        this.dialogService = useService("dialog");
        this.model = proxy(
            useModelWithSampleData(this.props.Model, {
                resModel: this.props.resModel,
                sectionField: this.props.archInfo.sectionField,
                rowFields: this.props.archInfo.rowFields,
                columnFieldName: this.props.archInfo.columnFieldName,
                measureField: this.props.archInfo.measureField,
                readonlyField: this.props.archInfo.readonlyField,
                fieldsInfo: this.props.relatedModels[this.props.resModel].fields,
                activeRangeName,
                ranges: this.props.archInfo.ranges,
                withRecordIds: this.props.archInfo.buttons.length > 0,
                defaultAnchor,
            }),
        );
        this.chassis = useViewChassis(this, {
            displayNoContent: () => this.displayNoContent,
        });
        const { rootRef } = this.chassis;
        useSetupAction({
            rootRef,
            getLocalState: () => {
                const { anchor, range } = this.model.navigationInfo;
                return {
                    anchor,
                    activeRangeName: range?.name,
                };
            },
        });
        this.state = proxy({
            activeRangeName: this.model.navigationInfo.range?.name,
            isWeekendVisible: this._getInitialWeekendVisibility(),
        });
        useViewButtons(rootRef, {
            beforeExecuteAction: this.beforeExecuteActionButton.bind(this),
            afterExecuteAction: this.afterExecuteActionButton.bind(this),
            reload: this.reload.bind(this),
        });
        onWillUnmount(() => this.closeDialog?.());
    }

    /**
     * The chassis' props with the grid's own root classes: the one every
     * grid style hangs off, and the one that hands the action container's
     * scroll to the grid on a small screen.
     *
     * @return {Object}
     */
    get chassisProps() {
        const classes = ["o_grid_view", this.props.className];
        if (this.isMobile) {
            classes.push("o_action_delegate_scroll");
        }
        return { ...this.chassis.props, className: classes.filter(Boolean).join(" ") };
    }

    /**
     * Whether weekend columns start out shown. The stored preference is
     * global to every grid, so it is only consulted by a grid that has
     * weekends to hide: a grid whose columns are not days has none, and
     * would otherwise inherit a `false` written by an unrelated view and
     * filter every one of its columns away.
     *
     * @private
     * @return {boolean}
     */
    _getInitialWeekendVisibility() {
        if (!this.canHideWeekend) {
            return true;
        }
        const stored = browser.localStorage.getItem("grid.isWeekendVisible");
        return stored === null || stored === undefined ? true : JSON.parse(stored);
    }

    /**
     * Hiding weekends is only meaningful where a column *is* a day: a range
     * stepping by month has no weekend column to drop, and a range spanning a
     * single day would hide the only column it has. Both are asked of the
     * range's shape rather than of its name, which the arch is free to choose.
     *
     * @return {boolean}
     */
    get canHideWeekend() {
        const { range } = this.model.navigationInfo;
        return Boolean(
            this.model.columnFieldIsDate &&
            range?.step === "day" &&
            range.span !== "day",
        );
    }

    /**
     * The visibility weekend columns are actually rendered with: the user's
     * stored preference only bites on a grid that can hide weekends at all,
     * so every consumer (column list, row and section grand totals, the
     * scale selector) reads one answer instead of re-deriving it.
     *
     * @return {boolean}
     */
    get isWeekendVisible() {
        return this.state.isWeekendVisible || !this.canHideWeekend;
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get isEditable() {
        return this.props.archInfo.activeActions.edit && this.props.archInfo.editable;
    }

    get displayNoContent() {
        return (
            !(this.props.archInfo.displayEmpty || this.model.hasData()) ||
            this.model.useSampleModel
        );
    }

    get displayAddALine() {
        return this.props.archInfo.activeActions.create;
    }

    get options() {
        const { hideLineTotal, hideColumnTotal, hasBarChartTotal, createInline } =
            this.props.archInfo;
        return {
            hideLineTotal,
            hideColumnTotal,
            hasBarChartTotal,
            createInline,
        };
    }

    createRecord(params) {
        const columnContext = this.model.columnFieldIsDate
            ? {
                  [`default_${this.model.columnFieldName}`]: serializeDate(
                      this.model.navigationInfo.anchor,
                  ),
              }
            : {};
        const context = {
            ...this.props.context,
            ...columnContext,
            ...params?.context,
        };
        this.closeDialog = this.dialogService.add(
            FormViewDialog,
            {
                title: _t("New Record"),
                resModel: this.model.resModel,
                viewId: this.props.archInfo.formViewId,
                onRecordSaved: this.onRecordSaved.bind(this),
                ...params,
                context,
            },
            {
                onClose: () => {
                    this.closeDialog = null;
                },
            },
        );
    }

    async beforeExecuteActionButton() {}

    async afterExecuteActionButton() {}

    async reload() {
        await this.model.reload();
    }

    async onRecordSaved(record) {
        await this.reload();
    }

    get columns() {
        if (this.isWeekendVisible) {
            return this.model.columnsArray;
        }
        return this.model.columnsArray.filter((column) => column.isWeekDay);
    }

    toggleWeekendVisibility() {
        this.state.isWeekendVisible = !this.state.isWeekendVisible;
        browser.localStorage.setItem(
            "grid.isWeekendVisible",
            this.state.isWeekendVisible,
        );
    }
}
