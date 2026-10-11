"use strict";

const shared = require("./shared");

const defaultGroups = [
  ["^\\u0000"],
  ["^node:"],
  ["^@?\\w"],
  ["^"],
  ["^\\."],
];

module.exports = {
  meta: {
    type: "layout",
    fixable: "code",
    schema: [
      {
        type: "object",
        properties: {
          groups: {
            type: "array",
            items: {
              type: "array",
              items: {
                type: "string",
              },
            },
          },
        },
        additionalProperties: false,
      },
    ],
    docs: {
      url: "https://github.com/lydell/eslint-plugin-simple-import-sort#sort-order",
      description: "Automatically sort imports.",
    },
    messages: {
      sort: "Run autofix to sort these imports!",
    },
  },
  create: (context) => {
    const { groups: rawGroups = defaultGroups } = context.options[0] || {};

    const outerGroups = rawGroups.map((groups) =>
      groups.map((item) => RegExp(item, "u")),
    );

    const parents = new Set();

    return {
      ImportDeclaration: (node) => {
        parents.add(node.parent);
      },

      "Program:exit": () => {
        for (const parent of parents) {
          for (const chunk of shared.extractChunks(parent, (node) =>
            isImport(node) ? "PartOfChunk" : "NotPartOfChunk",
          )) {
            maybeReportChunkSorting(chunk, context, outerGroups);
          }
        }
        parents.clear();
      },
    };
  },
};

function maybeReportChunkSorting(chunk, context, outerGroups) {
  const sourceCode = shared.getSourceCode(context);
  const items = shared.getImportExportItems(
    chunk,
    sourceCode,
    isSideEffectImport,
    getSpecifiers,
  );
  const sortedItems = makeSortedItems(items, outerGroups);
  const sorted = shared.printSortedItems(sortedItems, items, sourceCode);
  const { start } = items[0];
  const { end } = items[items.length - 1];
  shared.maybeReportSorting(context, sorted, start, end);
}

function makeSortedItems(items, outerGroups) {
  const itemGroups = outerGroups.map((groups) =>
    groups.map((regex) => ({ regex, items: [] })),
  );
  const rest = [];

  for (const item of items) {
    const { originalSource } = item.source;
    const source = item.isSideEffectImport
      ? `\0${originalSource}`
      : item.source.kind !== "value"
        ? `${originalSource}\0`
        : originalSource;
    const [matchedGroup] = shared
      .flatMap(itemGroups, (groups) =>
        groups.map((group) => [group, group.regex.exec(source)]),
      )
      .reduce(
        ([group, longestMatch], [nextGroup, nextMatch]) =>
          nextMatch != null &&
          (longestMatch == null || nextMatch[0].length > longestMatch[0].length)
            ? [nextGroup, nextMatch]
            : [group, longestMatch],
        [undefined, undefined],
      );
    if (matchedGroup == null) {
      rest.push(item);
    } else {
      matchedGroup.items.push(item);
    }
  }

  return itemGroups
    .concat([[{ regex: /^/, items: rest }]])
    .map((groups) => groups.filter((group) => group.items.length > 0))
    .filter((groups) => groups.length > 0)
    .map((groups) =>
      groups.map((group) => shared.sortImportExportItems(group.items)),
    );
}

function getSpecifiers(importNode) {
  return importNode.specifiers.filter((node) => isImportSpecifier(node));
}

function isImport(node) {
  return node.type === "ImportDeclaration";
}

function isImportSpecifier(node) {
  return node.type === "ImportSpecifier";
}

function isSideEffectImport(importNode, sourceCode) {
  return (
    importNode.specifiers.length === 0 &&
    (!importNode.importKind || importNode.importKind === "value") &&
    !shared.isPunctuator(sourceCode.getFirstToken(importNode, { skip: 1 }), "{")
  );
}
