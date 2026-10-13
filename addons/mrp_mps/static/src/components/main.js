/** @odoo-module native */
import MpsLineComponent from "@mrp_mps/components/line";
import { MasterProductionScheduleModel } from "@mrp_mps/models/master_production_schedule_model";
import { provideMrpMpsContext } from "@mrp_mps/mrp_mps_context";
import { Component, onWillStart, signal, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { useSetupAction } from "@web/core/action_hook";
import { download, rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { useRender } from "@web/core/utils/render_hooks";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";
import { ActionMenus } from "@web/search/action_menus/action_menus";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { usePager } from "@web/search/pager_hook";
import { ViewScaleSelector } from "@web/views/view_components";
import { ExportDataDialog } from "@web/views/view_dialogs";
import {
    getActionMenuItems,
    prepareStaticActionMenuItems,
} from "@web/views/view_utils";
import { standardActionServiceProps } from "@web/webclient/actions";

import {
    MrpMpsControlPanel,
    MrpMpsSearchBar,
} from "../search/mrp_mps_control_panel.js";

export const SCALE_LABELS = {
    day: _t("Day"),
    week: _t("Week"),
    month: _t("Month"),
    year: _t("Year"),
};

export class MainComponent extends Component {
    static template = "mrp_mps.mrp_mps";
    static components = {
        MrpMpsControlPanel,
        MpsLineComponent,
        CheckBox,
        MrpMpsSearchBar,
        ActionMenus,
        ViewScaleSelector,
    };
    static props = { ...standardActionServiceProps, searchDomain: t.array() };
    props = useProps(this.constructor.props);
    render = useRender();

    setup() {
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.viewService = useService("view");

        const { orm, action, dialog } = this;
        this.model = new MasterProductionScheduleModel(this.props, {
            orm,
            action,
            dialog,
        });

        this.config = {
            ...useViewConfig(),
            offset: 0,
            limit: 20,
            mpsImportRecords: true,
        };
        provideViewConfig(this.config);
        provideMrpMpsContext({
            manufacturingPeriods: [],
            model: this.model,
            defaultPageLimit: 20,
        });

        useSetupAction({
            getContext: () => this.props.action.context,
        });

        const modelRevision = signal(0);
        useBus(this.model, "update", () => {
            modelRevision.set(modelRevision() + 1);
            this.render(true);
        });

        onWillStart(async () => {
            this.config.setDisplayName(_t("Master Production Schedule"));
            const domain = this.props.searchDomain;
            await this.model.load(domain, this.config.offset, this.config.limit);
        });

        usePager(() => {
            void modelRevision();
            return {
                offset: this.config.offset,
                limit: this.config.limit,
                total: this.model.data.count,
                onUpdate: async ({ offset, limit }) => {
                    this.config.offset = offset;
                    this.config.limit = limit;
                    this.model.load(undefined, offset, limit);
                },
            };
        });
    }

    get lines() {
        return this.model.data.production_schedule_ids.slice(0, this.config.limit);
    }

    get manufacturingPeriods() {
        return this.model.data.dates;
    }

    get periodTypes() {
        return Object.fromEntries(
            this.model.data.manufacturing_period_types.map((s) => [
                s,
                { description: SCALE_LABELS[s] },
            ]),
        );
    }

    get currentPeriodType() {
        return this.model.data.manufacturing_period;
    }

    get isInDefaultPeriod() {
        return this.model.data.manufacturing_period === this.model.data.default_period;
    }

    async setScale(scale) {
        await this.model.load(
            this.props.searchDomain,
            this.config.offset,
            this.config.limit,
            scale,
        );
    }

    get groups() {
        return this.model.data.groups[0];
    }

    get isSelected() {
        return this.model.selectedRecords.size === this.lines.length;
    }

    toggleSelection() {
        this.model.toggleSelection();
    }

    /** @private */
    _onClickReplenish() {
        this.model.replenishAll();
    }

    _onMouseOverReplenish() {
        this.model.mouseOverReplenish();
    }

    _onMouseOutReplenish() {
        this.model.mouseOutReplenish();
    }

    _onClickCreate() {
        this.model._createProduct();
    }

    get actionMenuItems() {
        return getActionMenuItems({
            ...prepareStaticActionMenuItems({
                export: { callback: () => this.onExportData() },
                delete: { callback: () => this.model.unlinkSelectedRecord() },
            }),
            replenish: {
                groupNumber: COG_GROUP.APP,
                sequence: 10,
                icon: "fa-solid fa-cart-shopping",
                description: _t("Order"),
                callback: () => this.model.replenishSelectedRecords(),
            },
            indirect: {
                groupNumber: COG_GROUP.APP,
                sequence: 20,
                icon: "fa-solid fa-arrows-left-right",
                description: _t("Toggle Indirect Demand"),
                callback: () => this.model.toggleIsIndirect(),
            },
        });
    }

    get isRecordSelected() {
        return this.model.selectedRecords.size > 0;
    }

    async getExportedFields(import_compat, parentParams) {
        const resIds = Array.from(this.model.selectedRecords);
        const ids = resIds.length > 0 && resIds;
        const domain = [["id", "in", ids]];
        return await rpc("/web/export/get_fields", {
            model: "mrp.production.schedule",
            ...parentParams,
            domain,
            import_compat,
        });
    }

    async downloadExport(fields, import_compat, format) {
        const resIds = Array.from(this.model.selectedRecords);
        const exportedFields = fields.map((field) => ({
            name: field.name || field.id,
            label: field.label || field.string,
            store: field.store,
            type: field.field_type,
        }));
        if (import_compat) {
            exportedFields.unshift({ name: "id", label: _t("External ID") });
        }
        await download({
            data: {
                data: JSON.stringify({
                    import_compat,
                    context: this.props.context,
                    domain: this.model.domain,
                    fields: exportedFields,
                    ids: resIds.length > 0 && resIds,
                    model: "mrp.production.schedule",
                }),
            },
            url: `/web/export/${format}`,
        });
    }

    /** @private */
    onExportData() {
        const dialogProps = {
            context: this.props.context,
            defaultExportList: [],
            download: this.downloadExport.bind(this),
            getExportedFields: this.getExportedFields.bind(this),
            root: {
                resModel: "mrp.production.schedule",
                activeFields: [],
            },
        };
        this.dialog.add(ExportDataDialog, dialogProps);
    }

    async suggestForecastedDemand(data, productionScheduleId) {
        const action = await this.orm.call(
            "wizard.mrp.production.schedule.update.forecast",
            "action_view_suggest_forecasted_form_view",
            [[], productionScheduleId],
            {
                context: {
                    period_scale: this.currentPeriodType,
                    periods: this.manufacturingPeriods,
                },
            },
        );
        return this.action.doAction(action, {
            onClose: () => this.model.reload(productionScheduleId),
        });
    }
}
