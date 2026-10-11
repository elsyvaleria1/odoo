/** @odoo-module native */
import {
    applyObjectPropertyDifference,
    getEmbeddedProps,
    StateChangeManager,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import { ItemCalendarPropsDialog } from "@knowledge/components/item_calendar_props_dialog/item_calendar_props_dialog";
import { PromptEmbeddedViewNameDialog } from "@knowledge/components/prompt_embedded_view_name_dialog/prompt_embedded_view_name_dialog";
import {
    ReadonlyEmbeddedViewComponent,
    readonlyViewEmbedding,
} from "@knowledge/editor/embedded_components/backend/view/readonly_embedded_view";
import { provideKnowledgeContext } from "@knowledge/js/knowledge_context";
import { uuid } from "@web/core/utils/format/strings";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { useViewModel } from "@web/model/model";

export class EmbeddedViewComponent extends ReadonlyEmbeddedViewComponent {
    setup() {
        this.model = useViewModel();
        this.embeddedState = useEmbeddedState(this.props.host);
        if (!this.id) {
            this.initNewView();
        }
        super.setup();
        this.bus = useEventBus();
        provideKnowledgeContext({
            isEmbeddedReadonly: false,
        });
        this.dialogService = useService("dialog");
        useBus(this.bus, `KNOWLEDGE_EMBEDDED_${this.id}:EDIT`, () => {
            if (
                this.additionalViewProps &&
                Object.keys(this.additionalViewProps).length
            ) {
                this.editView();
            } else {
                this.renameView();
            }
        });
    }

    set additionalViewProps(value) {
        this.embeddedState.additionalViewProps = value;
    }

    get additionalViewProps() {
        return this.embeddedState.additionalViewProps;
    }

    set displayName(value) {
        this.embeddedState.displayName = value;
    }

    get displayName() {
        return this.embeddedState.displayName;
    }

    get favoriteFilters() {
        return this.embeddedState.favoriteFilters;
    }

    set id(value) {
        this.embeddedState.id = value;
    }

    get id() {
        return this.embeddedState.id;
    }

    deleteFavoriteFilter(searchItem) {
        delete this.favoriteFilters[searchItem.description];
    }

    editView() {
        if (
            this.action.res_model === "knowledge.article" &&
            this.action.view_mode === "calendar"
        ) {
            this.dialogService.add(ItemCalendarPropsDialog, {
                isNew: false,
                name: this.displayName,
                saveItemCalendarProps: (name, itemCalendarProps) => {
                    this.displayName = name;
                    this.additionalViewProps.itemCalendarProps = itemCalendarProps;
                },
                knowledgeArticleId: this.model.root.resId,
                ...this.additionalViewProps.itemCalendarProps,
            });
        } else {
            throw new Error("Cannot edit the view: the dialog is not implemented");
        }
    }

    initNewView() {
        if (!this.model.root.data.full_width) {
            this.model.root.update({ full_width: true });
        }
        this.id = uuid();
        const keyOptionalFields = this.props.viewProps.context.keyOptionalFields;
        if (keyOptionalFields) {
            const optionalFields = localStorage.getItem(keyOptionalFields);
            if (optionalFields) {
                localStorage.setItem(`${keyOptionalFields},${this.id}`, optionalFields);
            }
        }
    }

    renameView() {
        this.dialogService.add(PromptEmbeddedViewNameDialog, {
            isNew: false,
            defaultName: this.displayName,
            viewType: this.props.viewProps.viewType,
            save: (name) => {
                this.displayName = name;
            },
        });
    }

    saveFavoriteFilter(filter) {
        this.favoriteFilters[filter.name] = filter;
    }
}

export const viewEmbedding = {
    ...readonlyViewEmbedding,
    Component: EmbeddedViewComponent,
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                getEmbeddedState: (host) => {
                    const props = getEmbeddedProps(host);
                    return {
                        additionalViewProps: props.viewProps.additionalViewProps || {},
                        displayName: props.viewProps.displayName,
                        favoriteFilters: props.viewProps.favoriteFilters || {},
                        id: props.viewProps.id,
                    };
                },
                propertyUpdater: {
                    favoriteFilters: (state, previous, next) => {
                        applyObjectPropertyDifference(
                            state,
                            "favoriteFilters",
                            previous.favoriteFilters,
                            next.favoriteFilters,
                        );
                    },
                },
                stateToEmbeddedProps: (host, state) => {
                    const props = getEmbeddedProps(host);
                    props.viewProps.additionalViewProps = state.additionalViewProps;
                    props.viewProps.displayName = state.displayName;
                    props.viewProps.favoriteFilters = state.favoriteFilters;
                    props.viewProps.id = state.id;
                    return props;
                },
            }),
        ),
};
