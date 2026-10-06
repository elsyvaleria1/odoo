/** @odoo-module native */
import { loadBundle } from "@web/core/assets";
import { makeLogger } from "@web/core/debug/debug_logger";

const log = makeLogger("document_spreadsheet.attachments");

export const XLSX_MIME_TYPES = [
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/wps-office.xlsx",
];

export async function createXlsxAttachment(env, orm, attachmentRecords) {
    const spreadsheetAttachments = attachmentRecords.filter(
        (a) => a.mimetype === "application/o-spreadsheet",
    );
    const regularAttachments = attachmentRecords.filter(
        (a) => a.mimetype !== "application/o-spreadsheet",
    );

    const processed = [...regularAttachments];
    // Nothing to convert: return before pulling in the spreadsheet machinery.
    // The bundle load and the dynamic import used to run unconditionally, so
    // attaching a plain file through "Add from Documents" paid for the whole
    // o_spreadsheet bundle -- and in tests, where that bundle is not served,
    // the await never settled and the caller hung with no error.
    if (!spreadsheetAttachments.length) {
        log.logic("createXlsxAttachment:nothingToConvert", () => ({
            attachments: attachmentRecords.length,
        }));
        return processed;
    }
    log.pipeline("createXlsxAttachment", () => ({
        spreadsheets: spreadsheetAttachments.length,
        regular: regularAttachments.length,
    }));
    const endConvert = log.perf("createXlsxAttachment");

    await loadBundle("spreadsheet.o_spreadsheet");
    const { fetchSpreadsheetModel, waitForDataLoaded } =
        await import("@spreadsheet/helpers/model");

    const originalIdToAttachment = {};
    for (const att of spreadsheetAttachments) {
        originalIdToAttachment[att.original_id[0]] = att;
    }

    const originalIds = Object.keys(originalIdToAttachment).map(Number);

    const documentRecords = await orm.searchRead(
        "document.document",
        [["attachment_id", "in", originalIds]],
        ["id", "attachment_id"],
    );
    const spreadsheetPayload = [];

    for (const doc of documentRecords) {
        const model = await fetchSpreadsheetModel(env, "document.document", doc.id);
        await waitForDataLoaded(model);

        const originalAttachment = originalIdToAttachment[doc.attachment_id[0]];
        const files = model.exportXLSX().files;
        spreadsheetPayload.push({
            name: `${originalAttachment.name}.xlsx`,
            files,
            res_model: originalAttachment.res_model,
            res_id: originalAttachment.res_id,
        });
    }

    const xlsxAttachments = await orm.call(
        "document.document",
        "create_xlsx_attachment_from_spreadsheet",
        [spreadsheetPayload],
    );

    // Unlink old .o-spreadsheet attachments that we copied
    const idsToUnlink = spreadsheetAttachments.map((att) => att.id);
    if (idsToUnlink.length) {
        await orm.unlink("ir.attachment", idsToUnlink);
    }

    endConvert({
        documents: documentRecords.length,
        created: xlsxAttachments.length,
        unlinked: idsToUnlink.length,
    });
    return processed.concat(xlsxAttachments);
}
