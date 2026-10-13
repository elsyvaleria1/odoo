/** @odoo-module native */
import { EventBus } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { Mutex } from "@web/core/utils/concurrency";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MasterProductionScheduleModel extends EventBus {
    constructor(params, services) {
        super();
        this.domain = [];
        this.offset = 0;
        this.limit = false;
        this.params = params;
        this.orm = services.orm;
        this.action = services.action;
        this.dialog = services.dialog;
        this.selectedRecords = new Set();
        this.mutex = new Mutex();
    }

    async load(domain, offset, limit, scale) {
        if (domain !== undefined) {
            this.domain = domain;
        }
        if (offset !== undefined) {
            this.offset = offset;
        }
        if (limit !== undefined) {
            this.limit = limit;
        }
        if (scale !== undefined) {
            this.scale = scale;
        }
        this.data = await this.orm.call(
            "mrp.production.schedule",
            "get_mps_view_state",
            [this.domain, this.offset, this.limit, this.scale],
        );
        this.notify();
    }

    async reload(productionScheduleId) {
        return await this.orm
            .call("mrp.production.schedule", "get_impacted_schedule", [
                productionScheduleId,
                this.domain,
            ])
            .then((productionScheduleIds) => {
                productionScheduleIds.push(productionScheduleId);
                const visibleScheduleIds = new Set(
                    this.data.production_schedule_ids.map((ps) => ps.id),
                );
                const filteredScheduleIds = productionScheduleIds.filter((id) =>
                    visibleScheduleIds.has(id),
                );
                return this.orm.call(
                    "mrp.production.schedule",
                    "get_production_schedule_view_state",
                    [filteredScheduleIds, this.scale],
                );
            })
            .then((production_schedule_ids) => {
                for (let i = 0; i < production_schedule_ids.length; i++) {
                    const index = this.data.production_schedule_ids.findIndex(
                        (ps) => ps.id === production_schedule_ids[i].id,
                    );
                    if (index >= 0) {
                        this.data.production_schedule_ids.splice(
                            index,
                            1,
                            production_schedule_ids[i],
                        );
                    } else {
                        this.data.production_schedule_ids.push(
                            production_schedule_ids[i],
                        );
                    }
                }
                this.notify();
            });
    }

    notify() {
        this.unselectAll();
        this.trigger("update");
    }

    /**
     * @private
     * @param {Integer[]} productionScheduleIds
     * @return {Promise}
     */
    _actionReplenish(productionScheduleIds, basedOnLeadTime = false) {
        this.mutex.exec(() =>
            this.orm
                .call("mrp.production.schedule", "action_replenish", [
                    productionScheduleIds,
                    basedOnLeadTime,
                ])
                .then(() => {
                    if (productionScheduleIds.length === 1) {
                        this.reload(productionScheduleIds[0]);
                    } else {
                        this.load();
                    }
                }),
        );
    }

    replenishAll() {
        this.orm.search("mrp.production.schedule", this.domain).then((ids) => {
            this._actionReplenish(ids, true);
        });
    }

    replenishSelectedRecords() {
        this._actionReplenish(Array.from(this.selectedRecords), false);
    }

    /**
     * @private
     * @param {Integer} productionScheduleId
     * @param {Integer} dateIndex
     * @param {Float} forecastQty
     * @return {Promise}
     */
    _saveForecast(productionScheduleId, dateIndex, forecastQty) {
        return this.mutex.exec(() => {
            this.orm
                .call("mrp.production.schedule", "set_forecast_qty", [
                    productionScheduleId,
                    dateIndex,
                    forecastQty,
                    this.scale,
                ])
                .then(() => this.reload(productionScheduleId));
        });
    }

    /**
     * @private
     * @return {Promise}
     */
    _createProduct() {
        this.mutex.exec(() => {
            this.action.doAction("mrp_mps.action_mrp_mps_form_view", {
                onClose: () => this.load(),
            });
        });
    }

    /**
     * @private
     * @param {Integer} productionScheduleId
     */
    _editProduct(productionScheduleId) {
        this.mutex.exec(() => {
            this.action.doAction(
                {
                    name: "Edit Production Schedule",
                    type: "ir.actions.act_window",
                    res_model: "mrp.production.schedule",
                    views: [[false, "form"]],
                    target: "new",
                    res_id: productionScheduleId,
                },
                {
                    onClose: () => {
                        this.reload(productionScheduleId);
                    },
                },
            );
        });
    }

    /**
     * @private
     * @param {Integer[]} productionScheduleIds
     * @return {Promise}
     */
    _unlinkProduct(productionScheduleIds) {
        function doIt() {
            this.mutex.exec(async () =>
                Promise.all(
                    productionScheduleIds.map((id) =>
                        this.orm.unlink("mrp.production.schedule", [id]),
                    ),
                ).then(() => {
                    for (const productionScheduleId of productionScheduleIds) {
                        const index = this.data.production_schedule_ids.findIndex(
                            (ps) => ps.id === productionScheduleId,
                        );
                        this.data.production_schedule_ids.splice(index, 1);
                    }
                    this.notify();
                }),
            );
        }
        const body =
            productionScheduleIds.length > 1
                ? _t("Are you sure you want to delete these records?")
                : _t("Are you sure you want to delete this record?");
        this.dialog.add(ConfirmationDialog, {
            body: body,
            title: _t("Confirmation"),
            confirm: doIt.bind(this),
        });
    }

    unlinkSelectedRecord() {
        return this._unlinkProduct(Array.from(this.selectedRecords));
    }

    /**
     * @param {Integer} productionScheduleId
     * @param {String} action
     * @param {String} dateStr
     * @param {String} dateStart
     * @param {String} dateStop
     * @return {Promise}
     */
    _actionOpenDetails(productionScheduleId, action, dateStr, dateStart, dateStop) {
        this.mutex.exec(() =>
            this.orm
                .call("mrp.production.schedule", action, [
                    productionScheduleId,
                    dateStr,
                    dateStart,
                    dateStop,
                ])
                .then((action) => this.action.doAction(action)),
        );
    }

    /**
     * @private
     * @param {Integer} productionScheduleId
     * @param {Integer} dateIndex
     * @param {Float} replenishQty
     * @return {Promise}
     */
    _saveToReplenish(productionScheduleId, dateIndex, replenishQty) {
        return this.mutex.exec(() => {
            this.orm
                .call("mrp.production.schedule", "set_replenish_qty", [
                    productionScheduleId,
                    dateIndex,
                    replenishQty,
                    this.scale,
                ])
                .then(() => this.reload(productionScheduleId));
        });
    }

    /**
     * @private
     * @param {Integer} productionScheduleId
     * @param {Integer} dateIndex
     * @return {Promise}
     */
    _removeQtyToReplenish(productionScheduleId, dateIndex) {
        return this.mutex.exec(() => {
            this.orm
                .call("mrp.production.schedule", "remove_replenish_qty", [
                    productionScheduleId,
                    dateIndex,
                    this.scale,
                ])
                .then(() => this.reload(productionScheduleId));
        });
    }

    _getOriginValue(productionScheduleId, dateIndex, inputName) {
        return this.data.production_schedule_ids.find(
            (ps) => ps.id === productionScheduleId,
        ).forecast_ids[dateIndex][inputName];
    }

    /**
     * @private
     * @param {Object} values
     */
    _saveCompanySettings(values) {
        this.mutex.exec(() => {
            this.orm
                .call("res.company", "save_company_settings", [
                    this.data.company_id,
                    values,
                ])
                .then(() => {
                    this.load();
                });
        });
    }

    mouseOverReplenish() {
        this.trigger("mouse-over");
    }

    mouseOutReplenish() {
        this.trigger("mouse-out");
    }

    selectAll() {
        this.data.production_schedule_ids.map(({ id }) => this.selectedRecords.add(id));
    }

    unselectAll() {
        this.selectedRecords.clear();
    }

    toggleRecordSelection(productionScheduleId) {
        if (this.selectedRecords.has(productionScheduleId)) {
            this.selectedRecords.delete(productionScheduleId);
        } else {
            this.selectedRecords.add(productionScheduleId);
        }
        this.trigger("update");
    }

    toggleSelection() {
        if (this.selectedRecords.size === this.data.production_schedule_ids.length) {
            this.unselectAll();
        } else {
            this.selectAll();
        }
        this.trigger("update");
    }

    _toggleIsIndirect(productionScheduleIds) {
        this.mutex.exec(() =>
            this.orm
                .call("mrp.production.schedule", "action_toggle_is_indirect", [
                    productionScheduleIds,
                ])
                .then(() => {
                    if (productionScheduleIds.length === 1) {
                        this.reload(productionScheduleIds[0]);
                    } else {
                        this.load();
                    }
                }),
        );
    }

    toggleIsIndirect() {
        return this._toggleIsIndirect(Array.from(this.selectedRecords));
    }
}
