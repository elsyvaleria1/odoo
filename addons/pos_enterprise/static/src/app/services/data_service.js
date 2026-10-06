/** @odoo-module native */
import { PosData } from "@point_of_sale/app/services/data_service";
import { patch } from "@web/core/utils/patch";

// The preparation display reuses the PosData service with a different data
// pipeline (it loads pos.prep.display data instead of a PoS session). This patch
// is pulled into the shared web.assets_unit_tests_setup bundle, so it applies to
// every PoS unit test — including point_of_sale's own, which never set
// odoo.preparation_display and expect the stock PosData behaviour. Guard every
// override so it only takes effect when a preparation-display context is present
// (the prep-display app and its tests); otherwise fall back to the original
// method. Without this, point_of_sale unit tests crash on
// `odoo.preparation_display.id` (undefined) during data_service setup.
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
