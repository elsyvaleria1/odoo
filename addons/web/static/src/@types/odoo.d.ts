class OdooModuleLoader {
    bus: EventTarget;

    modules: Map<string, OdooModule>;

    settledBundles: Set<string>;

    externals: Map<string, Record<string, any>>;

    resolve?: (specifier: string) => string;

    constructor();

    provideExternals(
        namespaces: Record<string, any>,
        resolve: (specifier: string) => string,
    ): void;

    external(specifier: string): Record<string, any>;

    _providedNamespace(name: string, mod: any): any;

    registerNativeModules(
        modulesByName: Record<string, OdooModule>,
        bundle?: string,
    ): void;

    pendingBundles(): string[];

    whenBundlesEvaluated(callback: () => void): void;

    settleFailedBundle(target: EventTarget | null): void;

    handleAssetLoadError(target: EventTarget | null): boolean;

    _reloadPage(): void;

    _beacon: {
        reportJsError(info: {
            message: unknown;
            kind?: string;
            phase?: string;
            filename?: string;
            line?: number;
            col?: number;
            stack?: string;
            cause?: unknown;
            reloaded?: boolean;
            dedup?: boolean;
        }): boolean;
        seenErrors: Set<string>;
        serializeCause(cause: unknown): string;
        hashCode(str: string): string;
        limits: {
            ENDPOINT: string;
            MAX_MESSAGE: number;
            MAX_STACK: number;
            MAX_CAUSE: number;
            MAX_CAUSE_DEPTH: number;
            MAX_SEEN_KEYS: number;
            KINDS: Set<string>;
        };
    };
}

type OdooModule = Record<string, any>;

interface OdooModuleRebindDetail {
    specifiers: string[];
}

declare const odoo: {
    __WOWL_DEBUG__?: { root: import("@odoo/owl").Component };
    csrf_token: string;
    debug: string;
    loader: OdooModuleLoader;
    translationContext?: string;
    isReady?: boolean;
    discuss_data?: Record<string, any>;
    info?: {
        db: string;
        server_version: string;
        server_version_info: [number, number, number, string, number, string];
        isEnterprise: boolean;
        [key: string]: any;
    };
};
