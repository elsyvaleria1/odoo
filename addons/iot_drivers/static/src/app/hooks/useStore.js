/** @odoo-module native */
import { Plugin, useConfig, usePlugin } from "/web/static/lib/owl/owl.es.js";

export class StorePlugin extends Plugin {
    static id = "iot_drivers.store";
    store = useConfig("store");
}

export default function useStore() {
    return usePlugin(StorePlugin).store;
}
