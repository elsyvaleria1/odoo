/** @odoo-module native */
import { mrpTimerField } from "@mrp/widgets/timer";
import { useMrpDisplayContext } from "@mrp_workorder/mrp_display/mrp_display_context";
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { CharField } from "@web/fields/basic/char/char_field";
import { Field } from "@web/fields/field";
import { Many2OneField } from "@web/fields/relational/many2one";
import { PriorityField } from "@web/fields/selection/priority/priority_field";
import { SelectionField } from "@web/fields/selection/selection/selection_field";
import { useSearchModel } from "@web/search/search_model";

import { MrpLogNoteDialog } from "./dialog/mrp_log_note_dialog.js";
import { MrpMenuDialog } from "./dialog/mrp_menu_dialog.js";
import { MrpRegisterProductionDialog } from "./dialog/mrp_register_production_dialog.js";
import { MrpWorkorder } from "./mrp_record_line/mrp_workorder.js";
import { QualityCheck } from "./mrp_record_line/quality_check.js";
import { StockMove } from "./mrp_record_line/stock_move.js";

export class MrpDisplayRecord extends Component {
    static components = {
        CharField,
        Field,
        Many2OneField,
        SelectionField,
        MrpTimerField: mrpTimerField.component,
        PriorityField,
        StockMove,
        MrpWorkorder,
        QualityCheck,
    };
    static props = {
        groups: t.object(),
        barcodeTarget: t.boolean().optional(),
        production: t.object().optional(),
        record: t.object(),
        removeFromCache: t.function(),
        selectWorkcenter: t.function().optional(),
        sessionOwner: t.object(),
        updateEmployees: t.function(),
        workcenters: t.array(),
        demoRecord: t.boolean().optional(),
    };
    static template = "mrp_workorder.MrpDisplayRecord";
    props = useProps(this.constructor.props);

    setup() {
        this.mrpDisplayContext = useMrpDisplayContext();
        this.searchModel = useSearchModel();
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.state = proxy({
            underValidation: false,
        });
        this.resModel = this.props.record.resModel;
        this.model = this.props.record.model;
        this.record = this.props.record.data;
        this.props.record.component = this;

        this.quantityToProduce =
            this.record.qty_remaining ||
            this.record.product_qty ||
            this.props.production.data.product_qty;
        this.displayUOM = this.props.groups.uom;

        onWillUpdateProps((nextProps) => {
            this.resModel = nextProps.record.resModel;
            this.model = nextProps.record.model;
            this.record = nextProps.record.data;
        });
    }

    /**
     * Opens a confirmation dialog to register the produced quantity and set the
     * tracking number if it applies.
     */
    async registerProduction() {
        if (!this.props.production.data.qty_producing) {
            this.props.production.update({
                qty_producing: this.props.production.data.product_qty,
            });
        }
        if (
            this.props.production.data.product_tracking === "serial" &&
            this.props.production.data.product_qty > 1
        ) {
            const action = await this.props.record.model.orm.call(
                this.props.record.resModel,
                "action_generate_serial",
                [this.props.record.resId],
            );
            if (action && typeof action === "object") {
                return this.action.doAction(action, {
                    onClose: () => this.mrpDisplayContext.reload(),
                });
            }
            return;
        }
        const title = _t(
            "Register Production: %s",
            this.props.production.data.product_id.display_name,
        );
        const params = {
            record: this.props.production,
            reload: this.mrpDisplayContext.reload.bind(this),
            title,
            qtyToProduce: this.record.qty_remaining,
        };
        if (this.props.record.resModel === "mrp.workorder") {
            params.workorderId = this.props.record.resId;
        }
        this.dialog.add(MrpRegisterProductionDialog, params);
    }

    editLogNote(ev) {
        const title = _t("Log Note");
        const reload = () => this.mrpDisplayContext.reload();
        const params = { body: "", record: this.props.production, reload, title };
        ev.stopPropagation();
        this.dialog.add(MrpLogNoteDialog, params);
    }

    get quantityProducing() {
        return this.props.production.data.qty_producing;
    }

    get quantityToDisplay() {
        const fullQty =
            this.quantityProducing && this.quantityProducing !== this.quantityToProduce;
        const qtyProducing = fullQty ? `${this.quantityProducing} / ` : "";
        return `${qtyProducing}${this.quantityToProduce} ${this.uom}`;
    }

    get cssClass() {
        const active = this.props.record.data.employee_ids.records.length
            ? "o_active"
            : "";
        const disabled = this.disabled ? "o_disabled" : "";
        const demo = this.props.demoRecord ? "o_demo" : "";
        return `${active} ${disabled} ${demo}`;
    }

    get displayDoneButton() {
        return this.resModel === "mrp.production"
            ? this.props.record.data.picking_type_auto_close
            : this._workorderDisplayDoneButton();
    }

