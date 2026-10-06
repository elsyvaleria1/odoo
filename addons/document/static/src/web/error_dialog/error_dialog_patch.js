/** @odoo-module native */
import { ErrorDialog } from "@web/components/errors";
import { browser } from "@web/core/browser/browser";
import { FileUploadEvent } from "@web/core/events";
import { formatValue, now } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { uniqueId } from "@web/core/utils/functions";
import { useBus, useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

// the upload's form field naming the dialog that shared it
const TRACEBACK_MARKER = "documents_traceback";

patch(ErrorDialog.prototype, {
    setup() {
        super.setup();
        this.fileUpload = useService("file_upload");
        this.notification = useService("notification");
        this.canShareTraceback = user.isInternalUser;
        this.tracebackMarker = uniqueId("traceback_");
        this.state.tracebackUrl = null;
        this.state.processed = false;
        // every open error dialog hears every upload: only its own is its link
        const isOwnUpload = (upload) =>
            upload.data?.get(TRACEBACK_MARKER) === this.tracebackMarker;
        useBus(this.fileUpload.bus, FileUploadEvent.ERROR, ({ detail }) => {
            if (isOwnUpload(detail.upload)) {
                // the service said why; Share may be tried again
                this.state.processed = false;
            }
        });
        useBus(this.fileUpload.bus, FileUploadEvent.LOADED, ({ detail }) => {
            const { upload } = detail;
            if (!isOwnUpload(upload)) {
                return;
            }
            const response = upload.response;
            if (!Array.isArray(response) || response.length !== 1) {
                this.state.processed = false;
                return;
            }
            this.state.tracebackUrl = response[0];
            // Deferred so the upload service finishes its own bookkeeping
            // first; the copy is best effort, the URL is on screen anyway.
            setTimeout(async () => {
                try {
                    await browser.navigator.clipboard.writeText(response[0]);
                } catch {
                    return;
                }
                this.notification.add(
                    _t("The document URL has been copied to your clipboard."),
                    { type: "success" },
                );
            });
        });
    },
    shareTraceback() {
        if (this.state.processed) {
            return;
        }
        this.state.processed = true;
        const when = formatValue(now(), "yyyy-MM-dd HH:mm:ss");
        const file = new File([this.clipboardReport], `${this.title} - ${when}.txt`, {
            type: "text/plain",
        });
        this.fileUpload.upload("/documents/upload_traceback", [file], {
            buildFormData: (formData) =>
                formData.append(TRACEBACK_MARKER, this.tracebackMarker),
        });
    },
});
