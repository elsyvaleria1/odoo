declare module "@odoo/owl" {
    export type Env = Record<PropertyKey, any>;

    export interface ComponentConstructor<P = any, E extends Env = Env> {
        new (props: P, env: E, node?: any): Component<P, E>;
        template?: string;
        components?: any;
        props?: Record<string, any> | string[];
        defaultProps?: Record<string, any>;
    }

    export interface TemplateSetConfig {
        dev?: boolean;
        templates?: string | Document | Record<string, string | Element>;
        getTemplate?: (name: string) => Element | string | Function | null | undefined;
        translatableAttributes?: string[];
        translateFn?: (term: string, ...rest: any[]) => any;
        customDirectives?: Record<
            string,
            (node: Element, value: string, modifiers: string[]) => void
        >;
        globalValues?: Record<string, any>;
    }

    export interface AppConfig<E extends Env = Env> extends TemplateSetConfig {
        name?: string;
        test?: boolean;
        env?: E;
        plugins?: any[];
        config?: Record<string, any>;
        warnIfNoStaticProps?: boolean;
    }

    export class TemplateSet {
        static compiler: { compile: Function; parseXML: Function } | null;
        constructor(config?: TemplateSetConfig);
        dev: boolean;
        addTemplate(name: string, template: string | Element): void;
        addTemplates(templates: string | Document): void;
        getTemplate(name: string): Function;
        [key: string]: any;
    }

    export interface RootConfig {
        props?: any;
        env?: Env;
        pluginManager?: any;
        onError?: (error: any) => void;
        host?: any;
    }

    export interface Root<C extends Component = Component> {
        node: ComponentNode<C>;
        mount(target: HTMLElement | ShadowRoot, options?: any): Promise<C>;
        destroy(): void;
        [key: string]: any;
    }

    export class App extends TemplateSet {
        static apps: Set<App>;
        static version: string;
        constructor(config?: AppConfig);
        name: string;
        scheduler: any;
        roots: Set<Root<any>>;
        pluginManager: any;
        destroyed: boolean;
        createRoot<C extends Component>(
            Root: new (...args: any[]) => C,
            config?: RootConfig,
        ): Root<C>;
        destroy(): void;
    }

    export interface ComponentNode<C extends Component = any> {
        component: C;
        children: Record<string, ComponentNode>;
        app: App;
    }

    export class Component<P = any, E extends Env = Env> {
        static env?: Env;
        static template?: string;
        static components?: any;
        static props?: any;
        static defaultProps?: any;
        declare ["constructor"]: Function & {
            env?: Env;
            template?: string;
            components?: any;
            props?: any;
            defaultProps?: any;
        };
        constructor(props: P, env: E, node?: any);
        props: P;
        env: E;
        setup(): void;
        render(deep?: boolean): void;
        [key: string]: any;
    }

    export function onError(callback: (error: any) => void): void;
    export function onMounted(callback: () => void | Promise<void>): void;
    export function onPatched(callback: () => void): void;
    export function onWillDestroy(callback: () => void | Promise<void>): void;
    export function onWillPatch(callback: () => void): void;
    export function onWillStart(callback: () => void | Promise<void>): void;
    export function onWillUnmount(callback: () => void | Promise<void>): void;
    export function onWillUpdateProps(
        callback: (nextProps: any) => void | Promise<void>,
    ): void;

    export function markRaw<T>(target: T): T;
    export function toRaw<T>(target: T): T;
    export function batched<F extends (...args: any[]) => any>(fn: F): F;

    export function proxy<T extends object>(target: T): T;
    export function observe<T extends object>(target: T, callback: () => void): T;
    export function untrack<T>(fn: () => T): T;

    export interface Signal<T> {
        (): T;
        set(value: T): void;
    }
    export interface SignalOptions<T> {
        equals?: boolean | ((a: T, b: T) => boolean);
    }
    export const signal: {
        <T>(value: T, options?: SignalOptions<T>): Signal<T>;
        Array<T>(value?: T[], options?: SignalOptions<T[]>): Signal<T[]>;
        Object<T extends object>(value?: T, options?: SignalOptions<T>): Signal<T>;
        Map<K, V>(
            value?: Map<K, V>,
            options?: SignalOptions<Map<K, V>>,
        ): Signal<Map<K, V>>;
        Set<T>(value?: Set<T>, options?: SignalOptions<Set<T>>): Signal<Set<T>>;
        ref<T = HTMLElement>(type?: new (...args: any[]) => T): Signal<T | null>;
    };
    export interface ComputedOptions<T> extends SignalOptions<T> {
        /** makes the computed writable: `computed.set(value)` calls it */
        set?: (value: T) => void;
        /** not collected by the current scope: it outlives the component or effect that made it */
        detached?: boolean;
    }
    export function computed<T>(getter: () => T, options?: ComputedOptions<T>): () => T;
    export function asyncComputed<T>(getter: () => Promise<T>): () => T | undefined;
    export function effect(fn: () => void | (() => void)): () => void;
    export function immediateEffect(fn: () => void | (() => void)): () => void;
    export function shallowEqual(a: unknown, b: unknown): boolean;

    export function useEffect(fn: () => void | (() => void)): void;
    export function useOnChange<A extends any[]>(
        dependencies: () => A,
        callback: (...args: A) => void | (() => void),
        options?: { initialRun?: boolean },
    ): void;
    export function useListener(
        target: EventTarget | (() => EventTarget | null | undefined),
        eventName: string,
        handler: (event: any) => unknown,
        eventParams?: boolean | AddEventListenerOptions,
    ): void;

    export interface OwlType<T = any> {
        (context: any): void;
        optional(defaultValue?: T | (() => T)): OwlType<T | undefined>;
    }
    export interface Types {
        and(types: OwlType[]): OwlType;
        any(): OwlType<any>;
        array<T = any>(elementType?: OwlType<T>): OwlType<T[]>;
        boolean(): OwlType<boolean>;
        component(): OwlType<ComponentConstructor>;
        constructor(): OwlType<new (...args: any[]) => any>;
        customValidator<T = any>(
            type: OwlType<T>,
            validate: (value: T) => boolean,
            message?: string,
        ): OwlType<T>;
        function(): OwlType<(...args: any[]) => any>;
        instanceOf<T>(constructor: { prototype: T }): OwlType<T>;
        literal<T extends string | number | boolean | null | undefined>(
            value: T,
        ): OwlType<T>;
        number(): OwlType<number>;
        object(
            shape?: Record<string, OwlType> | string[],
        ): OwlType<Record<string, any>>;
        or(types: OwlType[]): OwlType;
        promise(): OwlType<Promise<any>>;
        record<T = any>(valueType?: OwlType<T>): OwlType<Record<string, T>>;
        ref(): OwlType;
        selection<T extends string>(values: T[]): OwlType<T>;
        signal(): OwlType<Signal<any>>;
        strictObject(shape?: Record<string, OwlType>): OwlType<Record<string, any>>;
        string(): OwlType<string>;
        tuple(types: OwlType[]): OwlType<any[]>;
    }
    export const t: Types;
    export const types: Types;
    export function assertType(
        value: unknown,
        type: OwlType,
        errorMessage?: string,
    ): void;
    export function applyDefaults<T>(value: T, type: OwlType): T;
    export function getDefault(type: OwlType): (() => any) | undefined;
    export function validateType(value: unknown, type: OwlType): any[];

    export const useProps: {
        <P = any>(type?: Record<string, OwlType> | string[] | null): P;
        static(type?: Record<string, OwlType> | string[] | null): any;
    };
    export const props: typeof useProps;

    export class Scope {
        app: App;
        pluginManager: any;
        status: number;
        [key: string]: any;
    }
    export function getScope(): Scope;
    export function useScope(): Scope;
    export function useConfig<T = any>(key: string, type?: OwlType<T>): T;
    export const config: any;

    export class Plugin {
        static id?: string;
        static dependencies?: (typeof Plugin)[];
        setup(): void;
        [key: string]: any;
    }
    export type PluginConstructor = { new (...args: any[]): Plugin } & typeof Plugin;
    export function plugin<P extends Plugin>(pluginType: new (...args: any[]) => P): P;
    export function usePlugin<P extends Plugin>(
        pluginType: new (...args: any[]) => P,
    ): P;
    export function providePlugins(
        pluginConstructors: (typeof Plugin)[],
        config?: any,
    ): void;

    export class Registry<T = any> {
        constructor(options?: { name?: string; validation?: OwlType });
        [key: string]: any;
    }
    export class Resource<T = any> {
        [key: string]: any;
    }
    export class Portal extends Component {}
    export class Suspense extends Component {}
    export class ErrorBoundary extends Component {}
    export const globalTemplates: any;
    export function useApp(): App;

    export interface Ref<T extends Element = HTMLElement> {
        el: T | null;
    }

    export class EventBus<
        EventDetailMap extends Record<string, any> = Record<string, any>,
    > extends EventTarget {
        constructor();
        addEventListener<K extends keyof EventDetailMap & string>(
            name: K,
            listener: (event: CustomEvent<EventDetailMap[K]>) => unknown,
            options?: boolean | AddEventListenerOptions,
        ): void;
        addEventListener(
            name: string,
            listener: EventListenerOrEventListenerObject,
            options?: boolean | AddEventListenerOptions,
        ): void;
        removeEventListener<K extends keyof EventDetailMap & string>(
            name: K,
            listener: (event: CustomEvent<EventDetailMap[K]>) => unknown,
            options?: boolean | EventListenerOptions,
        ): void;
        removeEventListener(
            name: string,
            listener: EventListenerOrEventListenerObject,
            options?: boolean | EventListenerOptions,
        ): void;
        trigger<K extends keyof EventDetailMap & string>(
            name: K,
            detail?: EventDetailMap[K],
        ): void;
    }

    export function xml(strings: TemplateStringsArray, ...values: any[]): string;

    export interface Markup extends String {
        toString(): string;
        readonly __markup: true;
    }
    export function markup(strings: TemplateStringsArray, ...values: any[]): Markup;
    export function markup(value: string): Markup;

    export function htmlEscape(value: unknown): Markup;

    export function mount<C extends Component>(
        component: ComponentConstructor,
        target: HTMLElement,
        config?: AppConfig,
    ): Promise<C>;

    export function status(
        component: Component,
    ): "new" | "mounted" | "cancelled" | "destroyed";

    export function whenReady(): Promise<void>;
    export function whenReady(callback: () => void): void;

    export class OwlError extends Error {
        constructor(message: string, options?: ErrorOptions);
    }

    export const blockDom: any;
    export const __info__: {
        readonly date: string;
        readonly hash: string;
        readonly url: string;
        readonly version: string;
    };
}

// owl's template compiler alone: importing it installs it into the runtime
// build that @odoo/owl names
declare module "@odoo/owl/compiler" {
    export function compile(
        template: string | Element,
        options?: Record<string, any>,
    ): Function;
    export function parseXML(xml: string): XMLDocument;
}
