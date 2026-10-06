/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { BuilderSelect } from "@html_builder/core/building_blocks/builder_select";
import { BuilderSelectItem } from "@html_builder/core/building_blocks/builder_select_item";
import {
    basicContainerBuilderComponentProps,
    useApplyVisibility,
    useVisibilityObserver,
} from "@html_builder/core/utils";
import { Component, onWillStart, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class BuilderFontFamilyPicker extends Component {
    static template = "html_builder.BuilderFontFamilyPicker";
    static props = {
        ...basicContainerBuilderComponentProps,
        valueParamName: t.string(),
    };
    static components = {
        BuilderSelect,
        BuilderSelectItem,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.rootRef = elementRef();
        this.contentRef = elementRef();
        useVisibilityObserver(this.contentRef, useApplyVisibility(this.rootRef));
        this.fonts = [];
        onWillStart(async () => {
            const fontsData =
                await this.builderContext.editor.shared.builderFont.getFontsData();
            this.fonts = fontsData._fonts
                .slice()
                .sort((a, b) => a.string.localeCompare(b.string));
        });
    }
    forwardProps(fontValue) {
        const result = Object.assign({}, this.props, {
            [this.props.valueParamName]: fontValue.fontFamilyValue,
        });
        delete result.selectMethod;
        delete result.valueParamName;
        return result;
    }
    async onAddFontClick() {
        await this.builderContext.editor.shared.websiteFont.addFont(
            this.props.actionParam,
        );
    }
    async onDeleteFontClick(font) {
        const save = await new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                body: _t(
                    "Deleting a font requires a reload of the page. This will save all your changes and reload the page, are you sure you want to proceed?",
                ),
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
        if (!save) {
            return;
        }
        await this.builderContext.editor.shared.websiteFont.deleteFont(font);
    }
}
