/** @odoo-module native */
import { DYNAMIC_PLACEHOLDER_PLUGINS } from "@html_editor/backend/plugin_sets";
import { HtmlField, htmlField } from "@html_editor/fields/html_field";
import { LocalOverlayContainer } from "@html_editor/local_overlay_container";
import { PowerButtonsPlugin } from "@html_editor/main/power_buttons_plugin";
import { MAIN_PLUGINS as MAIN_EDITOR_PLUGINS } from "@html_editor/plugin_sets";
import { normalizeHTML, parseHTML } from "@html_editor/utils/html";
import {
    getCSSRules,
    toInline,
} from "@mail/views/web/fields/html_mail_field/convert_inline";
import { MassMailingIframe } from "@mass_mailing/iframe/mass_mailing_iframe";
import { ThemeSelector } from "@mass_mailing/themes/theme_selector/theme_selector";
import { onWillUpdateProps, status, t, toRaw } from "@odoo/owl";
import { loadBundle } from "@web/core/assets";
import { useDebugMode } from "@web/core/debug/debug_context";
import { Domain } from "@web/core/domain";
import { registry } from "@web/core/registry";
import { Deferred } from "@web/core/utils/concurrency";
import { elementRef } from "@web/core/utils/element_ref";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { batched } from "@web/core/utils/timing";

export class MassMailingHtmlField extends HtmlField {
    static template = "mass_mailing.HtmlField";
    static components = {
        ...HtmlField.components,
        LocalOverlayContainer,
        MassMailingIframe,
        ThemeSelector,
    };
    static props = {
        ...HtmlField.props,
        inlineField: t.string(),
        filterTemplates: t.boolean().optional(),
    };

    setup() {
        let props = this.props;
        onWillUpdateProps((nextProps) => {
            if (nextProps !== this.props) {
                props = nextProps;
            }
        });
        super.setup();
        this.debug = useDebugMode();
        this.themeService = useService("mass_mailing.themes");
        this.ui = useService("ui");
        Object.assign(this.state, {
            showThemeSelector: this.props.record.isNew,
            activeTheme: undefined,
        });

        if (this.state.showThemeSelector) {
            loadBundle("mass_mailing.assets_builder");
        }

        this.resetIframe();
        this.iframeRef = useChildRef();
        this.codeViewButtonRef = elementRef();

        onWillUpdateProps((nextProps) => {
            if (
                this.props.readonly !== nextProps.readonly &&
                (this.props.readonly || nextProps.readonly)
            ) {
                this.state.key++;
            }
            if (nextProps.readonly) {
                toRaw(this.state).showThemeSelector = false;
            }
            if (nextProps.record.isNew) {
                Object.assign(toRaw(this.state), {
                    activeTheme: undefined,
                    showCodeView: false,
                    showThemeSelector: true,
                });
            }
        });

        let currentKey = this.state.key;
        effect(
            batched((state) => {
                if (status(this) === "destroyed") {
                    return;
                }
                if (state.key !== currentKey) {
                    this.resetIframe();
                    this.updateActiveTheme(props.record);
                    this.updateThemeSelector(props);
                    currentKey = state.key;
                }
            }),
            [this.state],
        );

        useLayoutEffect(
            () => {
                if (!this.codeViewRef.el) {
                    return;
                }
                this.codeViewRef.el.style.height =
                    this.codeViewRef.el.scrollHeight + "px";
            },
            () => [this.codeViewRef.el],
        );
    }

    get withBuilder() {
        return !this.props.readonly && this.state.activeTheme !== "basic";
    }

    resetIframe() {
        this.iframeLoaded = new Deferred();
    }

    async ensureIframeLoaded() {
        const iframeLoaded = this.iframeLoaded;
        const iframeInfo = await iframeLoaded;
        return iframeLoaded === this.iframeLoaded ? iframeInfo : undefined;
    }

    onIframeLoad(key, iframeLoaded) {
        if (key !== this.state.key) {
            return;
        }
        this.iframeLoaded.resolve(iframeLoaded);
    }

