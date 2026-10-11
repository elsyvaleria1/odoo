/** @odoo-module native */
import { SignatureInputPlugin } from "@accountant_knowledge/editor/plugins/signature_input_plugin/signature_input_plugin";
import { UploadLinkPlugin } from "@accountant_knowledge/editor/plugins/upload_link_plugin/upload_link_plugin";
import { KnowledgeHtmlField } from "@knowledge/components/knowledge_html_field/knowledge_html_field";
import { patch } from "@web/core/utils/patch";

patch(KnowledgeHtmlField.prototype, {
    /** @override */
    getConfig() {
        const config = super.getConfig();
        config.Plugins.push(SignatureInputPlugin, UploadLinkPlugin);
        return config;
    },
});
