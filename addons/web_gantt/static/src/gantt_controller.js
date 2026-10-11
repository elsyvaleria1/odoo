/** @odoo-module native */
import { Component, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { CallbackRecorder, useSetupAction } from "@web/core/action_hook";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useModelWithSampleData } from "@web/model/model";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { usePager } from "@web/search/pager_hook";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { ConfirmationDialog, deleteConfirmationMessage } from "@web/ui/dialog";
import { EmptyState } from "@web/views/empty_state/empty_state";
import { standardViewProps } from "@web/views/standard_view_props";
import { FormViewDialog } from "@web/views/view_dialogs";
import { provideGanttContext, useGanttContext } from "@web_gantt/gantt_context";

import { localEndOf, localStartOf } from "./gantt_helpers.js";

const log = makeLogger("gantt.controller");

export class GanttController extends Component {
    static components = {
        CogMenu,
        Layout,
        SearchBar,
        EmptyState,
    };
    static props = {
        ...standardViewProps,
        Model: t.function(),
        Renderer: t.function(),
        buttonTemplate: t.string(),
        modelParams: t.object(),
        multiCreateValues: t.object().optional(),
        scrollPosition: t.object().optional(),
    };
    static template = "web_gantt.GanttController";
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        useLifecycleLog(log);
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.orm = useService("orm");

        provideGanttContext({
            getCurrentFocusDateCallBackRecorder: new CallbackRecorder(),
            createFromSelectionCallBackRecorder: new CallbackRecorder(),
        });
        this.ganttContext = useGanttContext();

        const rootRef = (this.rootRef = elementRef());

        this.model = proxy(
            useModelWithSampleData(this.props.Model, this.props.modelParams),
        );
        useSetupAction({
            rootRef,
            getLocalState: () => ({
                metaData: this.model.metaData,
                displayParams: this.model.displayParams,
            }),
        });

        onWillUnmount(() => this.closeDialog?.());

        usePager(() => {
            const { groupedBy, pagerLimit, pagerOffset } = this.model.metaData;
            const { count } = this.model.data;
            if (pagerLimit !== null && groupedBy.length) {
                return {
                    offset: pagerOffset,
                    limit: pagerLimit,
                    total: count,
                    onUpdate: async ({ offset, limit }) => {
                        await this.model.updatePagerParams({ offset, limit });
                    },
                };
            }
        });

        useLayoutEffect(
            (showNoContentHelp) => {
                if (showNoContentHelp) {
                    const realRows = [
                        ...rootRef.el.querySelectorAll(
                            ".o_gantt_row_header:not(.o_sample_data_disabled)",
                        ),
                    ];
                    const headerContainerWidth =
                        rootRef.el.querySelector(".o_gantt_header_groups")
                            .clientHeight +
                        rootRef.el.querySelector(".o_gantt_header_columns")
                            .clientHeight;

                    const offset = realRows.reduce(
                        (current, el) => current + el.clientHeight,
                        headerContainerWidth,
                    );

                    const noContentHelperEl =
                        rootRef.el.querySelector(".o_view_nocontent");
                    noContentHelperEl.style.top = `${offset}px`;
                }
            },
            () => [this.showNoContentHelp],
        );
        this.searchBarToggler = useSearchBarToggler();
    }

    get className() {
        if (this.ui.isSmall) {
            const classList = (this.props.className || "").split(" ");
            classList.push("o_action_delegate_scroll");
            return classList.join(" ");
        }
        return this.props.className;
    }

    get showNoContentHelp() {
        return this.model.useSampleModel;
    }

    /**
     * @param {Record<string, any>} [context]
     */
    create(context) {
        const { createAction } = this.model.metaData;
        if (createAction) {
            this.actionService.doAction(createAction, {
                additionalContext: context,
                onClose: () => {
                    this.model.fetchData();
                },
            });
        } else {
            this.openDialog({ context });
        }
    }

    _getDialogProps(props) {
        const {
            canDelete,
            canEdit,
            resModel,
            formViewId: viewId,
        } = this.model.metaData;

        const title = props.title || (props.resId ? _t("Open") : _t("Create"));

        let removeRecord;
        if (canDelete && props.resId) {
            removeRecord = () =>
                new Promise((resolve) => {
                    this.dialogService.add(ConfirmationDialog, {
                        title: _t("Bye-bye, record!"),
                        body: deleteConfirmationMessage,
                        confirmLabel: _t("Delete"),
                        confirm: async () => {
                            await this.orm.unlink(resModel, [props.resId]);
                            resolve();
                        },
                        cancel: () => {},
                        cancelLabel: _t("No, keep it"),
                    });
                });
        }

        return {
            title,
            resModel,
            viewId,
            resId: props.resId,
            size: props.size,
            canExpand: props.canExpand,
            readonly: !canEdit,
            context: props.context,
            removeRecord,
        };
    }

    /**
     * Opens dialog to add/edit/view a record
     *
     * @param {Record<string, any>} props dialog component props
     * @param {Record<string, any>} [options={}]
     * @param {Component} [dialogComponent=FormViewDialog] component to instantiate
     */
    openDialog(props, options = {}, dialogComponent = FormViewDialog) {
        log.logic("openDialog", () => ({
            resId: props.resId,
            dialog: dialogComponent.name,
            context: props.context,
        }));
        this.closeDialog = this.dialogService.add(
            dialogComponent,
            this._getDialogProps(props),
            {
                ...options,
                onClose: () => {
                    this.closeDialog = null;
                    this.model.fetchData();
                },
            },
        );
    }

    createAtFocusDate() {
        this.create(this.getCreateContext());
    }

    onNewClicked() {
        if (!this.createFromSelection()) {
            this.createAtFocusDate();
        }
    }

    getCreateContext() {
        const { scale } = this.model.metaData;
        const focusDate = this.getCurrentFocusDate();
        const start = localStartOf(focusDate, scale.unit);
        const stop = localEndOf(focusDate, scale.unit).add({ milliseconds: 1 });
        return this.model.getDialogContext({ start, stop, withDefault: true });
    }

    createFromSelection() {
        const { callbacks } = this.ganttContext.createFromSelectionCallBackRecorder;
        if (callbacks.length) {
            return callbacks[0]();
        }
        return false;
    }

    getCurrentFocusDate() {
        const { callbacks } = this.ganttContext.getCurrentFocusDateCallBackRecorder;
        if (callbacks.length) {
            return callbacks[0]();
        }
        return this.model.metaData.focusDate;
    }
}
