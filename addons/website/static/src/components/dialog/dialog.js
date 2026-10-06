/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { _t } from "@web/core/translation";
import { useChildRef } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";

const NO_OP = () => {};

const log = makeLogger("website.dialog.website_dialog");

export class WebsiteDialog extends Component {
    static template = "website.WebsiteDialog";
    static components = { Dialog };
    static props = {
        ...Dialog.props,
        primaryTitle: t.string().optional(_t("Ok")),
        primaryClick: t.function().optional(),
        secondaryTitle: t.string().optional(_t("Cancel")),
        secondaryClick: t.function().optional(),
        showSecondaryButton: t.boolean().optional(true),
        close: t.function().optional(() => NO_OP),
        closeOnClick: t.boolean().optional(true),
        body: t.string().optional(),
        slots: t.object().optional(),
        showFooter: t.boolean().optional(true),
        title: Dialog.props.title.optional(_t("Confirmation")),
        size: Dialog.props.size.optional("md"),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.state = proxy({
            disabled: false,
        });
        this.modalRef = useChildRef();
    }
    /**
     * @param {function|void} handler
     * @returns {() => Promise<void>}
     */
    protectedClick(handler) {
        return async () => {
            if (this.state.disabled) {
                log.logic("protectedClick ignored: already running");
                return;
            }
            this.state.disabled = true;
            const endClick = log.perf("protectedClick handler", () => ({
                hasHandler: Boolean(handler),
            }));
            if (handler) {
                await handler();
            }
            endClick();
            if (this.props.closeOnClick) {
                log.lifecycle("protectedClick close dialog");
                return this.props.close();
            }
            this.state.disabled = false;
        };
    }

    get contentClasses() {
        const websiteDialogClass = "o_website_dialog";
        if (this.props.contentClass) {
            return `${websiteDialogClass} ${this.props.contentClass}`;
        }
        return websiteDialogClass;
    }
}
