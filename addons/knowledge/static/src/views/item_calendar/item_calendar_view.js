/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { ItemCalendarModel } from "@knowledge/views/item_calendar/item_calendar_model";
import { onMounted, onWillUpdateProps, t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { ConfirmationDialog } from "@web/ui/dialog";
import {
    CalendarCommonPopover,
    CalendarCommonRenderer,
    CalendarController,
    CalendarRenderer,
    calendarView,
} from "@web/views/calendar";

export class KnowledgeArticleItemsCalendarController extends CalendarController {
    static template = "knowledge.ArticleItemsCalendarController";

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.ui = useService("ui");
        if (
            !("isEmbeddedReadonly" in this.knowledgeContext) ||
            this.knowledgeContext.isEmbeddedReadonly
        ) {
            this.model.meta.canCreate = false;
        }
        if (this.props.itemCalendarProps) {
            this.updateModel(this.props.itemCalendarProps);
            this.state.isWeekendVisible =
                this.props.itemCalendarProps.showWeekEnds ??
                this.state.isWeekendVisible;
        } else {
            this.state.missingConfiguration = true;
            this.model.meta.invalid = true;
        }

        onMounted(async () => {
            if (
                !this.model.meta.invalid &&
                Object.keys(this.model.data.records).length === 0
            ) {
                const propertiesDefinition = await this.orm.read(
                    this.props.resModel,
                    [this.props.context.active_id],
                    ["article_properties_definition"],
                );
                this.state.missingConfiguration =
                    !propertiesDefinition[0].article_properties_definition.some(
                        (property) =>
                            property.name ===
                            this.props.itemCalendarProps.dateStartPropertyId,
                    );
            }
        });
        onWillUpdateProps((nextProps) => {
            if (
                JSON.stringify(this.props.itemCalendarProps) !==
                JSON.stringify(nextProps.itemCalendarProps)
            ) {
                this.updateModel(nextProps.itemCalendarProps);
                this.state.isWeekendVisible =
                    nextProps.itemCalendarProps.showWeekEnds ??
                    this.state.isWeekendVisible;
                this.state.missingConfiguration = false;
            }
        });
    }

    get showSideBar() {
        return !this.knowledgeContext.isEmbeddedView && super.showSideBar;
    }

    /**
     * Create a new article item and open it. If no record is given, creates it
     * without any start/stop date properties.
     * @param {Object} record: calendar record used to create the item with
     * properties.
     */
    async createRecord(record) {
        if (this.model.canCreate) {
            const createValues = {
                is_article_item: true,
                parent_id: this.props.context.active_id || false,
            };
            if (record) {
                const rawRecord = this.model.buildRawRecord(record);
                Object.assign(createValues, rawRecord);
            }
            const articleIds = await this.orm.call(
                "knowledge.article",
                "article_create",
                [],
                createValues,
            );
            this.selectRecord(articleIds[0]);
        }
    }

    deleteRecord(record) {
        this.displayDialog(ConfirmationDialog, {
            title: _t("Confirmation"),
            body: _t("Are you sure you want to send this article to the trash?"),
            confirm: async () => {
                await this.orm.call("knowledge.article", "action_send_to_trash", [
                    record.id,
                ]);
                this.model.load();
            },
            confirmLabel: _t("Send to trash"),
            cancel: () => {},
        });
    }

    /**
     * @override
     * Open an item to allow editing it. This override allows to load the article from the
     * KnowledgeController if the view is embedded, allowing to preserve the navigation history
     */
    editRecord(record) {
        this.selectRecord(record.id);
    }

    selectRecord(articleId) {
        if (this.knowledgeContext.isEmbeddedView) {
            this.props.selectRecord(articleId);
        } else {
            this.action.doAction(
                this.orm.call("knowledge.article", "action_home_page", [articleId]),
                {},
            );
        }
    }

    updateModel(modelProps) {
        this.model.meta.fieldMapping.date_start = modelProps.dateStartPropertyId;
        this.model.meta.fieldMapping.date_stop = modelProps.dateStopPropertyId;
        this.model.meta.fieldMapping.color = modelProps.colorPropertyId;
        this.model.meta.propertiesDateType = modelProps.dateType;
        if (modelProps.scale) {
            this.model.meta.scale = modelProps.scale;
        }
    }

    get rendererProps() {
        return {
            ...super.rendererProps,
            slotMaxTime: this.props.itemCalendarProps?.slotMaxTime || "24:00",
            slotMinTime: this.props.itemCalendarProps?.slotMinTime || "00:00",
        };
    }
}

class KnowledgeArticleItemsCommonPopover extends CalendarCommonPopover {
    static subTemplates = {
        ...CalendarCommonPopover.subTemplates,
        body: "knowledge.ArticleItemsCalendarCommonPopover.body",
        footer: "knowledge.ArticleItemsCalendarCommonPopover.footer",
    };

    get isEventDeletable() {
        return super.isEventDeletable && this.props.record.rawRecord.user_can_write;
    }
}

class KnowledgeArticleItemsCommonRenderer extends CalendarCommonRenderer {
    static props = {
        ...CalendarCommonRenderer.props,
        slotMinTime: t.string(),
        slotMaxTime: t.string(),
    };
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: KnowledgeArticleItemsCommonPopover,
    };

    get options() {
        return {
            ...super.options,
            slotMinTime: this.props.slotMinTime,
            slotMaxTime: this.props.slotMaxTime,
        };
    }

    setup() {
        super.setup();
        useLayoutEffect(
            (slotMinTime, slotMaxTime) => {
                this.fc.api.setOption("slotMinTime", slotMinTime);
                this.fc.api.setOption("slotMaxTime", slotMaxTime);
            },
            () => [this.options.slotMinTime, this.options.slotMaxTime],
        );
    }
}

class KnowledgeArticleItemsCalendarRenderer extends CalendarRenderer {
    static props = {
        ...CalendarRenderer.props,
        slotMinTime: t.string(),
        slotMaxTime: t.string(),
    };
    static components = {
        ...CalendarRenderer.components,
        day: KnowledgeArticleItemsCommonRenderer,
        week: KnowledgeArticleItemsCommonRenderer,
        month: KnowledgeArticleItemsCommonRenderer,
    };
}

registry.category("views").add("knowledge_article_view_calendar_embedded", {
    ...calendarView,
    Controller: KnowledgeArticleItemsCalendarController,
    Model: ItemCalendarModel,
    Renderer: KnowledgeArticleItemsCalendarRenderer,
});
