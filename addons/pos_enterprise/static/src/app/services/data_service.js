/** @odoo-module native */
import { PosData } from "@point_of_sale/app/services/data_service";
import { patch } from "@web/core/utils/patch";

export const unpatchPrepDataService = patch(PosData.prototype, {
    async loadInitialData() {
        if (!odoo.preparation_display) {
            return super.loadInitialData(...arguments);
        }
        const pdisId = odoo.preparation_display.id;
        return await this.orm.call("pos.prep.display", "load_preparation_data", [
            parseInt(pdisId),
        ]);
    },
    async loadFieldsAndRelations() {
        if (!odoo.preparation_display) {
            return super.loadFieldsAndRelations(...arguments);
        }
        const pdisId = odoo.preparation_display.id;
        return await this.orm.call("pos.prep.display", "load_data_params", [
            parseInt(pdisId),
        ]);
    },
    async initData(hard = false, limit = true) {
        if (!odoo.preparation_display) {
            return super.initData(...arguments);
        }
        const data = await this.loadInitialData(hard, limit);

        this.models.loadConnectedData(data, this.modelToLoad);
    },
    async initializeDeviceIdentifier() {
        if (!odoo.preparation_display) {
            return super.initializeDeviceIdentifier(...arguments);
        }
        return false;
    },
    initializeWebsocket() {
        if (!odoo.preparation_display) {
            return super.initializeWebsocket(...arguments);
        }
        return false;
    },
    initIndexedDB() {
        if (!odoo.preparation_display) {
            return super.initIndexedDB(...arguments);
        }
        return false;
    },
    initListeners() {
        if (!odoo.preparation_display) {
            return super.initListeners(...arguments);
        }
        return false;
    },
    syncLocalDataInIndexedDB() {
        if (!odoo.preparation_display) {
            return super.syncLocalDataInIndexedDB(...arguments);
        }
        return true;
    },
    async getCachedServerDataFromIndexedDB() {
        if (!odoo.preparation_display) {
            return super.getCachedServerDataFromIndexedDB(...arguments);
        }
        return {};
    },
    async getLocalDataFromIndexedDB() {
        if (!odoo.preparation_display) {
            return super.getLocalDataFromIndexedDB(...arguments);
        }
        return {};
    },
    async missingRecursive(recordMap) {
        if (!odoo.preparation_display) {
            return super.missingRecursive(...arguments);
        }
        return recordMap;
    },
    async deleteRecordsInIndexedDB(model, ids) {
        if (!odoo.preparation_display) {
            return super.deleteRecordsInIndexedDB(...arguments);
        }
        return true;
    },
});
