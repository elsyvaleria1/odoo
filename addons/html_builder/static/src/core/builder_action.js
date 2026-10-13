/** @odoo-module native */
/**
 * @typedef { import("../../../../html_editor/static/src/editor").EditorContext } EditorContext
 * @typedef { any } LoadResult
 * @typedef { any } ActionValue
 * @typedef {{
 *  mainParam: any,
 *  [param: string]: any,
 * }} ActionParams
 * @typedef { Object } NextBuilderAction
 * @property { ActionValue } actionValue
 * @property { ActionParams } actionParam
 * @typedef { Object } SelectableContext
 * @property { Object[] } items
 */

export class BuilderAction {
    /** @type { string[] } */
    static dependencies = [];
    static cancelReload = Symbol("cancel reload");
    /**
     * @param { EditorContext } context
     */
    constructor(context) {
        /** @type { EditorContext['document'] } */
        this.document = context.document;
        this.window = context.document.defaultView;
        /** @type { EditorContext['editable'] } */
        this.editable = context.editable;
        /** @type { EditorContext['config'] } */
        this.config = context.config;
        /** @type { EditorContext['services'] } */
        this.services = context.services;
        /** @type { EditorContext['dependencies'] } */
        this.dependencies = context.dependencies;
        /** @type { EditorContext['getResource'] } */
        this.getResource = context.getResource;
        /** @type { EditorContext['dispatchTo'] } */
        this.dispatchTo = context.dispatchTo;
        /** @type { EditorContext['delegateTo'] } */
        this.delegateTo = context.delegateTo;
        /** @type { EditorContext['checkPredicates'] } */
        this.checkPredicates = context.checkPredicates;

        this.setup();

        this.preview ??= this.reload ? false : true;
        this.withLoadingEffect ??= true;
        this.loadOnClean ??= false;
        this.canTimeout ??= !this.has("load");
    }

    setup() {}

    /**
     * @param { Object } context
     * @param { ActionParams } context.actionParam
     * @param { ActionValue } context.actionValue
     */
    async prepare(context) {}

    /**
     * @param { Object } context
     * @param { ActionParams } context.params
     * @param { ActionValue } context.value
     * @returns { number }
     */
    getPriority(context) {}

    /**
     * @param { Object } context
     * @param { import("./dependency_manager").DependencyManager } context.dependencyManager
     * @param { boolean } context.isPreviewing
     * @param { HTMLElement } context.editingElement
     * @param { ActionValue } context.value
     * @param { ActionParams } [context.params]
     * @param { LoadResult } [context.loadResult]
     * @param { SelectableContext } [context.selectableContext]
     */
    async apply(context) {}

    /**
     * @param { Object } context
     * @param { HTMLElement } context.editingElement
     * @param { ActionParams } [context.params]
     * @returns { any }
     */
    getValue(context) {}

    /**
     * @param { Object } context
     * @param { HTMLElement } context.editingElement
     * @param { ActionValue } context.value
     * @param { ActionParams } [context.params]
     * @returns {boolean}
     */
    isApplied(context) {}

    /**
     * @param { Object } context
     * @param { import("./dependency_manager").DependencyManager } context.dependencyManager
     * @param { NextBuilderAction } context.nextAction
     * @param { boolean } context.isPreviewing
     * @param { HTMLElement } context.editingElement
     * @param { ActionValue } context.value
     * @param { ActionParams } [context.params]
     * @param { LoadResult } [context.loadResult]
     * @param { SelectableContext } [context.selectableContext]
     */
    async clean(context) {}

    /**
     * @param { Object } context
     * @param { HTMLElement } context.editingElement
     * @returns { Promise<LoadResult> }
     */
    async load(context) {}

    /**
     * @param { "prepare"|"getPriority"|"load"|"apply"|"clean"|"isApplied"|"getValue" } method
     * @returns { boolean }
     */
    has(method) {
        const baseMethod = BuilderAction.prototype[method];
        const actualMethod = this.constructor.prototype[method];
        return baseMethod !== actualMethod;
    }
}
