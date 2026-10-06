/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    toRaw,
    useProps,
} from "@odoo/owl";
import { CodeEditor } from "@web/components/code_editor";
import { ResizablePanel } from "@web/components/resizable_panel";
import { SelectMenu } from "@web/components/select_menu";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { formatXML } from "@web/core/utils/dom/xml";

class ViewSelector extends SelectMenu {
    static template = "web_studio.ViewSelector";
    static choiceItemTemplate = "web_studio.ViewSelector.ChoiceItemRecursive";
    static props = {
        ...SelectMenu.props,
        choices: t
            .array(
                t.object({
                    value: t.any(),
                    label: t.string(),
                    resource: t.any().optional(),
                }),
            )
            .optional(),
    };

    getMainViews() {
        return this.filteredView.displayed.filter((opt) => opt.resource.isMainResource);
    }

    getInherited(choice) {
        const inheritedChoices = this.filteredView.displayed.filter(
            (opt) => (opt.resource.inherit_id || [])[0] === choice.resource.id,
        );
        if (inheritedChoices.length) {
            inheritedChoices.forEach(
                (opt) => (opt.resource.relatedChoice = choice.resource.id),
            );
        }
        return inheritedChoices;
    }

    getComposedBy(choice) {
        const resource = choice.resource;
        if (!resource.called_xml_ids) {
            return [];
        }
        const composedChoices = this.filteredView.displayed.filter(
            (opt) =>
                resource.called_xml_ids.includes(opt.resource.xml_id) ||
                resource.called_xml_ids.includes(opt.resource.key),
        );
        if (composedChoices.length) {
            composedChoices.forEach(
                (opt) => (opt.resource.relatedChoice = resource.id),
            );
        }
        return composedChoices;
    }

    // Parents of displayed options must also be visible when doing a search
    // Based on the filtered choices, they must be added from the list of choices
    filterOptions(searchString) {
        super.filterOptions(searchString);
        const childChoices = this.filtered.choices.filter(
            (c) => c.resource.relatedChoice,
        );
        childChoices.forEach((c) => this.addRelatedChoice(c.resource.relatedChoice));
        this.displayedCount = this.initialDisplayedCount();
    }

    addRelatedChoice(parentId) {
        if (this.filtered.choices.findIndex((c) => c.resource.id === parentId) === -1) {
            const parent = this.props.choices.find((c) => c.resource.id === parentId);
            if (!parent.resource.isMainResource) {
                this.addRelatedChoice(parent.resource.relatedChoice);
            }
            this.filtered.choices.push(parent);
        }
    }
}

export class XmlResourceEditor extends Component {
    static template = "web_studio.XmlResourceEditor";
    static components = { ResizablePanel, CodeEditor, SelectMenu: ViewSelector };
    static props = {
        onClose: t.function(),
        onCodeChange: t.function().optional(),
        onSave: t.function().optional(),
        mainResourceId: t.any(),
        defaultResourceId: t.any().optional(),
        getDefaultResource: t.function().optional(() => () => {}),
        canSave: t.boolean().optional(true),
        minWidth: t.number().optional(400),
        reloadSources: t.number().optional(1),
        displayAlerts: t.boolean().optional(true),
        onResourceChange: t.function().optional(() => () => {}),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            resourcesOptions: [],
            currentResourceId: null,
            _codeChanges: null,
        });
        this.codeEditorKey = this.props.reloadSources;
        onWillStart(() => this.loadResources(this.props.mainResourceId));

        onWillUpdateProps(async (nextProps) => {
            const resourceChanged =
                nextProps.mainResourceId !== this.props.mainResourceId;
            const shouldReload =
                resourceChanged || this.codeEditorKey !== nextProps.reloadSources;
            const nextResourceId =
                nextProps.mainResourceId !== this.props.mainResourceId
                    ? nextProps.mainResourceId
                    : this.state.currentResourceId;

            if (resourceChanged) {
                this.cursorPosition = undefined;
            }

            if (shouldReload) {
                this.state._codeChanges = null;
                await this.loadResources(nextProps.mainResourceId);
                this.state.currentResourceId = nextResourceId;
            }
            this.codeEditorKey = nextProps.reloadSources;
        });

        this.alerts = proxy({
            "built-in-file": {
                message: _t(
                    "Editing a built-in file through this editor is not advised, as it will prevent it from being updated during future App upgrades.",
                ),
                display: true,
            },
        });
    }

    get minWidth() {
        return this.props.minWidth;
    }

    get arch() {
        const currentResourceId = this.state.currentResourceId;
        if (!currentResourceId) {
            return "";
        }
        return this.tempCode || this.getResourceFromId(currentResourceId).arch;
    }

    get tempCode() {
        if (!this.state.currentResourceId) {
            return "";
        }
        return (
            this.state._codeChanges &&
            this.state._codeChanges[this.state.currentResourceId]
        );
    }

    set tempCode(value) {
        if (!this.state.currentResourceId) {
            return;
        }
        this.state._codeChanges = this.state._codeChanges || {};
        this.state._codeChanges[this.state.currentResourceId] = value;
    }

    getResourceFromId(resourceId) {
        const opt =
            this.state.resourcesOptions.find((opt) => opt.value === resourceId) || {};
        return opt.resource;
    }

    onFormat() {
        this.tempCode = formatXML(this.tempCode || this.arch, 4);
    }

    hideAlert(alertKey) {
        this.alerts[alertKey].display = false;
    }

    onCloseClick() {
        this.props.onClose();
    }

    onCodeChange(code, cursorPosition) {
        this.cursorPosition = cursorPosition;
        this.tempCode = code;
        if (this.props.onCodeChange) {
            this.props.onCodeChange({ ...toRaw(this.state._codeChanges) });
        }
    }

    onSaveClick() {
        if (!this.tempCode) {
            return;
        }
        const resource = this.getResourceFromId(this.state.currentResourceId);
        this.props.onSave({
            resourceId: resource.id,
            newCode: this.tempCode,
            oldCode: resource.oldArch,
        });
    }

    onResourceChange(resourceId) {
        this.state.currentResourceId = resourceId;
        this.cursorPosition = undefined;
        this.props.onResourceChange(
            this.getResourceFromId(this.state.currentResourceId),
        );
    }

    async loadResources(resourceId) {
        const resources = await rpc("/web_studio/get_xml_editor_resources", {
            key: resourceId,
        });

        const resourcesOptions = resources.views.map((res) => ({
            label: `${res.name} (${res.xml_id})`,
            value: res.id,
            resource: {
                ...res,
                oldArch: res.arch,
                isMainResource:
                    res.key === resourceId ||
                    res.id === resourceId ||
                    res.xml_id === resourceId,
            },
        }));

        this.state.resourcesOptions = resourcesOptions;
        if (resourcesOptions.length >= 1) {
            let defaultResource = this.props.getDefaultResource(
                resourcesOptions,
                resources.main_view_key,
            );
            if (
                !defaultResource &&
                (this.props.defaultResourceId || resources.main_view_key)
            ) {
                const defaultId =
                    this.props.defaultResourceId || resources.main_view_key;
                defaultResource = resourcesOptions.find(
                    (opt) =>
                        opt.resource.id === defaultId ||
                        opt.resource.xml_id === defaultId ||
                        opt.resource.key === defaultId,
                );
            }
            defaultResource = defaultResource || resourcesOptions[0];
            this.state.currentResourceId = defaultResource.value;
        }

        return resourcesOptions;
    }
}
