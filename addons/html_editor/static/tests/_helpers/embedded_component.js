import {
    applyObjectPropertyDifference,
    getEmbeddedProps,
    StateChangeManager,
    useEditableDescendants,
    useEmbeddedState,
} from "@html_editor/others/embedded_component_utils";
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { elementRef, elementRefs } from "@web/core/utils/element_ref";

export class Counter extends Component {
    static props = null;
    static template = xml`
        <span t-ref="this.ref" class="counter" t-on-click="this.increment">Counter:<t t-out="this.state.value"/></span>`;
    props = useProps(this.constructor.props);

    state = proxy({ value: 0 });
    ref = elementRef();

    increment() {
        this.state.value++;
    }
}

export const EmbeddedWrapperMixin = (editableDescendantName) =>
    class extends Component {
        static props = null;
        static template = xml`<t><div class="${editableDescendantName}" t-ref="this.descendantRefs.${editableDescendantName}"/></t>`;
        props = useProps(this.constructor.props);

        setup() {
            this.descendantRefs = elementRefs();
            useEditableDescendants(this.props.host, this.descendantRefs);
        }
    };

export class EmbeddedWrapper extends Component {
    static props = null;
    static template = xml`
        <t>
            <div t-if="this.editableDescendants.shallow" class="shallow" t-ref="this.descendantRefs.shallow"/>
            <div t-if="!this.state.switch">
                <div class="deep" t-ref="this.descendantRefs.deep"/>
            </div>
            <div t-else="">
                <div class="switched">
                    <div class="deep" t-ref="this.descendantRefs.deep"/>
                </div>
            </div>
        </t>`;
    props = useProps(this.constructor.props);

    setup() {
        this.descendantRefs = elementRefs();
        this.editableDescendants = useEditableDescendants(
            this.props.host,
            this.descendantRefs,
        );
        this.state = proxy({
            switch: false,
        });
    }
}

export class OffsetCounter extends Component {
    static props = null;
    static template = xml`
        <span class="counter" t-on-click="this.increment">Counter:<t t-out="this.counterValue"/></span>`;
    props = useProps(this.constructor.props);

    setup() {
        this.embeddedState = useEmbeddedState(this.props.host);
        this.state = proxy({
            value: 0,
        });
    }

    get counterValue() {
        return this.state.value + this.embeddedState.baseValue;
    }

    increment() {
        this.state.value++;
    }
}

export const offsetCounter = {
    name: "counter",
    Component: OffsetCounter,
    getProps: (host) => ({ host }),
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                propertyUpdater: {
                    baseValue: (state, previous, next) => {
                        const offset = next.baseValue - previous.baseValue;
                        state.baseValue += offset;
                    },
                },
            }),
        ),
};

export class SavedCounter extends Component {
    static props = null;
    static template = xml`
        <span class="counter" t-on-click="this.increment">Counter:<t t-out="this.counterValue"/></span>`;
    props = useProps(this.constructor.props);

    setup() {
        this.embeddedState = useEmbeddedState(this.props.host);
    }

    get counterValue() {
        return this.embeddedState.value || 0;
    }

    increment() {
        if (!this.embeddedState.value) {
            this.embeddedState.value = 0;
        }
        this.embeddedState.value++;
    }
}

export const savedCounter = {
    name: "counter",
    Component: SavedCounter,
    getProps: (host) => ({ host }),
    getStateChangeManager: (config) => new StateChangeManager(config),
};

export class CollaborativeObject extends Component {
    static props = null;
    static template = xml`
        <div class="obj"><t t-out="this.collaborativeObject"/></div>`;
    props = useProps(this.constructor.props);

    setup() {
        this.embeddedState = useEmbeddedState(this.props.host);
    }

    get collaborativeObject() {
        return Object.entries(this.embeddedState.obj || {})
            .map(([key, value]) => `${key}_${value}`)
            .join(",");
    }
}

export const collaborativeObject = {
    name: "obj",
    Component: CollaborativeObject,
    getProps: (host) => ({ host }),
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                propertyUpdater: {
                    obj: (state, previous, next) => {
                        applyObjectPropertyDifference(
                            state,
                            "obj",
                            previous.obj,
                            next.obj,
                        );
                    },
                },
            }),
        ),
};

export class NamedCounter extends Component {
    static props = null;
    static template = xml`
        <span class="counter" t-on-click="this.increment"><t t-out="this.props.name"/>:<t t-out="this.counterValue"/></span>`;
    props = useProps(this.constructor.props);

    setup() {
        this.embeddedState = useEmbeddedState(this.props.host);
    }

    get counterValue() {
        return this.embeddedState.value + this.embeddedState.baseValue;
    }

    increment() {
        this.embeddedState.value++;
    }
}

export const namedCounter = {
    name: "counter",
    Component: NamedCounter,
    getProps: (host) => ({
        host,
        ...getEmbeddedProps(host),
    }),
    getStateChangeManager: (config) =>
        new StateChangeManager(
            Object.assign(config, {
                propertyUpdater: {
                    baseValue: (state, previous, next) => {
                        const offset = next.baseValue - previous.baseValue;
                        state.baseValue += offset;
                    },
                },
                getEmbeddedState: (host) => {
                    const props = getEmbeddedProps(host);
                    return {
                        value: props.value,
                        baseValue: 3,
                    };
                },
                stateToEmbeddedProps: (host, state) => ({
                    ...getEmbeddedProps(host),
                    value: state.value,
                }),
            }),
        ),
};

export function embedding(
    name,
    Component,
    getProps = undefined,
    { getEditableDescendants, getStateChangeManager } = {},
) {
    return {
        name,
        Component,
        ...(getProps ? { getProps } : {}),
        ...arguments[3],
    };
}
