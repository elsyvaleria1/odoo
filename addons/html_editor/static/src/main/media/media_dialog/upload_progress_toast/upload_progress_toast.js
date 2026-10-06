/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";

export class ProgressBar extends Component {
    static template = "html_editor.ProgressBar";
    static props = {
        progress: t.number().optional(0),
        hasError: t.boolean().optional(false),
        uploaded: t.boolean().optional(false),
        name: t.string(),
        size: t.string().optional(""),
        errorMessage: t.string().optional(""),
    };
    props = useProps(this.constructor.props);

    get errorMessage() {
        return this.props.errorMessage || _t("File could not be saved");
    }

    get progress() {
        return Math.round(this.props.progress);
    }
}

export class UploadProgressToast extends Component {
    static template = "html_editor.UploadProgressToast";
    static components = {
        ProgressBar,
    };
    static props = { close: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        this.uploadService = useService("upload");
        this.state = proxy(this.uploadService.progressToast);
    }
}