    get byProducts() {
        if (this.resModel === "mrp.workorder") {
            const checks = this.props.record.data.check_ids.records;
            const checked_byproducts = checks.reduce((result, current) => {
                if (current.data.test_type === "register_byproducts") {
                    return [...result, current.data.component_id.id];
                }
                return result;
            }, []);
            return this.props.production.data.move_byproduct_ids.records.filter(
                (bp) =>
                    !checked_byproducts.includes(bp.data.product_id.id) &&
                    ((!bp.data.byproduct_id && !bp.data.operation_id) ||
                        bp.data.operation_id.id ===
                            this.props.record.data.operation_id.id),
            );
        }
        return this.props.record.data.move_byproduct_ids.records;
    }

    get checks() {
        if (this.resModel === "mrp.production") {
            return [];
        }

        const checks = this.props.record.data.check_ids.records;
        const sortedChecks = [];
        if (checks.length) {
            let check = checks.find((qc) => !qc.data.previous_check_id);
            sortedChecks.push(check);
            while (check.data.next_check_id) {
                check = checks.find((qc) => qc.resId === check.data.next_check_id.id);
                sortedChecks.push(check);
            }
        }

        return sortedChecks;
    }

    get moves() {
        const moMoves = this.props.production.data.move_raw_ids.records.filter(
            (move) =>
                !move.data.scrapped &&
                !move.data.bom_line_id &&
                !move.data.workorder_id,
        );
        if (this.resModel === "mrp.production") {
            return moMoves;
        }
        const woMovesNoCheck = this.props.record.data.move_raw_ids.records.filter(
            (move) =>
                !move.data.scrapped &&
                move.data.workorder_id.id === this.props.record.data.id &&
                !move.data.check_id.count,
        );
        return [...woMovesNoCheck, ...moMoves];
    }

    get workorders() {
        if (this.resModel === "mrp.workorder") {
            return [];
        }
        return this.props.record.data.workorder_ids.records.filter(
            (wo) => !["blocked"].includes(wo.data.state),
        );
    }

    get logNote() {
        return this.props.production.data.log_note;
    }

    get showAssignedEmployees() {
        return (
            this.props.record.resModel === "mrp.workorder" &&
            !this.props.isMyWO &&
            !this.record.is_user_working &&
            this.record.employee_assigned_ids &&
            this.record.employee_assigned_ids.resIds.length < 14
        );
    }

    subRecordProps(subRecord) {
        const props = {
            clickable: !this.state.underValidation && !this.disabled,
        };
        if (
            subRecord.resModel === "quality.check" &&
            ["register_consumed_materials", "register_byproducts"].includes(
                subRecord.data.test_type,
            )
        ) {
            props.check = subRecord;
            props.isCurrent =
                this.active &&
                subRecord.resId === this.props.record.data.current_quality_check_id.id;
            const moves =
                subRecord.data.test_type === "register_consumed_materials"
                    ? this.props.production.data.move_raw_ids
                    : this.props.production.data.move_byproduct_ids;
            subRecord = moves.records.find((m) =>
                m.data.check_id.resIds.includes(subRecord.resId),
            );
            props.displayUOM = this.displayUOM;
            props.production = this.props.production;
            props.startWorking = this.startWorking.bind(this);
            props.production = this.props.production;
        } else if (subRecord.resModel === "stock.move") {
            props.displayUOM = this.displayUOM;
            props.isCurrent = false;
            props.startWorking = this.startWorking.bind(this);
            props.production = this.props.production;
        }
        props.record = subRecord;

        if (subRecord.resModel === "quality.check") {
            props.isCurrent =
                this.active &&
                subRecord.resId === this.props.record.data.current_quality_check_id.id;
            props.startWorking = this.startWorking.bind(this);
            if (subRecord.data.test_type === "register_production") {
                props.registerProduction = this.registerProduction.bind(this);
                props.qtyProducing = `${this.quantityProducing} / ${this.quantityToProduce} ${this.uom}`;
            }
        } else if (subRecord.resModel === "mrp.workorder") {
            props.selectWorkcenter = this.props.selectWorkcenter;
            props.clickable =
                subRecord.data.state !== "done" &&
                this.props.workcenters
                    .map((wc) => wc.id)
                    .includes(subRecord.data.workcenter_id.id);
            props.sessionOwnerId = this.props.sessionOwner.id;
        }
        return props;
    }

    get active() {
        return this.props.record.data.employee_ids.records.some(
            (e) => e.resId === this.props.sessionOwner.id,
        );
    }

    get disabled() {
        if (this.props.demoRecord || this.state.underValidation) {
            return true;
        }
        if (
            this.resModel === "mrp.workorder" &&
            !this.props.record.data.all_employees_allowed &&
            !this.props.record.data.allowed_employees.currentIds.includes(
                this.props.sessionOwner.id,
            )
        ) {
            return true;
        }
        return this.props.groups.workorders && !this.props.sessionOwner.id;
    }

