/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { _t } from "@web/core/translation";
import { Dialog } from "@web/ui/dialog";
const log = makeLogger("pos.popup.retry_print");
export class RetryPrintPopup extends Component {
    static template = "point_of_sale.RetryPrintPopup";
    static components = { Dialog };
    static props = {
        title: t.string().optional(_t("Printing failed")),
        message: t
            .string()
            .optional(
                _t(
                    "An unknown error occurred. Do you want to download the receipt instead?",
                ),
            ),
        canRetry: t.boolean().optional(),
        download: t.function().optional(),
        retry: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    onClickDownload() {
        log.logic("download", () => ({ title: this.props.title }));
        this.props.download();
        this.props.close();
    }

    onClickRetry() {
        log.logic("retry", () => ({
            title: this.props.title,
            canRetry: this.props.canRetry,
        }));
        this.props.retry();
        this.props.close();
    }
}
