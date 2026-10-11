/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { parseXML } from "@web/core/utils/dom/xml";
import { nbsp } from "@web/core/utils/format/strings";
import { extractFieldsFromArchInfo } from "@web/model/relational_model";
import { useSearchModel } from "@web/search/search_model";
import { irToElement, literalNbsp } from "@web/views/ir/view_ir";
import { KanbanRecord } from "@web/views/kanban";
import { SelectCreateDialog } from "@web/views/view_dialogs";

import { GanttRendererInteractions } from "./gantt_renderer_interactions.js";

const viewRegistry = registry.category("views");

export class GanttRendererDialogs extends GanttRendererInteractions {
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
    }

    /**
     * @returns {any[][]}
     */
    getPlanDialogDomain() {
        const { dateStartField, dateStopField } = this.model.metaData;
        const newDomain = Domain.removeDomainLeaves(this.searchModel.globalDomain, [
            dateStartField,
            dateStopField,
        ]);
        return Domain.and([
            newDomain,
            ["|", [dateStartField, "=", false], [dateStopField, "=", false]],
        ]).toList({});
    }

    async _getKanbanViewParams() {
        const { dateStartField, dateStopField, kanbanViewId, fields, resModel } =
            this.model.metaData;

        if (kanbanViewId !== undefined) {
            const result = await this.viewService.loadViews({
                resModel,
                views: [[kanbanViewId, "kanban"]],
            });

            const archXmlDoc = irToElement(result.views.kanban.ir, {
                text: literalNbsp,
            });
            archXmlDoc.removeAttribute("highlight_color");
            const menu = archXmlDoc.querySelector(
                `templates [t-name=${KanbanRecord.KANBAN_MENU_ATTRIBUTE}]`,
            );
            menu?.remove();

            const { relatedModels } = result;
            const { ArchParser } = viewRegistry.get("kanban");
            const archInfo = new ArchParser().parse(
                archXmlDoc,
                relatedModels,
                resModel,
            );
            return {
                archInfo,
                ...extractFieldsFromArchInfo(archInfo, fields),
            };
        }
        if (!this.defaultkanbanViewParams) {
            const nameString = _t("Name");
            const startString = _t("Start");
            const stopString = _t("Stop");
            const formatted = (fieldName) =>
                fields[fieldName].type === "date"
                    ? `dates.formatDate(dates.deserializeDate(record.${fieldName}.raw_value))`
                    : `dates.formatValue(dates.parseISO(record.${fieldName}.raw_value), 'f')`;
            const arch = `
                <kanban>
                    <templates>
                        <field name="${dateStartField}"/>
                        <field name="${dateStopField}"/>
                        <t t-name="${KanbanRecord.KANBAN_CARD_ATTRIBUTE}">
                            <ul class="p-0 mb-0 list-unstyled">
                                <li class="pe-2">
                                    <strong>${nameString}</strong>: <field name="display_name"/>
                                </li>
                                <li class="pe-2">
                                    <strong>${startString}</strong>: <span t-out="${formatted(dateStartField)}"/>
                                </li>
                                <li class="pe-2">
                                    <strong>${stopString}</strong>: <span t-out="${formatted(dateStopField)}"/>
                                </li>
                            </ul>
                        </t>
                    </templates>
                </kanban>
            `;
            const archXmlDoc = parseXML(arch.replace(/&amp;nbsp;/g, nbsp));

            const relatedModels = { [resModel]: { fields } };
            const { ArchParser } = viewRegistry.get("kanban");
            const archInfo = new ArchParser().parse(
                archXmlDoc,
                relatedModels,
                resModel,
            );
            this.defaultkanbanViewParams = {
                archInfo,
                ...extractFieldsFromArchInfo(archInfo, fields),
            };
        }
        return this.defaultkanbanViewParams;
    }

    /**
     * @param {Pill} pill
     */
    async getPopoverProps(pill) {
        const { record } = pill;
        const { id: resId, display_name: displayName } = record;
        const { canEdit, popoverArchParams, resModel } = this.model.metaData;
        const kanbanViewParams = popoverArchParams.bodyTemplate
            ? {}
            : await this._getKanbanViewParams();
        return {
            ...popoverArchParams,
            kanbanViewParams,
            KanbanRecord,
            title: displayName,
            context: { ...record },
            actionContext: this.props.context,
            resId,
            resModel,
            reloadOnClose: () => {
                this.onCloseCurrentPopover = () => {
                    delete this.onCloseCurrentPopover;
                    this.model.fetchData();
                };
            },
            buttons: [
                {
                    id: "open_view_edit_dialog",
                    text: canEdit ? _t("Edit") : _t("View"),
                    class: "btn btn-sm btn-primary",
                    onClick: () =>
                        this.model.mutex.exec(() => this.props.openDialog({ resId })),
                },
            ],
        };
    }

    openPlanDialogCallback() {}

    getSelectCreateDialogProps(params) {
        const domain = this.getPlanDialogDomain();
        const schedule = this.model.getDialogContext(params);
        return {
            title: _t("Plan"),
            resModel: this.model.metaData.resModel,
            context: schedule,
            domain,
            noCreate: !this.model.metaData.canCellCreate,
            onSelected: (resIds) => {
                if (resIds.length) {
                    this.model.reschedule(
                        resIds,
                        schedule,
                        this.openPlanDialogCallback.bind(this),
                    );
                }
            },
        };
    }

    onCellClicked(rowId, column) {
        const row = this.rowByIds[rowId];
        if (!row) {
            return;
        }
        const startCol = column.grid.column[0];
        if (this.model.hasMultiCreate) {
            if (column.isFolded) {
                return;
            }
            const endCol = startCol + this.model.metaData.scale.cellPart;
            const [startRow, endRow] = row.grid.row;
            const block = { startCol, endCol, startRow, endRow };
            const action = this.ctrlPressed ? "toggle" : "replace";
            this.updateMultiSelection(block, action);
            this.drawCellGhosts(this.selectedCells);
            return;
        }
        if (!this.preventClick) {
            this.preventClick = true;
            setTimeout(() => (this.preventClick = false), 1000);
            if (column.isFolded) {
                this.toggleFoldableColumn(column, false);
                return;
            }
            const { canCellCreate, canPlan } = this.model.metaData;
            if (canPlan) {
                this.onPlan(rowId, startCol, startCol);
            } else if (canCellCreate) {
                this.onCreate(
                    rowId,
                    startCol,
                    startCol + this.model.metaData.scale.cellPart - 1,
                );
            }
        }
    }

    onCreate(rowId, startCol, stopCol, additionalContext = {}) {
        let { start } = this.getSubColumnFromColNumber(startCol);
        let { stop } = this.getSubColumnFromColNumber(stopCol);
        ({ start, stop } = this.normalizeTimeRange(start, stop));
        const context = this.model.getDialogContext({
            rowId,
            start,
            stop,
            withDefault: true,
        });
        this.props.create({
            ...context,
            ...additionalContext,
        });
    }

    /**
     * @param {PointerEvent} ev
     * @param {Pill} pill
     */
    async onPillClicked(ev, pill) {
        if (this.popover.isOpen) {
            return;
        }
        const target = ev.target.closest(".o_gantt_pill_wrapper");
        const props = await this.keepLast.add(this.getPopoverProps(pill));
        this.popover.open(target, props);
    }

    onPlan(rowId, startCol, stopCol) {
        let { start, stop } = this.getColumnStartStop(startCol, stopCol);
        ({ start, stop } = this.normalizeTimeRange(start, stop));
        this.dialogService.add(
            SelectCreateDialog,
            this.getSelectCreateDialogProps({ rowId, start, stop, withDefault: true }),
        );
    }
}