    get trackingMode() {
        return this.props.production.data.product_tracking;
    }

    onClickHeader() {
        this.searchModel.removeMOFilter();
        return this.startWorking(true);
    }

    onClickOpenMenu() {
        if (this.props.demoRecord) {
            return;
        }
        const params = {
            workcenters: this.props.workcenters,
            checks: this.checks,
        };
        this.dialog.add(MrpMenuDialog, {
            groups: this.props.groups,
            title: _t("Options"),
            record: this.props.record,
            params,
            reload: this.mrpDisplayContext.reload.bind(this),
            removeFromCache: this.props.removeFromCache,
            registerProduction: this.registerProduction.bind(this),
        });
    }

    async validate() {
        this.state.underValidation = true;
        let { resModel, resId } = this.props.record;
        let methodName = "button_mark_done";
        const kwargs = {};
        if (resModel === "mrp.workorder") {
            if (this.record.state === "ready" && this.record.qty_producing === 0) {
                this.props.record.update({ qty_producing: this.record.qty_production });
            }
            this.validatingEmployee = this.props.sessionOwner.id;
            if (
                this.props.record.data.employee_ids.records.some(
                    (emp) => emp.resId === this.validatingEmployee,
                )
            ) {
                await this.model.orm.call(resModel, "stop_employee", [
                    resId,
                    [this.validatingEmployee],
                ]);
                await this.props.record.load();
            }
            await this.props.record.save();
            methodName = "do_finish";
            kwargs.context = { no_start_next: true, mrp_display: true };
            if (this.validatingEmployee) {
                kwargs.context.employee_id = this.validatingEmployee;
            }
        }
        if (
            resModel === "mrp.production" ||
            (this.props.production.data.picking_type_auto_close &&
                this.record.is_last_unfinished_wo)
        ) {
            methodName = "button_mark_done";
            resModel = "mrp.production";
            resId = this.props.production.resId;
        }
        let automaticBackorderCreation;
        try {
            const action = await this.model.orm.call(
                resModel,
                methodName,
                [resId],
                kwargs,
            );
            if (action && typeof action === "object") {
                if (action.context?.marked_as_done) {
                    automaticBackorderCreation = true;
                } else {
                    if (action.context) {
                        action.context.skip_redirection = true;
                    }
                    return this._doAction(action);
                }
            }
        } catch (error) {
            this.state.underValidation = false;
            throw error;
        }
        if (resModel === "mrp.production" && !automaticBackorderCreation) {
            // Manually remove the parent MO from the model, to avoid a full reload.
            const productions_root = this.props.production.model.root;
            productions_root.records.splice(
                productions_root.records.findIndex(
                    (r) => r.resId === this.props.production.resId,
                ),
                1,
            );
            productions_root.count--;
        } else {
            this.props.removeFromCache(resId);
            if (this.quantityProducing < this.quantityToProduce) {
                // To make sure we see any potentially created backorders
                await this.mrpDisplayContext.reload();
            } else {
                await this.mrpDisplayContext.reload(this.props.production);
            }
            this.state.underValidation = false;
        }
        this.searchModel.removeMOFilter();
    }

    _doAction(action) {
        return this.action.doAction(action, {
            onClose: () => {
                this.mrpDisplayContext.reload();
            },
        });
    }

    openFormView() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.record.resModel,
            views: [[false, "form"]],
            res_id: this.props.record.resId,
        });
    }

    get uom() {
        if (this.displayUOM) {
            return this.record.product_uom_id?.display_name;
        }
        return this.quantityToProduce === 1 ? _t("Unit") : _t("Units");
    }

    _workorderDisplayDoneButton() {
        return (
            ["pending", "waiting", "ready", "progress"].includes(this.record.state) &&
            this.record.check_ids.records.every((qc) =>
                ["pass", "fail"].includes(qc.data.quality_state),
            )
        );
    }

    async startWorking(shouldStop = false) {
        const { resModel, resId } = this.props.record;
        if (resModel !== "mrp.workorder") {
            return;
        }
        await this.props.updateEmployees();
        const admin_id = this.props.sessionOwner.id;
        if (
            admin_id &&
            !this.props.record.data.employee_ids.resIds.includes(admin_id)
        ) {
            await this.model.orm.call(resModel, "button_start", [resId], {
                context: { mrp_display: true },
            });
            await this.mrpDisplayContext.reload(this.props.production);
        } else if (shouldStop) {
            await this.model.orm.call(resModel, "stop_employee", [resId, [admin_id]]);
            await this.mrpDisplayContext.reload(this.props.production);
        }
        return this.props.updateEmployees();
    }
}