    updateActiveTheme(record = this.props.record) {
        const state = toRaw(this.state);
        const getThemeName = () => {
            const value = record.data[this.props.name];
            if (!value || !value.toString()) {
                return;
            }
            const fragment = parseHTML(document, value);
            const layout = fragment.querySelector(".o_layout");
            if (!layout) {
                return "unknown";
            }
            return this.themeService.getThemeName(layout.classList) || "unknown";
        };
        const activeTheme = getThemeName();
        if (state.activeTheme !== activeTheme) {
            state.activeTheme = activeTheme;
        }
    }

    updateThemeSelector(props = this.props) {
        const state = toRaw(this.state);
        if (!state.activeTheme && !state.showThemeSelector && !props.readonly) {
            state.showThemeSelector = true;
        } else if ((state.activeTheme && state.showThemeSelector) || props.readonly) {
            state.showThemeSelector = false;
        }
        if (state.showThemeSelector && state.showCodeView) {
            state.showCodeView = false;
        }
    }

    getMassMailingIframeProps() {
        const props = {
            config: this.getConfig(),
            iframeRef: this.iframeRef,
            onBlur: this.onBlur.bind(this),
            onEditorLoad: this.onEditorLoad.bind(this),
            onIframeLoad: this.onIframeLoad.bind(this, this.state.key),
            readonly: this.props.readonly,
            showThemeSelector: this.state.showThemeSelector,
            showCodeView: this.state.showCodeView,
            withBuilder: this.withBuilder,
        };
        if (this.debug) {
            Object.assign(props, {
                toggleCodeView: () => this.toggleCodeView(),
            });
        }
        return props;
    }

    /**
     * Content reinsertion as done in the super method is not properly supported
     * by the editor (corrupted state). This override forces the creation of
     * a new editor instead, and all plugins will be instantiated from scratch.
     * @override
     */
    async toggleCodeView() {
        await this.commitChanges();
        this.state.showCodeView = !this.state.showCodeView;
        this.state.key++;
    }

    /**
     * @override
     */
    getConfig() {
        if (this.props.readonly) {
            return this.getReadonlyConfig();
        } else if (this.withBuilder) {
            return this.getBuilderConfig();
        } else {
            return this.getSimpleEditorConfig();
        }
    }

    /**
     * @override
     */
    getReadonlyConfig() {
        const config = super.getReadonlyConfig();
        config.value =
            config.value && config.value.toString()
                ? config.value
                : this.props.record.data[this.props.inlineField];
        return config;
    }

    getBuilderConfig() {
        const config = super.getConfig();
        delete config.Plugins;
        return {
            ...config,
            allowChecklist: false,
            record: this.props.record,
            mobileBreakpoint: "md",
            defaultImageMimetype: "image/png",
            onEditorReady: () => this.commitChanges(),
        };
    }

    getSimpleEditorConfig() {
        const config = super.getConfig();
        const codeViewCommand = [config.resources?.user_commands]
            .filter(Boolean)
            .flat()
            .find((cmd) => cmd.id === "codeview");
        if (codeViewCommand) {
            codeViewCommand.isAvailable = () => this.debug;
        }
        return {
            ...config,
            onEditorReady: () => this.commitChanges(),
            Plugins: [
                ...MAIN_EDITOR_PLUGINS,
                ...DYNAMIC_PLACEHOLDER_PLUGINS,
                ...registry.category("basic-editor-plugins").getAll(),
                PowerButtonsPlugin,
            ].filter((P) => !["banner", "prompt"].includes(P.id)),
        };
    }

    getThemeSelectorConfig() {
        return {
            setThemeHTML: (html) =>
                this.mutex.exec(() =>
                    this.props.record
                        .update({
                            [this.props.name]: html,
                            [this.props.inlineField]: "",
                        })
                        .catch(() => {}),
                ),
            filterTemplates: this.props.filterTemplates,
            mailingModelId: this.props.record.data.mailing_model_id.id,
            mailingModelName:
                this.props.record.data.mailing_model_id.display_name || "",
        };
    }

    onTextareaInput(ev) {
        this.onChange();
        ev.target.style.height = ev.target.scrollHeight + "px";
    }

