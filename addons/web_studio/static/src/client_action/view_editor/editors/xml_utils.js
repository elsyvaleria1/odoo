/** @odoo-module native */
import { evaluateExpr } from "@web/core/py_js/py";
import { appendAttr, isComponentNode } from "@web/views/view_compiler";

const nodeWeak = new WeakMap();

export function countPreviousSiblings(node) {
    const countXpath = `count(preceding-sibling::${node.tagName}[not(@data-used-by)])`;
    return node.ownerDocument.evaluate(countXpath, node, null, XPathResult.NUMBER_TYPE)
        .numberValue;
}

/**
 * @param {import("@web/views/ir/view_ir_schema").ViewIRNode} node
 * @param {Map<any, any>} parents
 * @param {string[]} upperKinds
 * @returns {string}
 */
export function computeIRXpath(node, parents, upperKinds) {
    const parent = parents.get(node) || null;
    const siblings = parent ? parent.children || [] : [node];
    const count =
        siblings
            .slice(0, siblings.indexOf(node))
            .filter(
                (sibling) =>
                    sibling.kind === node.kind && !sibling.attrs?.["data-used-by"],
            ).length + 1;
    const step = `${node.kind}[${count}]`;
    if (parent && !upperKinds.includes(node.kind)) {
        return `${computeIRXpath(parent, parents, upperKinds)}/${step}`;
    }
    return `/${step}`;
}

export function computeXpath(node, upperBoundSelector = "form") {
    if (nodeWeak.has(node)) {
        return nodeWeak.get(node);
    }
    const tagName = node.tagName;
    const count = countPreviousSiblings(node) + 1;

    let xpath = `${tagName}[${count}]`;
    const parent = node.parentElement;
    if (!node.matches(upperBoundSelector)) {
        const parentXpath = computeXpath(parent, upperBoundSelector);
        xpath = `${parentXpath}/${xpath}`;
    } else {
        xpath = `/${xpath}`;
    }
    nodeWeak.set(node, xpath);
    return xpath;
}

export function getNodeAttributes(node) {
    const attrs = {};
    for (const att of node.getAttributeNames()) {
        if (att === "options") {
            attrs[att] = evaluateExpr(node.getAttribute(att));
            continue;
        }
        attrs[att] = node.getAttribute(att);
    }
    return attrs;
}

function getXpathNodes(xpathResult) {
    const nodes = [];
    let res;
    while ((res = xpathResult.iterateNext())) {
        nodes.push(res);
    }
    return nodes;
}

export function getNodesFromXpath(xpath, xml) {
    const owner = "evaluate" in xml ? xml : xml.ownerDocument;
    const xpathResult = owner.evaluate(
        xpath,
        xml,
        null,
        XPathResult.ORDERED_NODE_ITERATOR_TYPE,
    );
    return getXpathNodes(xpathResult);
}

const parser = new DOMParser();
export const parseStringToXml = (str) => parser.parseFromString(str, "text/xml");

const serializer = new XMLSerializer();
export const serializeXmlToString = (xml) => serializer.serializeToString(xml);

export function applyInvisible(invisible, compiled, params) {
    if (!invisible || invisible === "False" || invisible === "0") {
        return compiled;
    }

    let isVisileExpr;
    if (invisible !== "True" && invisible !== "1") {
        const recordExpr = params.recordExpr || "__comp__.props.record";
        isVisileExpr = `!__comp__.evaluateBooleanExpr(${JSON.stringify(
            invisible,
        )},${recordExpr}.evalContextWithVirtualIds)`;
        if (isComponentNode(compiled)) {
            compiled.setAttribute("studioIsVisible", isVisileExpr);
        } else {
            appendAttr(
                compiled,
                "class",
                `o_web_studio_show_invisible:!${isVisileExpr}`,
            );
        }
    } else {
        if (isComponentNode(compiled)) {
            compiled.setAttribute("studioIsVisible", "false");
        } else {
            appendAttr(compiled, "class", `o_web_studio_show_invisible:true`);
        }
    }

    const studioShowExpr = `__comp__.viewEditorModel.showInvisible`;
    isVisileExpr = isVisileExpr
        ? `(${isVisileExpr} or ${studioShowExpr})`
        : studioShowExpr;
    if (compiled.hasAttribute("t-if")) {
        const formerTif = compiled.getAttribute("t-if");
        isVisileExpr = `( ${formerTif} ) and ${isVisileExpr}`;
    }
    compiled.setAttribute("t-if", isVisileExpr);
    return compiled;
}
