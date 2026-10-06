/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { CopyButton } from "@web/components/copy_button";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { _t } from "@web/core/translation";

export const LANGUAGES = {
    plaintext: _t("Plain Text"),
    markdown: _t("Markdown"),
    javascript: _t("Javascript"),
    typescript: _t("Typescript"),
    jsdoc: _t("JSDoc"),
    java: _t("Java"),
    python: _t("Python"),
    html: _t("HTML"),
    xml: _t("XML"),
    svg: _t("SVG"),
    json: _t("JSON"),
    css: _t("CSS"),
    sass: _t("SASS"),
    scss: _t("SCSS"),
    sql: _t("SQL"),
    diff: _t("Diff"),
};

export class CodeToolbar extends Component {
    static template = "html_editor.CodeToolbar";
    static props = {
        target: t.customValidator(t.any(), (el) => el.nodeType === Node.ELEMENT_NODE),
        getContent: t.function(),
        onLanguageChange: t.function(),
        currentLanguage: t.string(),
        convertToParagraph: t.function(),
    };
    static components = { Dropdown, DropdownItem, CopyButton };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.languages = LANGUAGES;
    }
}
