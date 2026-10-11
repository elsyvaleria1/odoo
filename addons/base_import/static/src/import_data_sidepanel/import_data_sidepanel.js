/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { useDebugMode } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import { DocumentationLink } from "@web/views/widgets";

export class ImportDataSidepanel extends Component {
    static template = "ImportDataSidepanel";
    static components = { CheckBox, DocumentationLink };
    static props = {
        filename: t.string(),
        formattingOptions: t.object().optional(),
        options: t.object(),
        importTemplates: t.array().optional(),
        isBatched: t.boolean().optional(),
        onOptionChanged: t.function(),
        onReload: t.function(),
        hasBinaryFields: t.boolean(),
        binaryFilesParams: t.object(),
        onBinaryFilesParamsChanged: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }

    get fileName() {
        const lastDot = this.props.filename.lastIndexOf(".");
        return lastDot === -1
            ? this.props.filename
            : this.props.filename.slice(0, lastDot);
    }

    get fileExtension() {
        return "." + this.props.filename.split(".").pop();
    }

    getOptionValue(name) {
        if (name === "skip") {
            return (this.props.options.skip + 1).toString();
        }
        return this.props.options[name].toString();
    }

    setOptionValue(name, value) {
        this.props.onOptionChanged(
            name,
            isNaN(parseFloat(value)) ? value : Number(value),
        );
    }

    onLimitChange(ev) {
        const line = Number.parseInt(ev.target.value, 10);
        const skip = Number.isInteger(line) && line > 1 ? line - 1 : 0;
        this._echo(ev.target, skip + 1);
        this.props.onOptionChanged("skip", skip);
    }

    onBatchLimitChange(ev) {
        const limit = Number.parseInt(ev.target.value, 10);
        const clamped = Number.isInteger(limit) && limit > 0 ? limit : 1;
        this._echo(ev.target, clamped);
        this.props.onOptionChanged("limit", clamped);
    }

    _echo(input, value) {
        input.value = value.toString();
    }

    isOptionApplicable(option) {
        return !option.csvOnly || this.fileExtension.toLowerCase() === ".csv";
    }

    get binaryFilesLabel() {
        const files = this.props.binaryFilesParams.binaryFiles.value;
        const number = Object.keys(files).length;
        if (number > 0) {
            return _t("%(number)s file(s) selected", { number });
        }
        return _t("No file selected");
    }
}
