// @ts-check
import { registry } from "@web/core/registry";
import { patchInfo } from "@web/core/utils/patch";

/**
 * @param {object} prototype
 * @param {string} key
 * @returns {PropertyDescriptor|undefined} the lowest definition of `key` on `prototype`, i.e.
 * the one whose `super` reaches the parent: the class body's, else the first patch's.
 */
function lowestOwnDefinition(prototype, key) {
    const info = patchInfo(prototype);
    if (!info?.originalProperties.has(key)) {
        return Object.getOwnPropertyDescriptor(prototype, key);
    }
    const original = info.originalProperties.get(key);
    if (original) {
        return original;
    }
    const first = info.extensions.find((extension) => Object.hasOwn(extension, key));
    return first && Object.getOwnPropertyDescriptor(first, key);
}

/**
 * @param {PropertyDescriptor|undefined} descriptor
 * @param {string} key
 */
function reachesSuper(descriptor, key) {
    return [descriptor?.value, descriptor?.get, descriptor?.set]
        .filter((fn) => typeof fn === "function")
        .some((fn) => String(fn).includes(`super.${key}`));
}

/**
 * A patch of a parent model's method is shadowed on subtype records when the subtype defines
 * the same method without calling `super` there: the patch never runs for them.
 * @returns {string[]}
 */
export function getShadowedPatches() {
    const Models = new Set(registry.category("discuss.model").getAll());
    const shadowed = [];
    for (const Subtype of Models) {
        const Parent = Object.getPrototypeOf(Subtype);
        if (!Models.has(Parent) || !Parent._discriminator) {
            continue;
        }
        const parentPatchedKeys = new Set(
            (patchInfo(Parent.prototype)?.extensions ?? []).flatMap((extension) =>
                Object.getOwnPropertyNames(extension),
            ),
        );
        for (const key of parentPatchedKeys) {
            if (
                Object.hasOwn(Subtype.prototype, key) &&
                !reachesSuper(lowestOwnDefinition(Subtype.prototype, key), key)
            ) {
                shadowed.push(`${Parent.name}.prototype :: ${key} <- ${Subtype.name}`);
            }
        }
    }
    return shadowed.sort();
}
