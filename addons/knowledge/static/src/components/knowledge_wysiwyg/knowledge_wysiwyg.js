/** @odoo-module native */
import { useEditorOverlayContext } from "@html_editor/core/editor_overlay_context";
import { isEmptyBlock } from "@html_editor/utils/dom_info";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { WysiwygArticleHelper } from "@knowledge/components/wysiwyg_article_helper/wysiwyg_article_helper";
import { proxy } from "@odoo/owl";
import { useViewModel } from "@web/model/model";

export class KnowledgeWysiwyg extends Wysiwyg {
    static template = "knowledge.KnowledgeWysiwyg";
    static components = {
        ...Wysiwyg.components,
        WysiwygArticleHelper,
    };

    setup() {
        super.setup();
        this.overlayContext = useEditorOverlayContext();
        this.model = useViewModel();
        this.articleHelperState = proxy({
            isVisible: false,
        });
    }

    /** @override */
    getEditorConfig() {
        const config = super.getEditorConfig();
        return {
            ...config,
            onChange: () => {
                this.articleHelperState.isVisible = isEmptyBlock(this.editor.editable);
                config.onChange?.();
            },
            onEditorReady: () => {
                this.articleHelperState.isVisible = isEmptyBlock(this.editor.editable);
            },
        };
    }
}
