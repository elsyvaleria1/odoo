/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { Deferred, Mutex } from "@web/core/utils/concurrency";

import {
    getImageThumbnail,
    getPdfThumbnail,
} from "./document_client_thumbnail_service_utils.js";

const log = makeLogger("document.thumbnail");

const THUMBNAIL_WIDTH = 200;
const THUMBNAIL_HEIGHT = 140;

export const documentsClientThumbnailService = {
    start(env) {
        let pdfEnabled = true;
        const mutex = new Mutex();
        const queued = new Set();

        const canStore = (record) => record.data.user_permission === "edit";

        const makeThumbnail = async (record) => {
            if (record.data.thumbnail_status !== "client_generated") {
                return;
            }
            let thumbnail = undefined;
            if (record.isPdf()) {
                if (!pdfEnabled) {
                    return;
                }
                let isPdfValid;
                ({ thumbnail, isPdfValid, pdfEnabled } = await this._getPdfThumbnail(
                    record,
                    THUMBNAIL_WIDTH,
                    THUMBNAIL_HEIGHT,
                ));
                if (!pdfEnabled) {
                    return;
                }
                if (isPdfValid === false) {
                    thumbnail = false;
                }
            } else if (record.data.mimetype?.startsWith("image/")) {
                try {
                    const img = await this._getLoadedImage(record);
                    ({ thumbnail } = await getImageThumbnail(
                        img,
                        THUMBNAIL_WIDTH,
                        THUMBNAIL_HEIGHT,
                    ));
                } catch (error) {
                    if (error.status === 403) {
                        return;
                    }
                    thumbnail = false;
                }
            }
            if (thumbnail !== undefined) {
                await rpc(`/documents/document/${record.resId}/update_thumbnail`, {
                    thumbnail,
                });
                record.data.thumbnail_status = thumbnail ? "present" : "error";
            }
        };

        return {
            enqueueRecords(records) {
                if (env.isSmall) {
                    return;
                }
                for (const record of records) {
                    if (
                        record.data.thumbnail_status === "client_generated" &&
                        canStore(record) &&
                        !queued.has(record.resId)
                    ) {
                        queued.add(record.resId);
                        mutex.exec(async () => {
                            const end = log.perf("makeThumbnail");
                            try {
                                await makeThumbnail(record);
                            } catch (error) {
                                log.logic("thumbnail failed", () => ({
                                    resId: record.resId,
                                    error: String(error),
                                }));
                            } finally {
                                end({ resId: record.resId });
                                queued.delete(record.resId);
                            }
                        });
                    }
                }
                return mutex.getUnlockedDef();
            },
        };
    },
    _getPdfThumbnail(record, width, height) {
        return getPdfThumbnail(record, width, height);
    },
    async _getLoadedImage(record) {
        const response = await fetch(
            `/web/content/document.document/${record.resId}/raw`,
        );
        if (!response.ok) {
            const error = new Error(`Thumbnail fetch failed (${response.status})`);
            error.status = response.status;
            throw error;
        }
        const objectUrl = URL.createObjectURL(await response.blob());
        try {
            const imagePromise = new Deferred();
            const img = new Image();
            img.onerror = (e) => imagePromise.reject(e);
            img.onload = () => imagePromise.resolve(img);
            img.src = objectUrl;
            return await imagePromise;
        } finally {
            URL.revokeObjectURL(objectUrl);
        }
    },
};

registry
    .category("services")
    .add("documents_client_thumbnail", documentsClientThumbnailService);