    /**
     * Ensure that the inlineField has its first value set (in case a template
     * was just applied or if the field value was set manually without using
     * this widget.
     * @override
     */
    async _commitChanges({ urgent }) {
        if (
            this.editor &&
            !this.editor.isDestroyed &&
            this.props.record.data[this.props.name].toString() !== "" &&
            this.props.record.data[this.props.inlineField].toString() === ""
        ) {
            if (
                (await this.ensureIframeLoaded()) &&
                this.editor &&
                !this.editor.isDestroyed
            ) {
                this.isDirty = true;
                this.lastValue = undefined;
            } else {
                return;
            }
        }
        if (!this.state.showCodeView && this.editor?.isDestroyed) {
            return;
        }
        return super._commitChanges({ urgent });
    }

    /**
     * Complete rewrite of `updateValue` to ensure that both the field and the
     * inlineField are saved at the same time. Depends on the iframe to compute
     * the style of the inlineField.
     * @override
     */
    async updateValue(value) {
        const iframeInfo = await this.ensureIframeLoaded();
        if (!iframeInfo) {
            return;
        }
        const { bundleControls, iframe } = iframeInfo;
        this.lastValue = normalizeHTML(value, this.clearElementToCompare.bind(this));
        this.isDirty = false;
        const shouldRestoreDisplayNone = iframe.classList.contains("d-none");
        iframe.classList.remove("d-none");
        iframe.style.setProperty("min-width", "1320px", "important");
        iframe.style.setProperty("max-width", "1320px", "important");
        const processingEl = iframe.contentDocument.createElement("DIV");
        processingEl.append(parseHTML(iframe.contentDocument, value));
        const processingContainer = iframe.contentDocument.querySelector(
            ".o_mass_mailing_processing_container",
        );
        bundleControls["mass_mailing.assets_inside_builder_iframe"]?.toggle(false);
        processingContainer.append(processingEl);
        this.preprocessFilterDomains(processingEl);
        const cssRules = getCSSRules(iframe.contentDocument);
        await toInline(processingEl, cssRules);
        const inlineValue = processingEl.innerHTML;
        processingEl.remove();
        bundleControls["mass_mailing.assets_inside_builder_iframe"]?.toggle(true);
        iframe.style.minWidth = "";
        iframe.style.maxWidth = "";
        if (shouldRestoreDisplayNone) {
            iframe.classList.add("d-none");
        }
        await this.props.record
            .update({
                [this.props.name]: value,
                [this.props.inlineField]: inlineValue,
            })
            .catch(() => (this.isDirty = true));
        this.setFieldDirty(this.isDirty);
    }
    /**
     * Processes the data-filter-domain to be converted to a t-if that will be interpreted on send
     * by QWeb.
     * TODO EGGMAIL: move in a convert_inline plugin when they are implemented.
     * @param {HTMLElement} htmlEl
     */
    preprocessFilterDomains(htmlEl) {
        htmlEl.querySelectorAll("[data-filter-domain]").forEach((el) => {
            let domain;
            try {
                domain = new Domain(JSON.parse(el.dataset.filterDomain));
            } catch {
                el.setAttribute("t-if", "false");
                return;
            }
            el.setAttribute("t-if", `object.filtered_domain(${domain.toString()})`);
        });
    }
}

export const massMailingHtmlField = {
    ...htmlField,
    component: MassMailingHtmlField,
    extractProps({ attrs, options }) {
        const props = htmlField.extractProps(...arguments);
        props.editorConfig.allowChecklist = false;
        props.editorConfig.allowVideo = false;
        props.editorConfig.baseContainers = ["P"];
        Object.assign(props, {
            filterTemplates: options.filterTemplates,
            inlineField: options["inline_field"],
            migrateHTML: false,
            embeddedComponents: false,
            isCollaborative: false,
            sandboxedPreview: false,
            codeview: true,
        });
        return props;
    },
    fieldDependencies: [{ name: "body_html", type: "html", readonly: "false" }],
};

registry.category("fields").add("mass_mailing_html", massMailingHtmlField);
