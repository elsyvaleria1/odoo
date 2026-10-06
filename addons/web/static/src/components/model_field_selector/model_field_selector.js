// @ts-check
/** @odoo-module native */

import {
    Component,
    onWillDestroy,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { KeepLast, SupersededError } from "@web/core/utils/concurrency";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover/popover_hook";

import { ModelFieldSelectorPopover } from "./model_field_selector_popover.js";

const log = makeLogger("web.components.model_field_selector");

export class ModelFieldSelector extends Component {
    static template = "web._ModelFieldSelector";
    static components = {
        Popover: ModelFieldSelectorPopover,
    };
    static props = {
        resModel: t.string(),
        path: t.any().optional(),
        allowEmpty: t.boolean().optional(false),
        readonly: t.boolean().optional(true),
        readProperty: t.boolean().optional(),
        showSearchInput: t.boolean().optional(true),
        isDebugMode: t.boolean().optional(false),
        update: t.function().optional(() => () => {}),
        filter: t.function().optional(),
        sort: t.function().optional(),
        followRelations: t.boolean().optional(true),
        showDebugInput: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {import("services").ServiceFactories["field"]} */
    fieldService;
    /** @type {KeepLast} */
    keepLast;
    /** @type {ReturnType<typeof usePopover>} */
    popover;
    /** @type {{ isInvalid: boolean; displayNames: string[] }} */
    state;

    /** @type {string | null} */
    newPath = null;

    setup() {
        this.fieldService = useService("field");
        this.pendingSelection = new KeepLast({ rejectSuperseded: true });
        this.popover = usePopover(
            /** @type {any} */ (this.constructor).components.Popover,
            {
                class: "o_popover_field_selector",
                onClose: () => this.commitPath(),
            },
        );
        this.keepLast = new KeepLast({ rejectSuperseded: true });
        this.state = proxy({ isInvalid: false, displayNames: [] });
        onWillDestroy(() => {
            this.keepLast.cancel();
            this.pendingSelection.cancel();
        });
        onWillStart(() => this.updateState(this.props));
        onWillUpdateProps((nextProps) => {
            const modelPathKeys = ["resModel", "path", "allowEmpty"];
            if (modelPathKeys.some((key) => this.props[key] !== nextProps[key])) {
                this.pendingSelection.cancel();
                this.updateState(nextProps);
            }
        });
    }

    openPopover(currentTarget) {
        if (this.props.readonly) {
            return;
        }
        this.pendingSelection.cancel();
        this.newPath = null;
        this.popover.open(currentTarget, {
            resModel: this.props.resModel,
            path: this.props.path,
            readProperty: this.props.readProperty,
            update: (path, _fieldInfo, debug = false) => {
                this.newPath = path;
                if (!debug) {
                    this.updateState({ ...this.props, path });
                }
            },
            showSearchInput: this.props.showSearchInput,
            isDebugMode: this.props.isDebugMode,
            filter: this.props.filter,
            sort: this.props.sort,
            followRelations: this.props.followRelations,
            showDebugInput: this.props.showDebugInput,
        });
    }

    async commitPath() {
        const path = this.newPath;
        if (path === null) {
            return;
        }
        this.newPath = null;
        const { resModel, update } = this.props;
        log.logic("commit path", () => ({ resModel, path }));
        let fieldInfo;
        try {
            fieldInfo = await this.pendingSelection.add(
                this.fieldService.loadFieldInfo(resModel, path),
            );
        } catch (error) {
            if (error instanceof SupersededError) {
                log.logic("path commit discarded");
                return;
            }
            throw error;
        }
        update(path, fieldInfo);
    }

    async updateState(params) {
        const { resModel, path, allowEmpty } = params;
        let state;
        try {
            state = await this.keepLast.add(
                this.fieldService.loadPathDescription(resModel, path, allowEmpty),
            );
        } catch (error) {
            if (error instanceof SupersededError) {
                return;
            }
            throw error;
        }
        Object.assign(this.state, state);
    }

    clear() {
        this.pendingSelection.cancel();
        if (this.popover.isOpen) {
            this.newPath = "";
            this.popover.close();
            return;
        }
        this.props.update("", {
            resModel: this.props.resModel,
            fieldDef: null,
        });
    }
}
