/** @odoo-module native */
import { _t } from "@web/core/translation";
import { Mutex } from "@web/core/utils/concurrency";
import { checkFileSize } from "@web/core/utils/files";

export class BinaryFileManager {
    constructor(resModel, fields, parameters, context, orm, notificationService) {
        this.resModel = resModel;
        this.fields = [".id", ...fields];
        this.parameters = parameters;

        this.context = context;
        this.orm = orm;
        this.notificationService = notificationService;

        this.maxBatchSize = this.parameters.maxBatchSize * 0.95;
        this.delayAfterEachBatch = this.parameters.delayAfterEachBatch * 1000;

        this.dataToSend = {};
        this.currentSize = 0;

        this.mutex = new Mutex();
    }

    async addFile(id, field, file) {
        if (!checkFileSize(file.size, this.notificationService)) {
            return;
        }

        const indexOfField = this.fields.indexOf(field, 1);
        if (indexOfField === -1) {
            this.notificationService.add(
                _t("Unknown binary field %(field)s, its files were not uploaded.", {
                    field,
                }),
                { type: "danger" },
            );
            return;
        }

        let data = await this._readFile(file);
        if (typeof data === "string" && data.startsWith("data:")) {
            data = data.split(",")[1];
        }
        const dataSize = data.length;

        if (this.getCurrentSize() + dataSize >= this.maxBatchSize) {
            await this.mutex.exec(async () => await this._send());
        }
        if (!(id in this.dataToSend)) {
            this.dataToSend[id] = Array(this.fields.length);
            this.dataToSend[id][0] = id;
        }
        this.dataToSend[id][indexOfField] = data;
        this.currentSize += dataSize;
    }

    async sendLastPayload() {
        if (Object.keys(this.dataToSend).length > 0) {
            await this.mutex.exec(async () => await this._send());
        }
    }

    async _send() {
        const data = Object.values(this.dataToSend);
        this.dataToSend = {};
        this.currentSize = 0;
        if (!data.length) {
            return;
        }
        const context = {
            ...this.context,
            import_file: true,
            tracking_disable: this.parameters.tracking_disable,
            name_create_enabled_fields:
                this.parameters.name_create_enabled_fields || {},
            import_set_empty_fields: this.parameters.import_set_empty_fields || [],
            import_skip_records: this.parameters.import_skip_records || [],
        };
        let res;
        try {
            res = await this.orm.call(this.resModel, "load", [], {
                fields: this.fields,
                data,
                context,
            });
            await new Promise((resolve) => {
                setTimeout(resolve, this.delayAfterEachBatch);
            });
        } catch (error) {
            console.error(error);
            this.notificationService.add(
                _t("Some binary/attachment fields could not be uploaded: %(error)s", {
                    error: error.message || error,
                }),
                { type: "danger" },
            );
            return { error };
        }
        return res;
    }

    _readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onerror = (event) => reject(event);
            reader.onabort = (event) => reject(event);
            reader.onload = (event) => resolve(event.target.result);
            reader.readAsDataURL(file);
        });
    }

    getCurrentSize() {
        return this.currentSize;
    }
}
