/** @odoo-module native */
import { formatLocalized } from "@web/core/l10n/date_format";
import { dateSettings, DATETIME_MED, deserializeDateTime } from "@web/core/l10n/dates";

export function formatToLocaleString(ISOdatetime, code) {
    return formatLocalized(deserializeDateTime(ISOdatetime), DATETIME_MED, {
        locale: code,
        numberingSystem: dateSettings.numberingSystem,
    });
}

export function addToRegistryWithCleanup(cleanUpHook, registry, name, item) {
    registry.replace(name, item);
    cleanUpHook(() => {
        registry.remove(name);
    });
}

export function sortModelFieldSelectorFields(fields) {
    return Object.keys(fields).sort((a, b) => {
        if (fields[a].relation && fields[b].relation) {
            return fields[a].string.localeCompare(fields[b].string);
        }
        if (fields[a].relation) {
            return 1;
        }
        if (fields[b].relation) {
            return -1;
        }
        return fields[a].string.localeCompare(fields[b].string);
    });
}
