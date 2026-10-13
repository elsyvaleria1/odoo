/** @odoo-module native */
import {
    provideBuilderContext,
    useBuilderContext,
} from "@html_builder/core/builder_context";
import { isElement, isTextNode } from "@html_editor/utils/dom_info";
import {
    Component,
    onMounted,
    onWillDestroy,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    toRaw,
    useProps,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { deepEqual } from "@web/core/utils/collections/objects";
import {
    useBus,
    useIsDestroyed,
    useIsMounted,
    useService,
} from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { effect } from "@web/core/utils/reactive";
import { batched, useDebounced } from "@web/core/utils/timing";

import { BuilderAction } from "./builder_action.js";

/**
 * @typedef { import("../../../../html_editor/static/src/editor").EditorContext } EditorContext
 */

function isConnectedElement(el) {
    return el && el.isConnected && !!el.ownerDocument.defaultView;
}

export function useDomState(getState, { checkEditingElement = true } = {}) {
    const isDestroyed = useIsDestroyed();
    const builderContext = useBuilderContext();
    const isValid = (el) => (!el && !checkEditingElement) || isConnectedElement(el);
    const handler = async (ev) => {
        const editingElement = builderContext.getEditingElement();
        if (isValid(editingElement)) {
            try {
                const newStatePromise = getState(editingElement);
                if (ev) {
                    ev.detail.getStatePromises.push(newStatePromise);
                    const newState = await newStatePromise;
                    const shouldApply = await ev.detail.updatePromise;
                    if (shouldApply) {
                        Object.assign(state, newState);
                    }
                } else {
                    Object.assign(state, await newStatePromise);
                }
            } catch (e) {
                if (!isValid(editingElement) || isDestroyed()) {
                    return;
                }
                throw e;
            }
        }
    };
    const state = proxy({});
    onWillStart(() => handler());
    useBus(builderContext.editorBus, "DOM_UPDATED", handler);
    return state;
}

export function useActionInfo() {
    const builderContext = useBuilderContext();
    const props = useProps();

    const getParam = (paramName) => {
        let param = props[paramName];
        param = param === undefined ? builderContext.weContext[paramName] : param;
        if (typeof param === "object") {
            param = JSON.stringify(param);
        }
        return param;
    };

    const actionParam = getParam("actionParam");

    return {
        actionId: props.action || builderContext.weContext.action,
        actionParam,
        actionValue: props.actionValue,
        classAction: getParam("classAction"),
        styleAction: getParam("styleAction"),
        styleActionValue: props.styleActionValue,
        attributeAction: getParam("attributeAction"),
        attributeActionValue: props.attributeActionValue,
    };
}

function querySelectorAll(targets, selector) {
    const elements = new Set();
    for (const target of targets) {
        for (const el of target.querySelectorAll(selector)) {
            elements.add(el);
        }
    }
    return [...elements];
}

export function useBuilderComponent() {
    const props = useProps();
    const childContext = {};
    const parentContext = useBuilderContext();
    let editingElements;
    let applyTo = props.applyTo;
    const updateEditingElements = () => {
        editingElements = applyTo
            ? querySelectorAll(parentContext.getEditingElements(), applyTo)
            : parentContext.getEditingElements();
    };
    updateEditingElements();
    parentContext.editorBus.addEventListener(
        "UPDATE_EDITING_ELEMENT",
        updateEditingElements,
    );
    onWillUpdateProps(async (nextProps) => {
        if (props.applyTo !== nextProps.applyTo) {
            applyTo = nextProps.applyTo;
            parentContext.editorBus.trigger("UPDATE_EDITING_ELEMENT");
            await parentContext.triggerDomUpdated();
        }
    });
    onWillDestroy(() => {
        parentContext.editorBus.removeEventListener(
            "UPDATE_EDITING_ELEMENT",
            updateEditingElements,
        );
    });
    childContext.getEditingElements = () => editingElements;
    childContext.getEditingElement = () => editingElements[0];
    const weContext = {};
    for (const key in basicContainerBuilderComponentProps) {
        if (key in props) {
            weContext[key] = props[key];
        }
    }
    if (Object.keys(weContext).length) {
        childContext.weContext = { ...parentContext.weContext, ...weContext };
    }
    provideBuilderContext(childContext);
}
export function useDependencyDefinition(id, item, { onReady } = {}) {
    const builderContext = useBuilderContext();
    const ignore = builderContext.ignoreBuilderItem;
    const isDestroyed = useIsDestroyed();
    let mounted = false;
    const add = () => {
        if (!isDestroyed()) {
            builderContext.dependencyManager.add(id, item, ignore);
        }
    };
    if (onReady) {
        onReady.then(add);
    } else {
        add();
    }
    onMounted(() => (mounted = true));
    onWillDestroy(() => {
        builderContext.dependencyManager.removeByValue(item, { silent: !mounted });
    });
}

export function useDependencies(dependencies) {
    const builderContext = useBuilderContext();
    const isDependenciesVisible = () => {
        const deps = Array.isArray(dependencies) ? dependencies : [dependencies];
        return deps.filter(Boolean).every((dependencyId) => {
            const match = dependencyId.match(/(!)?(.*)/);
            const inverse = !!match[1];
            const id = match[2];
            const isActiveFn = builderContext.dependencyManager.get(id)?.isActive;
            if (!isActiveFn) {
                return false;
            }
            const isActive = isActiveFn();
            return inverse ? !isActive : isActive;
        });
    };
    return isDependenciesVisible;
}

function useIsActiveItem() {
    const builderContext = useBuilderContext();
    const listenedKeys = new Set();

    function isActive(itemId) {
        const isActiveFn = builderContext.dependencyManager.get(itemId)?.isActive;
        if (!isActiveFn) {
            return false;
        }
        return isActiveFn();
    }

    const getState = () => {
        const newState = {};
        for (const itemId of listenedKeys) {
            newState[itemId] = isActive(itemId);
        }
        return newState;
    };
    const state = useDomState(getState);
    const isMounted = useIsMounted();
    const publish = batched(
        () => Object.assign(state, getState()),
        () => new Promise((resolve) => browser.requestAnimationFrame(resolve)),
    );
    const listener = () => {
        if (isMounted()) {
            publish();
            return;
        }
        const newState = getState();
        for (const [itemId, value] of Object.entries(newState)) {
            if (!(itemId in state) && builderContext.dependencyManager.get(itemId)) {
                state[itemId] = value;
            }
        }
    };
    onMounted(listener);
    builderContext.dependencyManager.addEventListener("dependency-updated", listener);
    onWillDestroy(() => {
        builderContext.dependencyManager.removeEventListener(
            "dependency-updated",
            listener,
        );
    });
    return function isActiveItem(itemId) {
        listenedKeys.add(itemId);
        if (state[itemId] === undefined) {
            return isActive(itemId);
        }
        return state[itemId];
    };
}

export function useGetItemValue() {
    const builderContext = useBuilderContext();
    const listenedKeys = new Set();

    function getValue(itemId) {
        const getValueFn = builderContext.dependencyManager.get(itemId)?.getValue;
        if (!getValueFn) {
            return null;
        }
        return getValueFn();
    }

    const getState = () => {
        const newState = {};
        for (const itemId of listenedKeys) {
            newState[itemId] = getValue(itemId);
        }
        return newState;
    };
    const state = useDomState(getState);
    const isMounted = useIsMounted();
    const listener = () => {
        const mounted = isMounted();
        for (const [itemId, value] of Object.entries(getState())) {
            const fills =
                !(itemId in state) &&
                value !== undefined &&
                builderContext.dependencyManager.get(itemId);
            if (mounted ? !deepEqual(state[itemId], value) : fills) {
                state[itemId] = value;
            }
        }
    };
    onMounted(listener);
    builderContext.dependencyManager.addEventListener("dependency-updated", listener);
    onWillDestroy(() => {
        builderContext.dependencyManager.removeEventListener(
            "dependency-updated",
            listener,
        );
    });
    return function getItemValue(itemId) {
        listenedKeys.add(itemId);
        if (!(itemId in state)) {
            return getValue(itemId);
        }
        return state[itemId];
    };
}

export function useSelectableComponent(id, { onItemChange } = {}) {
    useBuilderComponent();
    const selectableItems = [];
    const refreshCurrentItemDebounced = useDebounced(refreshCurrentItem, 0, {
        immediate: true,
    });
    const builderContext = useBuilderContext();

    const state = proxy({
        currentSelectedItem: null,
    });

    function refreshCurrentItem() {
        if (
            builderContext.editor.isDestroyed ||
            builderContext.editor.shared.history.getIsPreviewing()
        ) {
            return;
        }
        let currentItem;
        let itemPriority = 0;
        for (const selectableItem of selectableItems) {
            if (selectableItem.isApplied() && selectableItem.priority >= itemPriority) {
                currentItem = selectableItem;
                itemPriority = selectableItem.priority;
            }
        }
        if (currentItem && currentItem !== toRaw(state.currentSelectedItem)) {
            state.currentSelectedItem = currentItem;
            builderContext.dependencyManager.triggerDependencyUpdated();
        }
        if (currentItem) {
            onItemChange?.(currentItem);
        }
    }

    if (id) {
        useDependencyDefinition(id, {
            type: "select",
            getSelectableItems: () => selectableItems.slice(0),
        });
    }

    onMounted(refreshCurrentItem);
    useBus(builderContext.editorBus, "DOM_UPDATED", refreshCurrentItem);
    function cleanSelectedItem(...args) {
        if (state.currentSelectedItem) {
            return state.currentSelectedItem.clean(...args);
        }
    }

    provideBuilderContext({
        selectableContext: {
            cleanSelectedItem,
            addSelectableItem: (item) => {
                selectableItems.push(item);
            },
            removeSelectableItem: (item) => {
                const index = selectableItems.indexOf(item);
                if (index !== -1) {
                    selectableItems.splice(index, 1);
                }
            },
            update: refreshCurrentItemDebounced,
            items: selectableItems,
            refreshCurrentItem: () => refreshCurrentItem(),
            getSelectableState: () => state,
        },
    });
}

export function useSelectableItemComponent(id, { getLabel = () => {} } = {}) {
    const { operation, isApplied, getActions, priority, clean, onReady } =
        useClickableBuilderComponent();
    const builderContext = useBuilderContext();

    let isSelectableActive = isApplied;
    let state;
    if (builderContext.selectableContext) {
        const selectableState = builderContext.selectableContext.getSelectableState();
        isSelectableActive = () => {
            builderContext.selectableContext.refreshCurrentItem();
            return (
                toRaw(selectableState.currentSelectedItem) === selectableItem ||
                (id && selectableState.currentSelectedItem?.id === id)
            );
        };

        const selectableItem = {
            isApplied,
            priority,
            getLabel,
            clean,
            getActions,
            id,
        };

        builderContext.selectableContext.addSelectableItem(selectableItem);
        state = proxy({
            isActive: false,
        });
        effect(
            ({ currentSelectedItem }) => {
                state.isActive =
                    toRaw(currentSelectedItem) === selectableItem ||
                    (id && currentSelectedItem?.id === id);
            },
            [selectableState],
        );
        builderContext.selectableContext.refreshCurrentItem();
        onMounted(builderContext.selectableContext.update);
        onWillDestroy(() => {
            builderContext.selectableContext.removeSelectableItem(selectableItem);
        });
    } else {
        state = useDomState(async () => {
            await onReady;
            return {
                isActive: isSelectableActive(),
            };
        });
    }

    if (id) {
        useDependencyDefinition(
            id,
            {
                isActive: isSelectableActive,
                getActions,
                cleanSelectedItem: builderContext.selectableContext?.cleanSelectedItem,
            },
            { onReady },
        );
    }

    return { state, operation };
}

function usePrepareAction(getAllActions) {
    const builderContext = useBuilderContext();
    const getAction = builderContext.editor.shared.builderActions.getAction;
    const asyncActions = [];
    for (const descr of getAllActions()) {
        if (descr.actionId) {
            const action = getAction(descr.actionId);
            if (action.has("prepare")) {
                asyncActions.push({ action, descr });
            }
        }
    }
    let onReady;
    if (asyncActions.length) {
        let resolve;
        ({ promise: onReady, resolve } = Promise.withResolvers());
        onWillStart(async function () {
            await Promise.all(asyncActions.map((obj) => obj.action.prepare(obj.descr)));
            resolve();
        });
        onWillUpdateProps(async ({ actionParam, actionValue }) => {
            ({ promise: onReady, resolve } = Promise.withResolvers());
            await Promise.all(
                asyncActions.map((obj) =>
                    obj.action.prepare({
                        ...obj.descr,
                        actionParam: convertParamToObject(actionParam),
                        actionValue,
                    }),
                ),
            );
            resolve();
        });
    }
    return onReady;
}

function useReloadAction(getAllActions) {
    const builderContext = useBuilderContext();
    const getAction = builderContext.editor.shared.builderActions.getAction;
    let reload = false;
    for (const descr of getAllActions()) {
        if (descr.actionId) {
            const action = getAction(descr.actionId);
            if (action.reload) {
                reload = action.reload;
            }
        }
    }
    return { reload };
}

export function useHasPreview(getAllActions) {
    const builderContext = useBuilderContext();
    const props = useProps();
    const getAction = builderContext.editor.shared.builderActions.getAction;

    let hasPreview = true;
    for (const descr of getAllActions()) {
        if (descr.actionId) {
            const action = getAction(descr.actionId);
            if (action.preview === false) {
                hasPreview = false;
            }
        }
    }

    return (
        hasPreview &&
        (props.preview === true ||
            (props.preview === undefined && builderContext.weContext.preview !== false))
    );
}

function useWithLoadingEffect(getAllActions) {
    const builderContext = useBuilderContext();
    const getAction = builderContext.editor.shared.builderActions.getAction;
    let withLoadingEffect = true;
    for (const descr of getAllActions()) {
        if (descr.actionId) {
            const action = getAction(descr.actionId);
            if (action.withLoadingEffect === false) {
                withLoadingEffect = false;
            }
        }
    }

    return withLoadingEffect;
}

function useCanTimeout(getAllActions) {
    const builderContext = useBuilderContext();
    const getAction = builderContext.editor.shared.builderActions.getAction;
    let canTimeout = true;
    for (const descr of getAllActions()) {
        if (descr.actionId) {
            const action = getAction(descr.actionId);
            if (action.canTimeout === false) {
                canTimeout = false;
            }
        }
    }

    return canTimeout;
}

export function revertPreview(editor) {
    if (editor.isDestroyed) {
        return;
    }
    return editor.shared.operation.next();
}

export function useClickableBuilderComponent() {
    useBuilderComponent();
    const props = useProps();
    const builderContext = useBuilderContext();
    const host = { props, builderContext };
    const { getAllActions, callOperation, isApplied } =
        getAllActionsAndOperations(host);
    const getAction = builderContext.editor.shared.builderActions.getAction;

    const onReady = usePrepareAction(getAllActions);
    const { reload } = useReloadAction(getAllActions);

    const applyOperation =
        builderContext.editor.shared.history.makePreviewableAsyncOperation(callApply);
    const inheritedActionIds =
        props.inheritedActions || builderContext.weContext.inheritedActions || [];

    const hasPreview = useHasPreview(getAllActions);
    const operationWithReload = useOperationWithReload(callApply, reload);

    const withLoadingEffect = useWithLoadingEffect(getAllActions);
    const canTimeout = useCanTimeout(getAllActions);

    let preventNextPreview = false;
    const operation = {
        commit: () => {
            preventNextPreview = false;
            if (reload) {
                callOperation(operationWithReload, {
                    operationParams: {
                        withLoadingEffect: withLoadingEffect,
                        canTimeout: canTimeout,
                    },
                });
            } else {
                callOperation(applyOperation.commit, {
                    operationParams: {
                        withLoadingEffect: withLoadingEffect,
                        canTimeout: canTimeout,
                    },
                });
            }
        },
        preview: () => {
            if (preventNextPreview) {
                return;
            }
            preventNextPreview = true;
            callOperation(applyOperation.preview, {
                preview: true,
                operationParams: {
                    cancellable: true,
                    cancelPrevious: () => applyOperation.revert(),
                    canTimeout: canTimeout,
                },
            });
        },
        revert: () => {
            preventNextPreview = false;
            revertPreview(builderContext.editor);
        },
    };

    if (!hasPreview) {
        operation.preview = () => {};
    }

    function clean(nextApplySpecs, isPreviewing) {
        const proms = [];
        for (const { actionId, actionParam, actionValue } of getAllActions()) {
            for (const editingElement of builderContext.getEditingElements()) {
                let nextAction;
                proms.push(
                    getAction(actionId).clean?.({
                        isPreviewing,
                        editingElement,
                        params: actionParam,
                        value: actionValue,
                        dependencyManager: builderContext.dependencyManager,
                        selectableContext: builderContext.selectableContext,
                        get nextAction() {
                            nextAction =
                                nextAction ||
                                nextApplySpecs.find((a) => a.actionId === actionId) ||
                                {};
                            return {
                                params: nextAction.actionParam,
                                value: nextAction.actionValue,
                            };
                        },
                    }),
                );
            }
        }
        return Promise.all(proms);
    }

    async function callApply(applySpecs, isPreviewing) {
        await builderContext.selectableContext?.cleanSelectedItem(
            applySpecs,
            isPreviewing,
        );
        const cleans = inheritedActionIds
            .map(
                (actionId) =>
                    builderContext.dependencyManager.get(actionId).cleanSelectedItem,
            )
            .filter(Boolean);
        const cleanPromises = [];
        for (const clean of new Set(cleans)) {
            cleanPromises.push(clean(applySpecs, isPreviewing));
        }
        await Promise.all(cleanPromises);
        const cleanOrApplyProms = [];
        const isAlreadyApplied = isApplied();
        for (const applySpec of applySpecs) {
            const hasClean = !!applySpec.clean;
            const shouldClean = _shouldClean(host, hasClean, isAlreadyApplied);
            if (shouldClean) {
                cleanOrApplyProms.push(
                    applySpec.action.clean({
                        isPreviewing,
                        editingElement: applySpec.editingElement,
                        params: applySpec.actionParam,
                        value: applySpec.actionValue,
                        loadResult: applySpec.loadOnClean ? applySpec.loadResult : null,
                        dependencyManager: builderContext.dependencyManager,
                        selectableContext: builderContext.selectableContext,
                    }),
                );
            } else {
                cleanOrApplyProms.push(
                    applySpec.action.apply({
                        isPreviewing,
                        editingElement: applySpec.editingElement,
                        params: applySpec.actionParam,
                        value: applySpec.actionValue,
                        loadResult: applySpec.loadResult,
                        dependencyManager: builderContext.dependencyManager,
                        selectableContext: builderContext.selectableContext,
                    }),
                );
            }
        }
        return await Promise.all(cleanOrApplyProms);
    }
    function getPriority() {
        return (
            getAllActions()
                .map(
                    (a) =>
                        getAction(a.actionId).getPriority?.({
                            params: a.actionParam,
                            value: a.actionValue,
                        }) || 0,
                )
                .find((x) => x !== 0) || 0
        );
    }

    return {
        operation,
        isApplied,
        clean,
        priority: getPriority(),
        getActions: getAllActions,
        onReady,
    };
}
function useOperationWithReload(callApply, reload) {
    const builderContext = useBuilderContext();
    const ui = useService("ui");
    return async (...args) => {
        const { editingElement } = args[0][0];
        ui.block();
        try {
            const applyResults = await callApply(...args);
            if (!applyResults.includes(BuilderAction.cancelReload)) {
                builderContext.editor.shared.history.addStep();
                await builderContext.editor.shared.savePlugin.save();
                const target =
                    builderContext.editor.shared.builderOptions.getReloadSelector(
                        editingElement,
                    );
                const url = reload.getReloadUrl?.();
                await builderContext.editor.config.reloadEditor({ target, url });
            }
        } finally {
            ui.unblock();
        }
    };
}

function getValueWithDefault(userInputValue, defaultValue, formatRawValue) {
    if (defaultValue !== undefined) {
        if (
            !userInputValue ||
            (typeof userInputValue === "string" && !userInputValue.trim())
        ) {
            return formatRawValue(defaultValue);
        }
    }
    return userInputValue;
}

/**
 * @param {Error} error
 * @param {Element} editingElement
 * @param {Component} comp
 * @throws {Error}
 */
function handleBuilderActionError(error, editingElement, comp) {
    const isOutdated =
        comp.builderContext.editor.shared.versionError.checkNotifyOutdatedSnippet(
            editingElement,
        );
    if (!isOutdated) {
        throw error;
    }
}

export function useInputBuilderComponent({
    id,
    defaultValue,
    formatRawValue = (rawValue) => rawValue,
    parseDisplayValue = (displayValue) => displayValue,
} = {}) {
    const props = useProps();
    const builderContext = useBuilderContext();
    const host = { props, builderContext };
    const { getAllActions, callOperation } = getAllActionsAndOperations(host);
    const getAction = builderContext.editor.shared.builderActions.getAction;
    const state = useDomState(getState);

    const onReady = usePrepareAction(getAllActions);
    const { reload } = useReloadAction(getAllActions);

    const withLoadingEffect = useWithLoadingEffect(getAllActions);
    const canTimeout = useCanTimeout(getAllActions);

    onWillUpdateProps((nextProps) => {
        if ("default" in nextProps) {
            defaultValue = nextProps.default;
        }
    });

    async function callApply(applySpecs, isPreviewing) {
        const proms = [];
        for (const applySpec of applySpecs) {
            proms.push(
                applySpec.action.apply({
                    isPreviewing,
                    editingElement: applySpec.editingElement,
                    params: applySpec.actionParam,
                    value: applySpec.actionValue,
                    loadResult: applySpec.loadResult,
                    dependencyManager: builderContext.dependencyManager,
                }),
            );
        }
        return await Promise.all(proms);
    }

    const applyOperation =
        builderContext.editor.shared.history.makePreviewableAsyncOperation(callApply);
    const operationWithReload = useOperationWithReload(callApply, reload);
    function getState(editingElement) {
        if (!isConnectedElement(editingElement)) {
            return {};
        }
        const actionWithGetValue = getAllActions().find(({ actionId }) =>
            getAction(actionId).has("getValue"),
        );
        const { actionId, actionParam } = actionWithGetValue;
        try {
            const actionValue =
                getAction(actionId).getValue({ editingElement, params: actionParam }) ||
                defaultValue;
            return {
                value: actionValue,
            };
        } catch (error) {
            handleBuilderActionError(error, editingElement, host);
        }
    }

    function commit(userInputValue) {
        userInputValue = getValueWithDefault(
            userInputValue,
            defaultValue,
            formatRawValue,
        );
        const rawValue = parseDisplayValue(userInputValue);
        if (reload) {
            callOperation(operationWithReload, {
                userInputValue: rawValue,
                operationParams: {
                    withLoadingEffect: withLoadingEffect,
                    canTimeout: canTimeout,
                },
            });
        } else {
            callOperation(applyOperation.commit, {
                userInputValue: rawValue,
                operationParams: {
                    withLoadingEffect: withLoadingEffect,
                    canTimeout: canTimeout,
                },
            });
        }
        if (
            rawValue === null ||
            (rawValue === defaultValue && rawValue === state.value)
        ) {
            state.value = rawValue;
        }
        return rawValue !== undefined ? formatRawValue(rawValue) : "";
    }

    const shouldPreview = useHasPreview(getAllActions);
    function preview(userInputValue) {
        if (shouldPreview) {
            userInputValue = getValueWithDefault(
                userInputValue,
                defaultValue,
                formatRawValue,
            );
            callOperation(applyOperation.preview, {
                preview: true,
                userInputValue: parseDisplayValue(userInputValue),
                operationParams: {
                    cancellable: true,
                    cancelPrevious: () => applyOperation.revert(),
                    canTimeout: canTimeout,
                },
            });
        }
    }

    if (id) {
        useDependencyDefinition(
            id,
            {
                type: "input",
                getValue: () => state.value,
            },
            { onReady },
        );
    }

    return {
        state,
        commit,
        preview,
        onReady,
    };
}

export function useApplyVisibility(ref) {
    return (hasContent) => {
        ref.el?.classList.toggle("d-none", !hasContent);
    };
}

export function useVisibilityObserver(contentRef, callback) {
    const applyVisibility = () => {
        const hasContent = [...contentRef.el.childNodes].some(
            (el) =>
                (isTextNode(el) && el.textContent !== "") ||
                (isElement(el) && !el.classList.contains("d-none")),
        );
        callback(hasContent);
    };

    const observer = new MutationObserver(applyVisibility);
    useLayoutEffect(
        (contentEl) => {
            if (!contentEl) {
                return;
            }
            applyVisibility();
            observer.observe(contentEl, {
                subtree: true,
                attributes: true,
                childList: true,
                attributeFilter: ["class"],
            });
            return () => {
                observer.disconnect();
            };
        },
        () => [contentRef.el],
    );
}

export function useInputDebouncedCommit(comp, ref) {
    return useDebounced(() => {
        const normalizedDisplayValue = comp.commit(ref.el.value);
        ref.el.value = normalizedDisplayValue;
    }, 550);
}

export const basicContainerBuilderComponentProps = {
    id: t.string().optional(),
    applyTo: t.string().optional(),
    preview: t.boolean().optional(),
    inheritedActions: t.array(t.string()).optional(),
    action: t.string().optional(),
    actionParam: t.customValidator(t.any(), () => true).optional(),
    classAction: t.customValidator(t.any(), () => true).optional(),
    attributeAction: t.customValidator(t.any(), () => true).optional(),
    dataAttributeAction: t.customValidator(t.any(), () => true).optional(),
    styleAction: t.customValidator(t.any(), () => true).optional(),
};
const validateIsNull = t.literal(null);

export const clickableBuilderComponentProps = {
    ...basicContainerBuilderComponentProps,
    inverseAction: t.boolean().optional(),
    actionValue: t
        .or([
            t.boolean(),
            t.string(),
            t.number(),
            t.array(t.or([t.boolean(), t.string(), t.number()])),
        ])
        .optional(),
    classActionValue: t.or([t.string(), t.array(), validateIsNull]).optional(),
    attributeActionValue: t.or([t.string(), t.array(), validateIsNull]).optional(),
    dataAttributeActionValue: t.or([t.string(), t.array(), validateIsNull]).optional(),
    styleActionValue: t.or([t.string(), t.array(), validateIsNull]).optional(),
    inheritedActions: t.array(t.string()).optional(),
};

export function getAllActionsAndOperations(comp) {
    const inheritedActionIds =
        comp.props.inheritedActions ||
        comp.builderContext.weContext.inheritedActions ||
        [];

    function getActionsSpecs(actions, userInputValue) {
        const getAction = comp.builderContext.editor.shared.builderActions.getAction;
        const overridableMethods = ["apply", "clean", "load", "loadOnClean"];
        const specs = [];
        for (let { actionId, actionParam, actionValue } of actions) {
            const action = getAction(actionId);
            actionValue = actionValue === undefined ? userInputValue : actionValue;
            for (const editingElement of comp.builderContext.getEditingElements()) {
                const spec = {
                    editingElement,
                    actionId,
                    actionParam,
                    actionValue,
                    action,
                };
                for (const method of overridableMethods) {
                    if (!action.has || action.has(method)) {
                        spec[method] = action[method];
                    }
                }
                specs.push(spec);
            }
        }
        return specs;
    }
    function getShorthandActions() {
        const actions = [];
        const shorthands = [
            ["classAction", "classActionValue"],
            ["attributeAction", "attributeActionValue"],
            ["dataAttributeAction", "dataAttributeActionValue"],
            ["styleAction", "styleActionValue"],
        ];
        for (const [actionId, actionValue] of shorthands) {
            const actionParam =
                comp.builderContext.weContext[actionId] || comp.props[actionId];
            if (actionParam !== undefined) {
                actions.push({
                    actionId,
                    actionParam: convertParamToObject(actionParam),
                    actionValue: comp.props[actionValue],
                });
            }
        }
        return actions;
    }
    function getCustomAction() {
        const actionId = comp.props.action || comp.builderContext.weContext.action;
        if (actionId) {
            const actionParam =
                comp.props.actionParam ?? comp.builderContext.weContext.actionParam;
            return {
                actionId: actionId,
                actionParam: convertParamToObject(actionParam),
                actionValue: comp.props.actionValue,
            };
        }
    }
    function getAllActions() {
        const actions = getShorthandActions();

        const { actionId, actionParam, actionValue } = getCustomAction() || {};
        if (actionId) {
            actions.push({ actionId, actionParam, actionValue });
        }
        const inheritedActions =
            inheritedActionIds
                .map(
                    (actionId) =>
                        comp.builderContext.dependencyManager
                            .get(actionId)
                            ?.getActions?.() || [],
                )
                .flat() || [];
        return actions.concat(inheritedActions || []);
    }
    function callOperation(fn, params = {}) {
        const isPreviewing = !!params.preview;
        const actionsSpecs = getActionsSpecs(getAllActions(), params.userInputValue);

        comp.builderContext.editor.shared.operation.next(
            async () => {
                try {
                    await fn(actionsSpecs, isPreviewing);
                } catch (error) {
                    handleBuilderActionError(
                        error,
                        comp.builderContext.getEditingElement(),
                        comp,
                    );
                }
            },
            {
                load: async () => {
                    try {
                        return await Promise.all(
                            actionsSpecs.map(async (applySpec) => {
                                if (!applySpec.action.has("load")) {
                                    return;
                                }
                                const hasClean = !!applySpec.action.has("clean");
                                if (
                                    !applySpec.loadOnClean &&
                                    _shouldClean(comp, hasClean, isApplied())
                                ) {
                                    return;
                                }
                                const result = await applySpec.action.load({
                                    editingElement: applySpec.editingElement,
                                    params: applySpec.actionParam,
                                    value: applySpec.actionValue,
                                });
                                applySpec.loadResult = result;
                            }),
                        );
                    } catch (error) {
                        handleBuilderActionError(
                            error,
                            comp.builderContext.getEditingElement(),
                            comp,
                        );
                    }
                },
                ...params.operationParams,
            },
        );
    }
    function isApplied() {
        const getAction = comp.builderContext.editor.shared.builderActions.getAction;
        const editingElements = comp.builderContext.getEditingElements();
        if (!editingElements.length) {
            return;
        }
        const areActionsActiveTabs = getAllActions().map((o) => {
            const { actionId, actionParam, actionValue } = o;
            const editingElement = editingElements[0];
            if (!isConnectedElement(editingElement)) {
                return false;
            }
            try {
                const isApplied = getAction(actionId).isApplied?.({
                    editingElement,
                    params: actionParam,
                    value: actionValue,
                });
                return comp.props.inverseAction ? !isApplied : isApplied;
            } catch (error) {
                handleBuilderActionError(error, editingElement, comp);
            }
        });
        if (areActionsActiveTabs.every((el) => el === undefined)) {
            return false;
        }
        if (areActionsActiveTabs.some((el) => el === false)) {
            return false;
        }
        return true;
    }
    return {
        getAllActions: getAllActions,
        callOperation: callOperation,
        isApplied: isApplied,
    };
}
function _shouldClean(comp, hasClean, isApplied) {
    if (!hasClean) {
        return false;
    }
    const shouldToggle = !comp.builderContext.selectableContext;
    const shouldClean = shouldToggle && isApplied;
    return comp.props.inverseAction ? !shouldClean : shouldClean;
}
export function convertParamToObject(param) {
    if (param === undefined) {
        param = {};
    } else if (
        param instanceof Array ||
        param instanceof Function ||
        !(param instanceof Object)
    ) {
        param = {
            ["mainParam"]: param,
        };
    }
    return param;
}

export class BaseOptionComponent extends Component {
    static components = {};
    static props = {};
    static template = "";
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        /** @type {EditorContext} */
        const context =
            this.builderContext.editor.shared.builderOptions.getBuilderOptionContext(
                this.constructor,
            );
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

        this.isActiveItem = useIsActiveItem();
        const comp = this;
        const editor = comp.builderContext.editor;

        if (!Object.hasOwn(comp.constructor, "components")) {
            comp.constructor.components = { ...comp.constructor.components };
        }
        const Components = editor.shared.builderComponents.getComponents();
        Object.assign(comp.constructor.components, Components);
    }
    /**
     * @param {string[]} itemIds
     * @returns {boolean}
     */
    isActiveItems(itemIds) {
        return itemIds.map((i) => this.isActiveItem(i)).find(Boolean) || false;
    }
}
