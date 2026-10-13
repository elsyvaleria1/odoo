/** @odoo-module native */
import {
    provideMarketingAutomationContext,
    useMarketingAutomationContext,
} from "@marketing_automation/marketing_automation_context";
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { append, createElement, parseXML } from "@web/core/utils/dom/xml";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";
import { useX2ManyCrud } from "@web/fields/relational/x2many_crud";
import { useOpenX2ManyRecord } from "@web/fields/relational/x2many_dialog";
import { ConfirmationDialog } from "@web/ui/dialog";
import { KanbanRecord, KanbanRenderer } from "@web/views/kanban";

const fieldRegistry = registry.category("fields");

export class HierarchyKanbanRecord extends KanbanRecord {
    static components = {
        ...KanbanRecord.components,
        HierarchyKanbanRecord,
    };

    static props = {
        ...KanbanRecord.props,
        getRecordDepth: t.function(),
    };

    setup() {
        super.setup();
        this.marketingAutomationContext = useMarketingAutomationContext();

        this.activeTab = "graph";
        useLayoutEffect(
            () => {
                const activityTabs =
                    this.rootRef.el.querySelectorAll(".o_ma_activity_tab");
                const onMarketingActivityTabClick =
                    this.onMarketingActivityTabClick.bind(this);
                activityTabs.forEach((el) => {
                    el.addEventListener("click", onMarketingActivityTabClick);
                });

                return () => {
                    activityTabs.forEach((el) => {
                        el.removeEventListener("click", onMarketingActivityTabClick);
                    });
                };
            },
            () => [],
        );

        useLayoutEffect(this.applyTabPanelVisibility.bind(this), () => [
            this.rootRef.el,
        ]);

        useLayoutEffect(
            () => {
                const addChildActivityButtons = this.rootRef.el.querySelectorAll(
                    ".o_add_child_activity",
                );
                const onAddChildActivityClick = this.onAddChildActivityClick.bind(this);
                addChildActivityButtons.forEach((el) => {
                    el.addEventListener("click", onAddChildActivityClick);
                });

                return () => {
                    addChildActivityButtons.forEach((el) => {
                        el.removeEventListener("click", onAddChildActivityClick);
                    });
                };
            },
            () => [],
        );
    }

    /** @param {MouseEvent} ev */
    async onAddChildActivityClick(ev) {
        await this.props.record.model.root.save();

        const context = {
            default_parent_id: this.props.record.resId,
            default_trigger_type: ev.target.dataset.triggerType,
        };
        this.marketingAutomationContext.onAddMarketingActivity({ context });
    }

    /** @param {MouseEvent} ev */
    onMarketingActivityTabClick(ev) {
        ev.stopPropagation();

        this.activeTab = ev.currentTarget.dataset.tabType;
        this.applyTabPanelVisibility();
        this.props.record.model.notify();
    }

    applyTabPanelVisibility() {
        const graphTab = this.rootRef.el.querySelector(".o_pane_graph");
        const filterTab = this.rootRef.el.querySelector(".o_pane_filter");

        if (!graphTab || !filterTab) {
            return;
        }

        this.rootRef.el
            .querySelectorAll(".o_ma_activity_tab")
            .forEach((el) => el.classList.remove("active"));

        if (this.activeTab === "graph") {
            graphTab.classList.remove("d-none");
            filterTab.classList.add("d-none");
            const graphTabButton = this.rootRef.el.querySelector(
                '[data-tab-type="graph"]',
            );
            if (graphTabButton) {
                graphTabButton.classList.add("active");
            }
        } else if (this.activeTab === "filter") {
            graphTab.classList.add("d-none");
            filterTab.classList.remove("d-none");
            const filterTabButton = this.rootRef.el.querySelector(
                '[data-tab-type="filter"]',
            );
            if (filterTabButton) {
                filterTabButton.classList.add("active");
            }
        }
    }
}

