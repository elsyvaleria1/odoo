/** @odoo-module native */
/**
 * @param {String} dataBehaviorPropsAttribute
 * @returns {Object}
 */
export function decodeDataBehaviorProps(dataBehaviorPropsAttribute) {
    if (!dataBehaviorPropsAttribute) {
        return undefined;
    }
    return JSON.parse(decodeURIComponent(dataBehaviorPropsAttribute));
}

/**
 * @param {string} propName
 * @param {Element} anchor
 * @returns {Element}
 */
export function getPropNameNode(propName, anchor) {
    const propNodes = anchor.querySelectorAll(`[data-prop-name="${propName}"]`);
    for (let i = propNodes.length - 1; i >= 0; i--) {
        const closest = propNodes[i].closest(".o_knowledge_behavior_anchor");
        if (closest === anchor) {
            return propNodes[i];
        }
    }
}
