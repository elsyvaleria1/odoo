/** @odoo-module native */
import { READONLY_MAIN_EMBEDDINGS } from "@html_editor/others/embedded_components/embedding_sets";
import { ArticleTemplatePickerNoContentHelper } from "@knowledge/components/article_template_picker_dialog/article_template_picker_no_content_helper";
import { KnowledgeHtmlViewer } from "@knowledge/components/knowledge_html_viewer/knowledge_html_viewer";
import { WithViewModel } from "@knowledge/components/with_view_model/with_view_model";
import { KNOWLEDGE_READONLY_EMBEDDINGS } from "@knowledge/editor/embedded_components/embedding_sets";
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { groupBy } from "@web/core/utils/collections/arrays";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Record } from "@web/model/record";
import { ConfirmationDialog, Dialog } from "@web/ui/dialog";

/**
 * This component will display an article template picker. The user will be able
 * to preview the article templates and select the one they want.
 */
export class ArticleTemplatePickerDialog extends Component {
    static template = "knowledge.ArticleTemplatePickerDialog";
    static components = {
        Dialog,
        Record,
        KnowledgeHtmlViewer,
        NoContentHelper: ArticleTemplatePickerNoContentHelper,
        WithViewModel,
    };
    static props = {
        articles: t.array(t.object()),
        templates: t.array(t.object()),
        templateRenderingContext: t.object().optional(),
        onLoadArticle: t.function(),
        onLoadTemplate: t.function(),
        onDeleteArticle: t.function(),
        onDeleteTemplate: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
    /**
     * @override
     */
    setup() {
        super.setup();
        this.size = "fs";
        this.user = user;
        this.orm = useService("orm");
        this.dialogService = useService("dialog");
        this.scrollView = elementRef();

        const articlesListedInTemplateGallery = this.props.articles;
        const templates = this.props.templates;

        const templatesGroupedByCategory = Object.values(
            groupBy(templates, (template) => template["template_category_id"][0]),
        )
            .sort(
                (a, b) =>
                    a[0]["template_category_sequence"] -
                    b[0]["template_category_sequence"],
            )
            .map((group) =>
                group.sort((a, b) => a["template_sequence"] - b["template_sequence"]),
            );

        this.state = proxy({
            articlesListedInTemplateGallery,
            templatesGroupedByCategory,
        });
        this.selectFirstEntryFromSidebar();

        onMounted(() => {
            const { el } = this.scrollView;
            if (el) {
                el.scrollTop = 0;
            }
        });

        useLayoutEffect(
            () => {
                const { el } = this.scrollView;
                if (el) {
                    el.style.visibility = "visible";
                }
            },
            () => [this.state.resId],
        );
    }

    /**
     * @param {integer} resId
     * @param {function} onLoadRecord
     */
    loadRecord(resId, onLoadRecord) {
        const { el } = this.scrollView;
        if (el) {
            el.scrollTop = 0;
        }
        if (resId !== this.state.resId) {
            if (el) {
                el.style.visibility = "hidden";
            }
            this.state.resId = resId;
            onLoadRecord?.();
        }
    }

    /**
     * Selects the first entry from the templates gallery sidebar.
     */
    selectFirstEntryFromSidebar() {
        if (this.state.articlesListedInTemplateGallery.length > 0) {
            const articleId = this.state.articlesListedInTemplateGallery[0].id;
            this.onSelectArticle(articleId);
        } else if (this.state.templatesGroupedByCategory.length > 0) {
            const templateId = this.state.templatesGroupedByCategory[0][0].id;
            this.onSelectTemplate(templateId);
        }
    }

    /** @returns {boolean} */
    canDeleteTemplates() {
        return user.isAdmin;
    }

    /**
     * @param {integer} articleId
     */
    async onDeleteArticle(articleId) {
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Remove Template from List"),
            body: _t(
                "Are you sure you want to remove this template from the list?\nIf needed, it can be added later from the Article.",
            ),
            confirmLabel: _t("Remove Template"),
            confirm: async () => {
                await this.props.onDeleteArticle(articleId);
                this.state.articlesListedInTemplateGallery =
                    this.state.articlesListedInTemplateGallery.filter(
                        (article) => article.id !== articleId,
                    );
                if (this.state.resId === articleId) {
                    this.selectFirstEntryFromSidebar();
                }
            },
            cancel: () => {},
        });
    }

    /**
     * @param {integer} templateId
     */
    async onDeleteTemplate(templateId) {
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Delete Template"),
            body: _t(
                "Are you sure you want to delete this template from the database?",
            ),
            confirmLabel: _t("Remove Template"),
            confirm: async () => {
                await this.props.onDeleteTemplate(templateId);
                const groups = [];
                for (const group of this.state.templatesGroupedByCategory) {
                    const templates = group.filter(
                        (template) => template.id !== templateId,
                    );
                    if (templates.length > 0) {
                        groups.push(templates);
                    }
                }
                this.state.templatesGroupedByCategory = groups;
                if (this.state.resId === templateId) {
                    this.selectFirstEntryFromSidebar();
                }
            },
            cancel: () => {},
        });
    }

    /**
     * @param {integer} articleId
     */
    onSelectArticle(articleId) {
        this.loadRecord(articleId, () => {
            this.state.isRenderingTemplate = false;
        });
    }

    /**
     * @param {integer} templateId
     */
    onSelectTemplate(templateId) {
        this.loadRecord(templateId, () => {
            this.state.isRenderingTemplate = true;
        });
    }

    async onLoadArticle() {
        await this.props.onLoadArticle(this.state.resId);
        this.props.close();
    }

    async onLoadTemplate() {
        await this.props.onLoadTemplate(this.state.resId);
        this.props.close();
    }

    /**
     * @param {Record} record
     * @returns {Object}
     */
    getHtmlViewerConfig(record) {
        return {
            config: {
                value: record.data.template_preview || record.data.body,
                embeddedComponents: [
                    ...READONLY_MAIN_EMBEDDINGS,
                    ...KNOWLEDGE_READONLY_EMBEDDINGS,
                ],
            },
        };
    }

    /**
     * Returns the fields required for the preview of the templates.
     * @returns {Array[String]}
     */
    get templateFieldNames() {
        return [
            "cover_image_url",
            "icon",
            "id",
            "parent_id",
            "template_name",
            "template_preview",
            "template_description",
        ];
    }

    /**
     * Returns the fields required for the preview of the articles that are
     * listed in the templates gallery.
     * @returns {Array[String]}
     */
    get articleFieldNames() {
        return ["body", "cover_image_url", "icon", "id", "name", "parent_id"];
    }
}
