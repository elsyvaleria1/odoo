/** @odoo-module native */
import { Img } from "@html_builder/core/img";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

export class CustomInnerSnippet extends Component {
    static template = "html_builder.CustomInnerSnippet";
    static props = {
        snippetModel: t.object(),
        snippet: t.object(),
        onClickHandler: t.function(),
        disabledTooltip: t.string(),
    };
    static components = { Img };
    props = useProps(this.constructor.props);

    setup() {
        this.renameInputRef = elementRef();
        useAutofocus({ ref: this.renameInputRef });

        this.state = proxy({ isRenaming: false });

        this.renameButtonTooltip = _t("Rename %(snippetTitle)s", {
            snippetTitle: this.snippet.title,
        });
        this.deleteButtonTooltip = _t("Delete %(snippetTitle)s", {
            snippetTitle: this.snippet.title,
        });
    }

    get snippet() {
        return this.props.snippet;
    }

    toggleRenamingState() {
        this.state.isRenaming = !this.state.isRenaming;
    }

    onConfirmRename() {
        this.props.snippetModel.renameCustomSnippet(
            this.snippet,
            this.renameInputRef.el.value,
        );
        this.toggleRenamingState();
    }
}