export class HierarchyKanbanRenderer extends KanbanRenderer {
    static template = "marketing_automation.HierarchyKanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        KanbanRecord: HierarchyKanbanRecord,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");

        this.dialogService = useService("dialog");
        const rootEl = this.props.archInfo.templateDocs["card"].firstElementChild;
        const rootTemplate = createElement("t", { "t-name": "root" });
        append(rootTemplate, rootEl);
        this.props.archInfo.templateDocs.root = rootTemplate;

        const mainTemplate = parseXML(
            `
            <t t-name="card">
                <t t-set="currentDepth" t-value="currentDepth ? currentDepth + 1 : 1"/>
                <div t-if="__comp__.props.getRecordDepth(__comp__.props.record) - currentDepth + 1 > 0" class="o_ma_body_wrapper">
                    <t t-call="{{ __comp__.templates['card'] }}"/>
                </div>
                <t t-else="" t-call="{{ __comp__.templates.root }}"/>
            </t>
            `,
        );

        this.props.archInfo.templateDocs["card"] = mainTemplate;
    }

    deleteRecord(record) {
        const directChildren = this.props.list.records.filter(
            (listRecord) =>
                listRecord.data.parent_id &&
                listRecord.data.parent_id.id === record.resId,
        );

        if (directChildren.length !== 0) {
            this.dialogService.add(ConfirmationDialog, {
                body: _t(
                    "Deleting this activity will delete ALL its children activities. Are you sure?",
                ),
                confirmLabel: _t("Delete"),
                confirm: () => this.props.deleteRecord(record),
                cancel: () => {},
            });
        } else {
            return this.props.deleteRecord(record);
        }
    }

    getGroupsOrRecords() {
        return this._getSortedRecordsByHierarchy(this.props.list.records, false).map(
            (record) => ({
                record,
                key: record.id,
            }),
        );
    }

    getRecordDepth(record) {
        const parentByChildMap = this._getParentByChildMap(this.props.list.records);
        let childId = record.resId;
        let depth = 0;
        while (childId) {
            childId = parentByChildMap[childId];
            if (childId) {
                depth++;
            }
        }
        return depth;
    }

    _getParentByChildMap(records) {
        const parentMap = {};
        records.forEach((activityRecord) => {
            const parentId = activityRecord.data.parent_id;
            if (parentId) {
                parentMap[activityRecord.resId] = parentId.id;
            }
        });

        return parentMap;
    }

    _getSortedRecordsByHierarchy(records, parentId) {
        return records.flatMap((record) => {
            if (!record.resId) {
                return [];
            } else if (!record.data.parent_id && parentId) {
                return [];
            } else if (record.data.parent_id && record.data.parent_id.id !== parentId) {
                return [];
            }

            return [
                record,
                ...this._getSortedRecordsByHierarchy(records, record.resId),
            ];
        });
    }
}

export class HierarchyKanban extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        KanbanRenderer: HierarchyKanbanRenderer,
    };

    setup() {
        super.setup();

        const { saveAndLink, updateRecord } = useX2ManyCrud(
            () => this.list,
            this.isMany2Many,
        );

        const openRecord = useOpenX2ManyRecord({
            resModel: this.list.resModel,
            activeField: this.activeField,
            activeActions: this.activeActions,
            getList: () => this.list,
            saveRecord: async (record) => {
                await saveAndLink(record);
                await this.props.record.save();
            },
            updateRecord: updateRecord,
        });
        this._openRecord = openRecord;

        provideMarketingAutomationContext({
            onAddMarketingActivity: this.onAdd.bind(this),
        });
    }

    async onAdd() {
        if (!(await this.props.record.save())) {
            return;
        }
        return super.onAdd(...arguments);
    }
}

export const hierarchyKanban = {
    ...x2ManyField,
    component: HierarchyKanban,
};

fieldRegistry.add("hierarchy_kanban", hierarchyKanban);
