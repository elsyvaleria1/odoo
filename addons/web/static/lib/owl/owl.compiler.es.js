// ../owl-core/src/owl_error.ts
var OwlError = class extends Error {
};

// ../owl-core/src/event_modifiers.ts
var EventModifier = {
  PREVENT_ANY: 1,
  STOP_ANY: 2,
  SELF: 4,
  PREVENT: 8,
  STOP: 16
};
var LISTENER_MODIFIERS = ["capture", "passive", "synthetic"];
function eventModifierMask(key) {
  const parts = key.split(".");
  const selfIndex = parts.indexOf("self", 1);
  let mask = 0;
  for (let i = 1; i < parts.length; i++) {
    const m = parts[i];
    const beforeSelf = i < selfIndex;
    if (m === "self") {
      mask |= EventModifier.SELF;
    } else if (m === "prevent") {
      mask |= beforeSelf ? EventModifier.PREVENT_ANY : EventModifier.PREVENT;
    } else if (m === "stop") {
      mask |= beforeSelf ? EventModifier.STOP_ANY : EventModifier.STOP;
    } else if (!LISTENER_MODIFIERS.includes(m)) {
      throw new OwlError(`Unknown event modifier: '${m}'`);
    }
  }
  return mask;
}

// ../owl-compiler/src/inline_expressions.ts
var RESERVED_WORDS = new Set(
  "true,false,NaN,null,undefined,debugger,console,window,in,instanceof,new,function,return,eval,void,__globals__,Math,RegExp,Array,Object,Date,Number,Boolean,String,Symbol,BigInt,Map,Set,JSON,Intl,Error,Infinity,isFinite,isNaN,parseFloat,parseInt,decodeURI,decodeURIComponent,encodeURI,encodeURIComponent".split(",")
);
var STATEMENT_KEYWORDS = new Set(
  "break,case,catch,class,const,continue,default,do,else,enum,export,extends,finally,for,if,import,super,switch,throw,try,var,while,with,yield".split(",")
);
var WORD_REPLACEMENT = Object.assign(/* @__PURE__ */ Object.create(null), {
  and: "&&",
  or: "||",
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<="
});
var STATIC_TOKEN_MAP = Object.assign(/* @__PURE__ */ Object.create(null), {
  "{": "LEFT_BRACE",
  "}": "RIGHT_BRACE",
  "[": "LEFT_BRACKET",
  "]": "RIGHT_BRACKET",
  ":": "COLON",
  ",": "COMMA",
  "(": "LEFT_PAREN",
  ")": "RIGHT_PAREN"
});
var OPERATORS = "...,.,===,==,++,+,!==,!=,!,||,&&,>=,>,<=,<,??=,??,?.,?,--,-,*,/,%,typeof ,delete ,=>,=,;,in ,new ,|,&,^,~".split(
  ","
);
var tokenizeString = function(expr) {
  let s = expr[0];
  let start = s;
  if (s !== "'" && s !== '"' && s !== "`") {
    return false;
  }
  if (start === "`") {
    const end = findTemplateEnd(expr, 0);
    const value = expr.slice(0, end + 1);
    return {
      type: "TEMPLATE_STRING",
      value,
      replace(replacer) {
        return replaceInterpolations(value, replacer);
      }
    };
  }
  let i = 1;
  let cur;
  while (expr[i] && expr[i] !== start) {
    cur = expr[i];
    s += cur;
    if (cur === "\\") {
      i++;
      cur = expr[i];
      if (!cur) {
        throw new OwlError("Invalid expression");
      }
      s += cur;
    }
    i++;
  }
  if (expr[i] !== start) {
    throw new OwlError("Invalid expression");
  }
  s += start;
  return { type: "VALUE", value: s };
};
function findTemplateEnd(str, start) {
  for (let i = start + 1; i < str.length; i++) {
    if (str[i] === "\\") {
      i++;
    } else if (str[i] === "`") {
      return i;
    } else if (str.startsWith("${", i)) {
      i = findClosingBrace(str, i + 2);
    }
  }
  throw new OwlError("Invalid expression");
}
function replaceInterpolations(template, replacer) {
  let result = "";
  let i = 0;
  while (i < template.length) {
    if (template[i] === "\\") {
      result += template.slice(i, i + 2);
      i += 2;
    } else if (template.startsWith("${", i)) {
      const end = findClosingBrace(template, i + 2);
      result += "${" + replacer(template.slice(i + 2, end)) + "}";
      i = end + 1;
    } else {
      result += template[i++];
    }
  }
  return result;
}
var REGEXP_PREFIX_RE = /[(,=:[!&|?{};+\-*%<>~^]/;
var REGEXP_PREFIX_WORDS = /* @__PURE__ */ new Set([
  "return",
  "void",
  "typeof",
  "delete",
  "in",
  "new",
  ...Object.keys(WORD_REPLACEMENT)
]);
function startsRegExp(str, previous) {
  if (previous < 0) {
    return true;
  }
  const char = str[previous];
  if ((char === "+" || char === "-") && str[previous - 1] === char) {
    return false;
  }
  if (REGEXP_PREFIX_RE.test(char)) {
    return true;
  }
  let start = previous + 1;
  while (start > 0 && IDENTIFIER_CHAR_RE.test(str[start - 1])) {
    start--;
  }
  if (!REGEXP_PREFIX_WORDS.has(str.slice(start, previous + 1))) {
    return false;
  }
  let before = start - 1;
  while (before >= 0 && /\s/.test(str[before])) {
    before--;
  }
  return str[before] !== ".";
}
function findClosingBrace(str, start) {
  let depth = 0;
  let previous = -1;
  for (let i = start; i < str.length; i++) {
    const char = str[i];
    if (char === "'" || char === '"') {
      for (i++; i < str.length && str[i] !== char; i++) {
        if (str[i] === "\\") {
          i++;
        }
      }
    } else if (char === "`") {
      i = findTemplateEnd(str, i);
    } else if (str.startsWith("/*", i) || str.startsWith("//", i)) {
      i = commentEnd(str, i) - 1;
      continue;
    } else if (char === "/" && startsRegExp(str, previous)) {
      i = regExpEnd(str, i);
    } else if (char === "{") {
      depth++;
    } else if (char === "}") {
      if (!depth) {
        return i;
      }
      depth--;
    }
    if (!/\s/.test(char)) {
      previous = i;
    }
  }
  throw new OwlError("Invalid expression");
}
function regExpEnd(str, start) {
  let inClass = false;
  let i = start + 1;
  for (; str[i] !== "/" || inClass; i++) {
    const char = str[i];
    if (!char || char === "\n") {
      throw new OwlError("Invalid expression");
    }
    if (char === "\\") {
      i++;
    } else if (char === "[") {
      inClass = true;
    } else if (char === "]") {
      inClass = false;
    }
  }
  return i;
}
function commentEnd(str, start) {
  if (str[start + 1] === "*") {
    const end2 = str.indexOf("*/", start + 2);
    if (end2 < 0) {
      throw new OwlError("Invalid expression");
    }
    return end2 + 2;
  }
  const end = str.indexOf("\n", start);
  return end < 0 ? str.length : end;
}
var NUMBER_RE = /^(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d[\d_]*)?)n?/;
var tokenizeNumber = function(expr) {
  const match = NUMBER_RE.exec(expr);
  return match ? { type: "VALUE", value: match[0] } : false;
};
var SYMBOL_RE = /^[\p{ID_Start}_$][\p{ID_Continue}$\u200C\u200D]*/u;
var IDENTIFIER_CHAR_RE = /[\p{ID_Continue}$\u200C\u200D]/u;
var OBJECT_KEY_END_RE = /^\s*[:,}]/;
var tokenizeSymbol = function(expr, previous) {
  const match = SYMBOL_RE.exec(expr);
  if (!match) {
    return false;
  }
  const s = match[0];
  const isKey = (previous?.type === "LEFT_BRACE" || previous?.type === "COMMA") && OBJECT_KEY_END_RE.test(expr.slice(s.length));
  if (s in WORD_REPLACEMENT && !isKey) {
    return { type: "OPERATOR", value: WORD_REPLACEMENT[s], size: s.length };
  }
  return { type: "SYMBOL", value: s };
};
var OPERAND_PREFIXES = /* @__PURE__ */ new Set([
  "OPERATOR",
  "LEFT_BRACE",
  "LEFT_BRACKET",
  "LEFT_PAREN",
  "COMMA",
  "COLON"
]);
var OPERAND_KEYWORDS = /* @__PURE__ */ new Set(["void", "return"]);
var tokenizeRegExp = function(expr, previous, beforePrevious) {
  const afterKeyword = previous?.type === "SYMBOL" && OPERAND_KEYWORDS.has(previous.value) && beforePrevious?.value !== "." && beforePrevious?.value !== "?.";
  if (expr[0] !== "/" || previous && !afterKeyword && (!OPERAND_PREFIXES.has(previous.type) || previous.value === "++" || previous.value === "--")) {
    return false;
  }
  const i = regExpEnd(expr, 0);
  const flags = /^[a-z]*/.exec(expr.slice(i + 1))[0];
  return { type: "VALUE", value: expr.slice(0, i + 1 + flags.length) };
};
var tokenizeStatic = function(expr) {
  const char = expr[0];
  if (char && char in STATIC_TOKEN_MAP) {
    return { type: STATIC_TOKEN_MAP[char], value: char };
  }
  return false;
};
var tokenizeProperty = function(expr) {
  const match = SYMBOL_RE.exec(expr);
  return match ? { type: "SYMBOL", value: match[0] } : false;
};
var tokenizeOperator = function(expr) {
  for (let op of OPERATORS) {
    if (op === "?." && /\d/.test(expr[2])) {
      continue;
    }
    if (op.endsWith(" ")) {
      const word = op.slice(0, -1);
      const next = expr[word.length] || "";
      if (expr.startsWith(word) && !IDENTIFIER_CHAR_RE.test(next)) {
        return next === " " ? { type: "OPERATOR", value: op } : { type: "OPERATOR", value: op, size: word.length };
      }
    } else if (expr.startsWith(op)) {
      return { type: "OPERATOR", value: op };
    }
  }
  return false;
};
var TOKENIZERS = [
  tokenizeString,
  tokenizeRegExp,
  tokenizeNumber,
  tokenizeOperator,
  tokenizeSymbol,
  tokenizeStatic
];
var PROPERTY_TOKENIZERS = [tokenizeProperty, ...TOKENIZERS];
function tokenize(expr) {
  const result = [];
  let token = true;
  let error;
  let current = expr;
  try {
    while (token) {
      current = current.trim();
      while (current.startsWith("/*") || current.startsWith("//")) {
        current = current.slice(commentEnd(current, 0)).trim();
      }
      if (current) {
        const previous = result[result.length - 1];
        const isProperty = previous?.value === "." || previous?.value === "?.";
        for (let tokenizer of isProperty ? PROPERTY_TOKENIZERS : TOKENIZERS) {
          token = tokenizer(current, previous, result[result.length - 2]);
          if (token) {
            result.push(token);
            current = current.slice(token.size || token.value.length);
            break;
          }
        }
      } else {
        token = false;
      }
    }
  } catch (e) {
    error = e;
  }
  if (current.length || error) {
    throw new OwlError(`Tokenizer error: could not tokenize \`${expr}\``);
  }
  return result;
}
var isLeftSeparator = (token) => token && (token.type === "LEFT_BRACE" || token.type === "COMMA");
var isRightSeparator = (token) => token && (token.type === "RIGHT_BRACE" || token.type === "COMMA");
var paddedValues = /* @__PURE__ */ new Map([
  ["in ", " in "],
  ["instanceof", " instanceof "],
  ["void", "void "]
]);
function render(tokens) {
  let code = "";
  for (const t of tokens) {
    const value = t.isKeyword ? t.value + " " : paddedValues.get(t.value) || t.value;
    const last = code[code.length - 1];
    if ((last === "+" || last === "-") && value[0] === last || last && IDENTIFIER_CHAR_RE.test(last) && IDENTIFIER_CHAR_RE.test(value[0])) {
      code += " ";
    }
    code += value;
  }
  return code;
}
var LEFT_GROUPS = /* @__PURE__ */ new Set(["LEFT_BRACE", "LEFT_BRACKET", "LEFT_PAREN"]);
var RIGHT_GROUPS = /* @__PURE__ */ new Set(["RIGHT_BRACE", "RIGHT_BRACKET", "RIGHT_PAREN"]);
function bindArrowParams(tokens, end, scope) {
  let depth = 0;
  let start = end;
  for (; start >= 0; start--) {
    const type = tokens[start].type;
    if (RIGHT_GROUPS.has(type)) {
      depth++;
    } else if (LEFT_GROUPS.has(type) && !--depth) {
      break;
    }
  }
  bindPattern(tokens, start, scope);
  for (let k = start + 1; k < end; k++) {
    const t = tokens[k];
    if (t.type === "SYMBOL" && t.varName && scope.has(t.varName)) {
      t.value = `_${t.varName}`;
      t.isLocal = true;
    }
  }
  return start;
}
var DECLARATION_KEYWORDS = /* @__PURE__ */ new Set(["const", "let", "var"]);
function bindBlockDeclarations(tokens, start, scope) {
  let depth = 0;
  for (let k = start + 1; k < tokens.length && depth >= 0; k++) {
    const t = tokens[k];
    if (LEFT_GROUPS.has(t.type)) {
      depth++;
    } else if (RIGHT_GROUPS.has(t.type)) {
      depth--;
    } else if (!depth && t.type === "SYMBOL" && DECLARATION_KEYWORDS.has(t.value) && (tokens[k + 1]?.type === "SYMBOL" || tokens[k + 1]?.type === "LEFT_BRACE" || tokens[k + 1]?.type === "LEFT_BRACKET")) {
      t.isKeyword = true;
      k = bindDeclarators(tokens, k + 1, scope);
    }
  }
}
function bindDeclarators(tokens, start, scope) {
  let depth = 0;
  let inValue = false;
  let k = start;
  for (; k < tokens.length; k++) {
    const t = tokens[k];
    if (LEFT_GROUPS.has(t.type)) {
      if (!depth && !inValue) {
        k = bindPattern(tokens, k, scope);
      } else {
        depth++;
      }
    } else if (RIGHT_GROUPS.has(t.type)) {
      if (!depth--) {
        return k - 1;
      }
    } else if (depth) {
      continue;
    } else if (t.type === "COMMA") {
      inValue = false;
    } else if (t.type === "OPERATOR" && t.value === "=") {
      inValue = true;
    } else if (t.type === "OPERATOR" && t.value === ";") {
      return k;
    } else if (t.type === "SYMBOL" && !inValue) {
      scope.add(t.value);
    }
  }
  return k;
}
function bindPattern(tokens, start, scope) {
  const levels = [];
  let k = start;
  for (; k < tokens.length; k++) {
    const t = tokens[k];
    const level = levels[levels.length - 1];
    if (LEFT_GROUPS.has(t.type)) {
      const prev = tokens[k - 1]?.type;
      const inExpr = !!level && (level.inExpr || level.isObject && (prev === "LEFT_BRACE" || prev === "COMMA"));
      levels.push({ inExpr, base: inExpr, isObject: t.type === "LEFT_BRACE" });
    } else if (RIGHT_GROUPS.has(t.type)) {
      levels.pop();
      if (!levels.length) {
        return k;
      }
    } else if (t.type === "COMMA") {
      level.inExpr = level.base;
    } else if (t.type === "OPERATOR" && t.value === "=") {
      level.inExpr = true;
    } else if (t.type === "SYMBOL" && !level.inExpr && tokens[k + 1]?.type !== "COLON" && tokens[k - 1].value !== "." && tokens[k - 1].value !== "?.") {
      scope.add(t.varName ?? t.value);
    }
  }
  return k;
}
function isAsyncArrow(tokens, i) {
  const prev = tokens[i - 1];
  if (prev?.type === "OPERATOR" && (prev.value === "." || prev.value === "?.")) {
    return false;
  }
  let next = i + 1;
  if (tokens[next]?.type === "LEFT_PAREN") {
    let depth = 0;
    for (; next < tokens.length; next++) {
      const type = tokens[next].type;
      if (LEFT_GROUPS.has(type)) {
        depth++;
      } else if (RIGHT_GROUPS.has(type) && !--depth) {
        break;
      }
    }
  } else if (tokens[next]?.type !== "SYMBOL") {
    return false;
  }
  const arrow = tokens[next + 1];
  return arrow?.type === "OPERATOR" && arrow.value === "=>";
}
function collectVariables(tokens, start) {
  const vars = /* @__PURE__ */ new Set();
  for (let i = start; i < tokens.length; i++) {
    const t = tokens[i];
    if (t.varName && !t.isLocal) {
      vars.add(t.varName);
    }
    for (const v of t.templateVars || []) {
      vars.add(v);
    }
  }
  return [...vars];
}
function processExpr(expr, seededLocals, inAsyncArrow = false) {
  const scopeStack = [];
  if (seededLocals?.size || inAsyncArrow) {
    scopeStack.push({
      vars: seededLocals || /* @__PURE__ */ new Set(),
      depth: -Infinity,
      ternaries: 0,
      isAsync: inAsyncArrow
    });
  }
  const tokens = tokenize(expr);
  let i = 0;
  const stack = [];
  let topLevelArrowIndex = -1;
  let topLevelParams = null;
  function isLocal(name) {
    return scopeStack.some((s) => s.vars.has(name));
  }
  function innermostScopeAtDepth() {
    const scope = scopeStack[scopeStack.length - 1];
    return scope && scope.depth === stack.length ? scope : null;
  }
  while (i < tokens.length) {
    let token = tokens[i];
    let prevToken = tokens[i - 1];
    let nextToken = tokens[i + 1];
    let groupType = stack[stack.length - 1];
    switch (token.type) {
      case "LEFT_BRACE":
        if (prevToken?.value === "=>") {
          stack.push("BLOCK");
          const scope = scopeStack[scopeStack.length - 1];
          if (scope) {
            bindBlockDeclarations(tokens, i, scope.vars);
          }
        } else {
          stack.push(token.type);
        }
        break;
      case "LEFT_BRACKET":
      case "LEFT_PAREN":
        stack.push(token.type);
        break;
      case "RIGHT_BRACE":
      case "RIGHT_BRACKET":
      case "RIGHT_PAREN":
        stack.pop();
        while (scopeStack.length > 0 && stack.length < scopeStack[scopeStack.length - 1].depth) {
          scopeStack.pop();
        }
        break;
      case "COMMA":
        while (innermostScopeAtDepth()) {
          scopeStack.pop();
        }
        break;
      case "COLON": {
        let scope;
        while (scope = innermostScopeAtDepth()) {
          if (scope.ternaries) {
            scope.ternaries--;
            break;
          }
          scopeStack.pop();
        }
        break;
      }
      case "OPERATOR":
        if (token.value === ";") {
          while (innermostScopeAtDepth()) {
            scopeStack.pop();
          }
        } else if (token.value === "?") {
          const scope = innermostScopeAtDepth();
          if (scope) {
            scope.ternaries++;
          }
        }
        break;
    }
    if (token.type === "SYMBOL") {
      if (token.value === "async") {
        token.isKeyword = isAsyncArrow(tokens, i);
      } else if (token.value === "await") {
        token.isKeyword = !!scopeStack[scopeStack.length - 1]?.isAsync;
      }
    }
    let isVar = token.type === "SYMBOL" && !token.isKeyword && !RESERVED_WORDS.has(token.value);
    if (isVar) {
      if (prevToken) {
        if (groupType === "LEFT_BRACE" && isLeftSeparator(prevToken) && (isRightSeparator(nextToken) || nextToken?.type === "OPERATOR" && nextToken.value === "=")) {
          tokens.splice(i + 1, 0, { type: "COLON", value: ":" }, { ...token });
          nextToken = tokens[i + 1];
        }
        if (prevToken.type === "OPERATOR" && (prevToken.value === "." || prevToken.value === "?.")) {
          isVar = false;
        } else if (prevToken.type === "LEFT_BRACE" || prevToken.type === "COMMA") {
          if (nextToken && nextToken.type === "COLON") {
            isVar = false;
          }
        }
      }
      const startsStatement = groupType === "BLOCK" && (prevToken.type === "LEFT_BRACE" || prevToken.type === "RIGHT_BRACE" || prevToken.value === ";");
      if (isVar && startsStatement && STATEMENT_KEYWORDS.has(token.value)) {
        throw new OwlError(
          `Unsupported statement '${token.value}' in a template expression (\`${expr}\`): an arrow function's block body takes declarations, expressions and return only`
        );
      }
    }
    if (token.type === "TEMPLATE_STRING") {
      const currentLocals = /* @__PURE__ */ new Set();
      for (const scope of scopeStack) {
        for (const v of scope.vars) currentLocals.add(v);
      }
      const templateVars = [];
      token.value = token.replace((expr2) => {
        const isAsync = !!scopeStack[scopeStack.length - 1]?.isAsync;
        const processed = processExpr(expr2, currentLocals, isAsync);
        templateVars.push(...processed.variables);
        return processed.expr;
      });
      token.templateVars = templateVars;
    }
    if (nextToken && nextToken.type === "OPERATOR" && nextToken.value === "=>") {
      const newScope = /* @__PURE__ */ new Set();
      let paramStart = i;
      let params = [i, i + 1];
      if (token.type === "RIGHT_PAREN") {
        paramStart = bindArrowParams(tokens, i, newScope);
        params = [paramStart + 1, i];
      } else {
        newScope.add(token.value);
      }
      const isAsync = !!tokens[paramStart - 1]?.isKeyword;
      if (paramStart === 0 || paramStart === 1 && isAsync) {
        topLevelArrowIndex = i + 1;
        topLevelParams = params;
      }
      scopeStack.push({ vars: newScope, depth: stack.length, ternaries: 0, isAsync });
    }
    if (isVar) {
      token.varName = token.value;
      if (!isLocal(token.value)) {
        token.value = `ctx['${token.value}']`;
      } else {
        token.value = `_${token.value}`;
        token.isLocal = true;
      }
    }
    i++;
  }
  const freeVariables = topLevelArrowIndex === -1 ? null : collectVariables(tokens, topLevelParams[0]).filter((v) => v !== "this");
  const arrow = topLevelArrowIndex === -1 ? null : {
    isAsync: !!tokens[0].isKeyword,
    params: render(tokens.slice(...topLevelParams)),
    body: render(tokens.slice(topLevelArrowIndex + 1))
  };
  return {
    expr: render(tokens),
    freeVariables,
    variables: collectVariables(tokens, 0),
    arrow
  };
}
function compileExpr(expr) {
  return processExpr(expr).expr;
}
function findInterpolations(s) {
  const result = [];
  for (let i = 0; i < s.length; i++) {
    const isDouble = s.startsWith("{{", i);
    if (!isDouble && !s.startsWith("#{", i)) {
      continue;
    }
    let close;
    try {
      close = findClosingBrace(s, i + 2);
    } catch {
      continue;
    }
    if (isDouble && s[close + 1] !== "}") {
      continue;
    }
    const end = isDouble ? close + 2 : close + 1;
    result.push({ start: i, end, expr: s.slice(i + 2, close) });
    i = end - 1;
  }
  return result;
}
function isInterpolated(s) {
  return findInterpolations(s).length > 0;
}
function escapeTemplateString(str) {
  return str.replace(/\\/g, "\\\\").replace(/`/g, "\\`").replace(/\$\{/g, "\\${");
}
function interpolate(s) {
  const parts = findInterpolations(s);
  if (parts.length === 1 && parts[0].start === 0 && parts[0].end === s.length) {
    return `(${compileExpr(parts[0].expr)})`;
  }
  let r = "";
  let last = 0;
  for (const { start, end, expr } of parts) {
    r += escapeTemplateString(s.slice(last, start)) + "${" + compileExpr(expr) + "}";
    last = end;
  }
  return "`" + r + escapeTemplateString(s.slice(last)) + "`";
}

// ../owl-compiler/src/parse_xml.ts
function parseXML(xml) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, "text/xml");
  if (doc.getElementsByTagName("parsererror").length) {
    let msg = "Invalid XML in template.";
    const parsererrorText = doc.getElementsByTagName("parsererror")[0].textContent;
    if (parsererrorText) {
      msg += "\nThe parser has produced the following error message:\n" + parsererrorText;
      const position = /line(?: number)?\s+(\d+)\D+?column\s+(\d+)/i.exec(parsererrorText) || /(\d+)\D+(\d+)/.exec(parsererrorText);
      if (position) {
        const lineNumber = Number(position[1]);
        const column = Number(position[2]);
        const line = xml.split("\n")[lineNumber - 1];
        if (line && column >= 1 && column <= line.length) {
          msg += `
The error might be located at xml line ${lineNumber} column ${column}
${line}
${"-".repeat(column - 1)}^`;
        }
      }
    }
    throw new OwlError(msg);
  }
  return doc;
}

// ../owl-compiler/src/parser.ts
var ASTType = {
  Text: 0,
  DomNode: 2,
  Multi: 3,
  TIf: 4,
  TSet: 5,
  TCall: 6,
  TOut: 7,
  TForEach: 8,
  TKey: 9,
  TComponent: 10,
  TDebug: 11,
  TLog: 12,
  TCallSlot: 13,
  TCallBlock: 14,
  TTranslation: 15,
  TTranslationContext: 16
};
var ForEachNoFlag = {
  First: 1,
  Last: 2,
  Index: 4,
  Value: 8
};
var NO_DIRECTIVES = {};
var cache = /* @__PURE__ */ new WeakMap();
function parse(xml, customDir) {
  const customDirectives = customDir && Object.keys(customDir).length ? customDir : void 0;
  const ctx = { inPreTag: false, customDirectives };
  if (typeof xml === "string") {
    const elem = parseXML(`<t>${xml}</t>`).firstChild;
    return _parse(elem, ctx);
  }
  const directivesKey = customDirectives || NO_DIRECTIVES;
  let astCache = cache.get(directivesKey);
  if (!astCache) {
    astCache = /* @__PURE__ */ new WeakMap();
    cache.set(directivesKey, astCache);
  }
  let ast = astCache.get(xml);
  if (!ast) {
    ast = _parse(xml.cloneNode(true), ctx);
    astCache.set(xml, ast);
  }
  return ast;
}
function _parse(xml, ctx) {
  normalizeXML(xml);
  return parseNode(xml, ctx) || { type: ASTType.Text, value: "" };
}
function parseNode(node, ctx) {
  if (!(node instanceof Element)) {
    return parseTextCommentNode(node, ctx);
  }
  return parseTCustom(node, ctx) || parseTDebugLog(node, ctx) || parseTForEach(node, ctx) || parseTIf(node, ctx) || parseTTranslation(node, ctx) || parseTTranslationContext(node, ctx) || parseTKey(node, ctx) || parseTCall(node, ctx) || parseTCallBlock(node, ctx) || parseTOutNode(node, ctx) || parseTCallSlot(node, ctx) || parseComponent(node, ctx) || parseDOMNode(node, ctx) || parseTSetNode(node, ctx) || parseTNode(node, ctx);
}
function isTranslationContext(attribute) {
  return attribute === "t-translation-context" || attribute.startsWith(TRANSLATION_CONTEXT_PREFIX);
}
function unsupportedDirectiveError(directive, where) {
  return new OwlError(`Unsupported directive '${directive}' on ${where}`);
}
function tRefError(node) {
  return new OwlError(
    `Directive 't-ref' can only be used on DOM nodes (used on a <${node.tagName}>)`
  );
}
function exprAttr(node, attr) {
  const value = node.getAttribute(attr);
  if (value !== null && !value.trim()) {
    throw emptyExprError(attr, node);
  }
  return value;
}
function emptyExprError(attr, node) {
  return new OwlError(`Directive '${attr}' needs an expression (on a <${node.tagName}>)`);
}
function wrapping(ast, content) {
  if (!content || content.hasNoRepresentation) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function isComponentNode(el) {
  const first = el.tagName[0];
  return first === first.toUpperCase() || el.hasAttribute("t-component");
}
var TRANSLATION_CONTEXT_PREFIX = "t-translation-context-";
function collectHandler(found, name, value, events = true) {
  if (name.startsWith(TRANSLATION_CONTEXT_PREFIX)) {
    (found.translationCtx ||= {})[name.slice(TRANSLATION_CONTEXT_PREFIX.length)] = value;
    return true;
  }
  if (events && name.startsWith("t-on-")) {
    (found.on ||= {})[name.slice(5)] = value;
    return true;
  }
  return false;
}
function parseTNode(node, ctx) {
  if (node.tagName !== "t") {
    return null;
  }
  if (node.hasAttribute("t-ref")) {
    throw tRefError(node);
  }
  return parseChildNodes(node, ctx);
}
var lineBreakRE = /[\r\n]/;
var htmlWhitespaceOnlyRE = /^[ \t\n\r\f]*$/;
function parseTextCommentNode(node, ctx) {
  if (node.nodeType === Node.TEXT_NODE) {
    let value = node.textContent || "";
    if (!ctx.inPreTag && lineBreakRE.test(value) && htmlWhitespaceOnlyRE.test(value)) {
      return null;
    }
    return { type: ASTType.Text, value };
  }
  return null;
}
function parseTCustom(node, ctx) {
  if (!ctx.customDirectives) {
    return null;
  }
  const nodeAttrsNames = node.getAttributeNames();
  for (let attr of nodeAttrsNames) {
    if (attr === "t-custom" || attr === "t-custom-") {
      throw new OwlError("Missing custom directive name with t-custom directive");
    }
    if (attr.startsWith("t-custom-")) {
      const directiveName = attr.split(".")[0].slice(9);
      const customDirective = ctx.customDirectives[directiveName];
      if (!customDirective) {
        throw new OwlError(`Custom directive "${directiveName}" is not defined`);
      }
      const value = node.getAttribute(attr);
      const modifiers = attr.split(".").slice(1);
      node.removeAttribute(attr);
      try {
        customDirective(node, value, modifiers);
      } catch (error) {
        throw new OwlError(
          `Custom directive "${directiveName}" throw the following error: ${error}`
        );
      }
      return parseNode(node, ctx);
    }
  }
  return null;
}
function parseTDebugLog(node, ctx) {
  if (node.hasAttribute("t-debug")) {
    node.removeAttribute("t-debug");
    const content = parseNode(node, ctx);
    return wrapping({ type: ASTType.TDebug, content }, content);
  }
  if (node.hasAttribute("t-log")) {
    const expr = node.getAttribute("t-log");
    node.removeAttribute("t-log");
    const content = parseNode(node, ctx);
    return wrapping({ type: ASTType.TLog, expr, content }, content);
  }
  return null;
}
var ROOT_SVG_TAGS = /* @__PURE__ */ new Set(["svg", "g", "path"]);
var ATT_DIRECTIVE_RE = /^t-att(f?-.+)?$/;
var T_MODEL_MODIFIERS = /* @__PURE__ */ new Set(["lazy", "trim", "number", "proxy"]);
var SLOT_HIDING_DIRECTIVES = /* @__PURE__ */ new Set([
  "t-if",
  "t-elif",
  "t-else",
  "t-foreach",
  "t-out",
  "t-esc",
  "t-call",
  "t-call-block",
  "t-call-slot",
  "t-slot",
  "t-set"
]);
function parseDOMNode(node, ctx) {
  const { tagName } = node;
  const dynamicTag = node.getAttribute("t-tag");
  node.removeAttribute("t-tag");
  if (tagName === "t" && !dynamicTag) {
    return null;
  }
  if (tagName.startsWith("block-")) {
    throw new OwlError(`Invalid tag name: '${tagName}'`);
  }
  ctx = Object.assign({}, ctx);
  if (tagName === "pre") {
    ctx.inPreTag = true;
  }
  let ns = !ctx.nameSpace && ROOT_SVG_TAGS.has(tagName) ? "http://www.w3.org/2000/svg" : null;
  const ref = exprAttr(node, "t-ref");
  node.removeAttribute("t-ref");
  const nodeAttrsNames = node.getAttributeNames();
  let attrs = null;
  const handlers = { on: null, translationCtx: null };
  let model = null;
  for (let attr of nodeAttrsNames) {
    const value = node.getAttribute(attr);
    if (attr === "t-on" || attr === "t-on-") {
      throw new OwlError("Missing event name with t-on directive");
    }
    if (collectHandler(handlers, attr, value)) {
      continue;
    }
    if (attr === "t-model" || attr.startsWith("t-model.")) {
      if (!["input", "select", "textarea"].includes(tagName)) {
        throw new OwlError(
          "The t-model directive only works with <input>, <textarea> and <select>"
        );
      }
      if (!value.trim()) {
        throw emptyExprError(attr, node);
      }
      const typeAttr = node.getAttribute("type");
      const isInput = tagName === "input";
      const isSelect = tagName === "select";
      const isCheckboxInput = isInput && typeAttr === "checkbox";
      const isRadioInput = isInput && typeAttr === "radio";
      const modifiers = attr.split(".").slice(1);
      for (const modifier of modifiers) {
        if (!T_MODEL_MODIFIERS.has(modifier)) {
          throw new OwlError(`Unknown t-model modifier: '${modifier}'`);
        }
      }
      const hasTrimMod = modifiers.includes("trim");
      const hasLazyMod = hasTrimMod || modifiers.includes("lazy");
      const hasNumberMod = modifiers.includes("number");
      const hasProxyMod = modifiers.includes("proxy");
      const eventType = isRadioInput ? "click" : isSelect || hasLazyMod ? "change" : "input";
      model = {
        expr: value,
        targetAttr: isCheckboxInput ? "checked" : "value",
        specialInitTargetAttr: isRadioInput ? "checked" : null,
        eventType,
        hasDynamicChildren: false,
        shouldTrim: hasTrimMod,
        shouldNumberize: hasNumberMod,
        isProxy: hasProxyMod
      };
      if (isSelect) {
        ctx.tModelInfo = model;
      }
    } else if (attr.startsWith("block-")) {
      throw new OwlError(`Invalid attribute: '${attr}'`);
    } else if (attr === "xmlns") {
      ns = value;
    } else if (attr !== "t-name") {
      if (attr.startsWith("t-")) {
        if (!ATT_DIRECTIVE_RE.test(attr)) {
          if (attr.startsWith("t-custom-") && attr.length > 9) {
            throw new OwlError(`Custom directive "${attr.split(".")[0].slice(9)}" is not defined`);
          }
          throw new OwlError(`Unknown QWeb directive: '${attr}'`);
        }
        if (!attr.startsWith("t-attf") && !value.trim()) {
          throw emptyExprError(attr, node);
        }
      }
      const tModel = ctx.tModelInfo;
      if (tModel && ["t-att-value", "t-attf-value"].includes(attr)) {
        tModel.hasDynamicChildren = true;
      }
      attrs = attrs || {};
      attrs[attr] = value;
    }
  }
  if (ns) {
    ctx.nameSpace = ns;
  }
  const children = parseChildren(node, ctx);
  return {
    type: ASTType.DomNode,
    tag: tagName,
    dynamicTag,
    attrs,
    attrsTranslationCtx: handlers.translationCtx,
    on: handlers.on,
    ref,
    content: children,
    model,
    ns
  };
}
function parseTOutNode(node, ctx) {
  if (!node.hasAttribute("t-out") && !node.hasAttribute("t-esc")) {
    return null;
  }
  if (node.hasAttribute("t-esc")) {
    console.warn(
      `t-esc has been deprecated in favor of t-out. If the value to render is not wrapped by the "markup" function, it will be escaped`
    );
  }
  const expr = exprAttr(node, node.hasAttribute("t-out") ? "t-out" : "t-esc");
  node.removeAttribute("t-out");
  node.removeAttribute("t-esc");
  const tOut = { type: ASTType.TOut, expr, body: null };
  if (node.tagName === "t" && !node.hasAttribute("t-tag")) {
    if (node.hasAttribute("t-ref")) {
      throw tRefError(node);
    }
    const directive = node.getAttributeNames().find((a) => a.startsWith("t-") && a !== "t-name" && !isTranslationContext(a));
    if (directive) {
      throw unsupportedDirectiveError(directive, "a <t> with t-out");
    }
    const body = parseChildren(node, ctx);
    tOut.body = body.length ? body : null;
    return tOut;
  }
  const ref = exprAttr(node, "t-ref");
  node.removeAttribute("t-ref");
  const ast = parseNode(node, ctx);
  if (ast?.type !== ASTType.DomNode) {
    throw new OwlError(`t-out cannot be used on a <${node.tagName}> with this combination`);
  }
  tOut.body = ast.content.length ? ast.content : null;
  return {
    ...ast,
    ref,
    content: [tOut]
  };
}
function parseTForEach(node, ctx) {
  if (!node.hasAttribute("t-foreach")) {
    return null;
  }
  const html = node.outerHTML;
  const collection = exprAttr(node, "t-foreach");
  node.removeAttribute("t-foreach");
  const elem = node.getAttribute("t-as");
  if (!elem) {
    throw new OwlError(
      `Directive t-foreach should always be used with t-as (expression: t-foreach="${collection}")`
    );
  }
  node.removeAttribute("t-as");
  const key = exprAttr(node, "t-key");
  if (!key) {
    throw new OwlError(
      `"Directive t-foreach should always be used with a t-key!" (expression: t-foreach="${collection}" t-as="${elem}")`
    );
  }
  node.removeAttribute("t-key");
  const memo = exprAttr(node, "t-memo");
  node.removeAttribute("t-memo");
  const body = parseNode(node, ctx);
  if (!body) {
    return null;
  }
  if (memo !== null) {
    const directive = findNode(body, unvisitable);
    if (body.hasNoRepresentation || directive) {
      throw new OwlError(
        `t-memo needs an item made of elements, text, t-out and components only (expression: t-foreach="${collection}" t-memo="${memo}"${directive ? `, found ${directive}` : ""})`
      );
    }
  }
  const hasNoTCall = !/\st-call="/.test(html);
  let noFlags = 0;
  if (hasNoTCall && !html.includes(`${elem}_first`)) noFlags |= ForEachNoFlag.First;
  if (hasNoTCall && !html.includes(`${elem}_last`)) noFlags |= ForEachNoFlag.Last;
  if (hasNoTCall && !html.includes(`${elem}_index`)) noFlags |= ForEachNoFlag.Index;
  if (hasNoTCall && !html.includes(`${elem}_value`)) noFlags |= ForEachNoFlag.Value;
  const ast = {
    type: ASTType.TForEach,
    collection,
    elem,
    body,
    key,
    noFlags
  };
  if (memo !== null) {
    ast.memo = memo;
    if (findNode(body, memoizedContent)) {
      ast.memoContent = true;
    }
  }
  return wrapping(ast, body);
}
var UNVISITABLE = {
  [ASTType.TCall]: "t-call",
  [ASTType.TCallSlot]: "t-slot",
  [ASTType.TCallBlock]: "t-call-block"
};
function findNode(value, test) {
  if (!value || typeof value !== "object") {
    return null;
  }
  if (!Array.isArray(value)) {
    const found = typeof value.type === "number" ? test(value) : null;
    if (found) {
      return found;
    }
  }
  for (const key in value) {
    const found = findNode(value[key], test);
    if (found) {
      return found;
    }
  }
  return null;
}
var unvisitable = (ast) => UNVISITABLE[ast.type] || null;
var memoizedContent = (ast) => ast.type === ASTType.TComponent ? "a component" : ast.type === ASTType.TForEach && ast.memo !== void 0 ? "a memoized list" : null;
function parseTKey(node, ctx) {
  if (!node.hasAttribute("t-key")) {
    return null;
  }
  const key = exprAttr(node, "t-key");
  node.removeAttribute("t-key");
  const content = parseNode(node, ctx);
  if (!content) {
    return null;
  }
  return wrapping({ type: ASTType.TKey, expr: key, content }, content);
}
function parseTCall(node, ctx) {
  if (!node.hasAttribute("t-call")) {
    return null;
  }
  if (node.tagName !== "t") {
    throw new OwlError(
      `Directive 't-call' can only be used on <t> nodes (used on a <${node.tagName}>)`
    );
  }
  const subTemplate = node.getAttribute("t-call");
  const context = exprAttr(node, "t-call-context");
  node.removeAttribute("t-call");
  node.removeAttribute("t-call-context");
  let attrs = null;
  const handlers = { on: null, translationCtx: null };
  for (let attributeName of node.getAttributeNames()) {
    const value = node.getAttribute(attributeName);
    if (collectHandler(handlers, attributeName, value, false)) {
      continue;
    }
    if (attributeName.startsWith("t-")) {
      throw unsupportedDirectiveError(attributeName, "a t-call node");
    }
    attrs = attrs || {};
    attrs[attributeName] = value;
  }
  const body = parseChildNodes(node, ctx);
  return {
    type: ASTType.TCall,
    name: subTemplate,
    attrs,
    attrsTranslationCtx: handlers.translationCtx,
    body,
    context
  };
}
function parseTCallBlock(node, ctx) {
  if (!node.hasAttribute("t-call-block")) {
    return null;
  }
  const name = exprAttr(node, "t-call-block");
  const directive = node.getAttributeNames().find((a) => a.startsWith("t-") && a !== "t-call-block" && !isTranslationContext(a));
  if (directive) {
    throw unsupportedDirectiveError(directive, "a t-call-block node");
  }
  return {
    type: ASTType.TCallBlock,
    name
  };
}
function parseTIf(node, ctx) {
  if (!node.hasAttribute("t-if")) {
    return null;
  }
  const condition = exprAttr(node, "t-if");
  node.removeAttribute("t-if");
  const content = parseNode(node, ctx) || { type: ASTType.Text, value: "" };
  let nextElement = node.nextElementSibling;
  const tElifs = [];
  while (nextElement && nextElement.hasAttribute("t-elif")) {
    const condition2 = exprAttr(nextElement, "t-elif");
    nextElement.removeAttribute("t-elif");
    const tElif = parseNode(nextElement, ctx) || { type: ASTType.Text, value: "" };
    const next = nextElement.nextElementSibling;
    nextElement.remove();
    nextElement = next;
    tElifs.push({ condition: condition2, content: tElif });
  }
  let tElse = null;
  if (nextElement && nextElement.hasAttribute("t-else")) {
    nextElement.removeAttribute("t-else");
    tElse = parseNode(nextElement, ctx);
    nextElement.remove();
  }
  return {
    type: ASTType.TIf,
    condition,
    content,
    tElif: tElifs.length ? tElifs : null,
    tElse
  };
}
function parseTSetNode(node, ctx) {
  if (!node.hasAttribute("t-set")) {
    return null;
  }
  const name = node.getAttribute("t-set");
  const value = node.getAttribute("t-value") || null;
  const isText = [...node.childNodes].every(
    (n) => n.nodeType === Node.TEXT_NODE || n.nodeType === Node.COMMENT_NODE
  );
  let defaultValue = null;
  let body = null;
  if (isText) {
    defaultValue = node.textContent || null;
  } else {
    const content = parseChildren(node, ctx);
    body = content.length ? content : null;
  }
  return { type: ASTType.TSet, name, value, defaultValue, body, hasNoRepresentation: true };
}
var directiveErrorMap = /* @__PURE__ */ new Map([
  [
    "t-ref",
    "t-ref is no longer supported on components. Consider exposing only the public part of the component's API through a callback prop."
  ],
  ["t-att", "t-att makes no sense on component: props are already treated as expressions"],
  [
    "t-attf",
    "t-attf is not supported on components: use template strings for string interpolation in props"
  ]
]);
function parseComponent(node, ctx) {
  let name = node.tagName;
  let isDynamic = node.hasAttribute("t-component");
  if (isDynamic && name !== "t") {
    throw new OwlError(
      `Directive 't-component' can only be used on <t> nodes (used on a <${name}>)`
    );
  }
  if (!isComponentNode(node)) {
    return null;
  }
  if (isDynamic) {
    name = exprAttr(node, "t-component");
    node.removeAttribute("t-component");
  }
  const dynamicProps = exprAttr(node, "t-props");
  node.removeAttribute("t-props");
  const defaultSlotScope = node.getAttribute("t-slot-scope");
  node.removeAttribute("t-slot-scope");
  const handlers = { on: null, translationCtx: null };
  let props = null;
  for (let name2 of node.getAttributeNames()) {
    const value = node.getAttribute(name2);
    if (collectHandler(handlers, name2, value)) {
      continue;
    }
    if (name2.startsWith("t-")) {
      const message = directiveErrorMap.get(name2.split("-").slice(0, 2).join("-"));
      throw new OwlError(message || `unsupported directive on Component: ${name2}`);
    }
    props = props || {};
    props[name2] = value;
  }
  let slots = null;
  if (node.hasChildNodes()) {
    const clone = node.cloneNode(true);
    const slotNodes = Array.from(clone.querySelectorAll("[t-set-slot]")).filter(
      (slotNode) => isOwnSlot(slotNode, clone)
    );
    for (let slotNode of slotNodes) {
      const name2 = slotNode.getAttribute("t-set-slot");
      slotNode.removeAttribute("t-set-slot");
      slotNode.remove();
      const slotHandlers = { on: null, translationCtx: null };
      let attrs = null;
      let scope = null;
      for (let attributeName of slotNode.getAttributeNames()) {
        const value = slotNode.getAttribute(attributeName);
        if (attributeName === "t-slot-scope") {
          scope = value;
        } else if (!collectHandler(slotHandlers, attributeName, value)) {
          continue;
        }
        slotNode.removeAttribute(attributeName);
      }
      const slotAst = parseNode(slotNode, ctx);
      for (let attributeName of slotNode.getAttributeNames()) {
        attrs = attrs || {};
        attrs[attributeName] = slotNode.getAttribute(attributeName);
      }
      slots = slots || {};
      slots[name2] = {
        content: slotAst,
        on: slotHandlers.on,
        attrs,
        attrsTranslationCtx: slotHandlers.translationCtx,
        scope
      };
    }
    const defaultContent = parseChildNodes(clone, ctx);
    slots = slots || {};
    if (defaultContent && !slots.default) {
      slots.default = {
        content: defaultContent,
        on: null,
        attrs: null,
        attrsTranslationCtx: null,
        scope: defaultSlotScope
      };
    }
  }
  return {
    type: ASTType.TComponent,
    name,
    isDynamic,
    dynamicProps,
    props,
    propsTranslationCtx: handlers.translationCtx,
    slots,
    on: handlers.on
  };
}
function isOwnSlot(slotNode, root) {
  if (slotNode.tagName !== "t") {
    throw new OwlError(
      `Directive 't-set-slot' can only be used on <t> nodes (used on a <${slotNode.tagName}>)`
    );
  }
  let directiveAbove = null;
  for (let el = slotNode.parentElement; el !== root; el = el.parentElement) {
    if (isComponentNode(el)) {
      return false;
    }
    if (el.hasAttribute("t-set-slot")) {
      throw new OwlError(
        `Directive 't-set-slot' cannot be nested in another t-set-slot (slot "${slotNode.getAttribute("t-set-slot")}" in slot "${el.getAttribute("t-set-slot")}")`
      );
    }
    const directive = el.getAttributeNames().find((a) => SLOT_HIDING_DIRECTIVES.has(a));
    directiveAbove ||= directive ? `${directive} on a <${el.tagName}>` : null;
  }
  if (directiveAbove) {
    throw new OwlError(
      `Directive 't-set-slot' cannot be used under a directive (${directiveAbove}) inside a component`
    );
  }
  return true;
}
function parseTCallSlot(node, ctx) {
  if (!node.hasAttribute("t-call-slot") && !node.hasAttribute("t-slot")) {
    return null;
  }
  if (node.hasAttribute("t-slot")) {
    console.warn(`t-slot has been renamed t-call-slot.`);
  }
  const name = node.getAttribute("t-call-slot") || node.getAttribute("t-slot");
  node.removeAttribute("t-call-slot");
  node.removeAttribute("t-slot");
  const dynamicProps = exprAttr(node, "t-props");
  node.removeAttribute("t-props");
  let attrs = null;
  const handlers = { on: null, translationCtx: null };
  for (let attributeName of node.getAttributeNames()) {
    const value = node.getAttribute(attributeName);
    if (collectHandler(handlers, attributeName, value)) {
      continue;
    }
    if (attributeName.startsWith("t-")) {
      throw unsupportedDirectiveError(attributeName, "a t-call-slot node");
    }
    attrs = attrs || {};
    attrs[attributeName] = value;
  }
  return {
    type: ASTType.TCallSlot,
    name,
    dynamicProps,
    attrs,
    attrsTranslationCtx: handlers.translationCtx,
    on: handlers.on,
    defaultContent: parseChildNodes(node, ctx)
  };
}
function parseWrapped(node, ctx, attr, wrap) {
  node.removeAttribute(attr);
  const result = parseNode(node, ctx);
  if (result?.type === ASTType.Multi) {
    return makeASTMulti(result.content.map(wrap));
  }
  return wrap(result);
}
function parseTTranslation(node, ctx) {
  if (node.getAttribute("t-translation") !== "off") {
    return null;
  }
  return parseWrapped(
    node,
    ctx,
    "t-translation",
    (content) => wrapping({ type: ASTType.TTranslation, content }, content)
  );
}
function parseTTranslationContext(node, ctx) {
  const translationCtx = node.getAttribute("t-translation-context");
  if (!translationCtx) {
    return null;
  }
  return parseWrapped(
    node,
    ctx,
    "t-translation-context",
    (content) => wrapping(
      { type: ASTType.TTranslationContext, content, translationCtx },
      content
    )
  );
}
function parseChildren(node, ctx) {
  const children = [];
  for (let child of node.childNodes) {
    const childAst = parseNode(child, ctx);
    if (childAst) {
      if (childAst.type === ASTType.Multi) {
        children.push(...childAst.content);
      } else {
        children.push(childAst);
      }
    }
  }
  return children;
}
function makeASTMulti(children) {
  const ast = { type: ASTType.Multi, content: children };
  if (children.every((c) => c.hasNoRepresentation)) {
    ast.hasNoRepresentation = true;
  }
  return ast;
}
function parseChildNodes(node, ctx) {
  const children = parseChildren(node, ctx);
  switch (children.length) {
    case 0:
      return null;
    case 1:
      return children[0];
    default:
      return makeASTMulti(children);
  }
}
function normalizeTIf(el) {
  let tbranch = el.querySelectorAll("[t-elif], [t-else]");
  for (let i = 0, ilen = tbranch.length; i < ilen; i++) {
    let node = tbranch[i];
    let prevElem = node.previousElementSibling;
    if (prevElem && (prevElem.hasAttribute("t-if") || prevElem.hasAttribute("t-elif"))) {
      if (prevElem.hasAttribute("t-foreach")) {
        throw new OwlError(
          "t-if cannot stay at the same level as t-foreach when using t-elif or t-else"
        );
      }
      const elseIf = node.hasAttribute("t-else") && node.hasAttribute("t-if");
      const branches = ["t-if", "t-elif", "t-else"].filter((a) => node.hasAttribute(a)).length;
      if (!(elseIf && !node.hasAttribute("t-elif")) && branches > 1) {
        throw new OwlError("Only one conditional branching directive is allowed per node");
      }
      let textNode;
      while ((textNode = node.previousSibling) !== prevElem) {
        if (textNode.nodeValue.trim().length && textNode.nodeType !== 8) {
          throw new OwlError("text is not allowed between branching directives");
        }
        textNode.remove();
      }
    } else {
      throw new OwlError(
        "t-elif and t-else directives must be preceded by a t-if or t-elif directive"
      );
    }
  }
}
function normalizeTOut(el) {
  const elements = [...el.querySelectorAll(`[t-out], [t-esc]`)].filter(isComponentNode);
  for (const el2 of elements) {
    if (el2.childNodes.length) {
      throw new OwlError(`Cannot have t-out on a component that already has content`);
    }
    const directive = el2.hasAttribute("t-out") ? "t-out" : "t-esc";
    const value = el2.getAttribute(directive);
    el2.removeAttribute(directive);
    const t = el2.ownerDocument.createElement("t");
    t.setAttribute(directive, value);
    el2.appendChild(t);
  }
}
function normalizeXML(el) {
  normalizeTIf(el);
  normalizeTOut(el);
}

// ../owl-compiler/src/code_generator.ts
var SCOPE_MARK = "scope";
var SCOPE_MARKER_RE = /\u0001scope\d+\u0001/g;
var CONTEXT_WRITE = /ctx\['[^']*'\]\s*(?:[-+*/%&|^]|\*\*|<<|>>>?|&&|\|\||\?\?)?=(?![=>])|ctx\['[^']*'\]\s*(?:\+\+|--)|(?:\+\+|--)\s*ctx\[|delete\s+ctx\[|[[,{:]\s*ctx\['[^']*'\]\s*[,\]}][^;=\n]*?=(?![=>])/;
var MAX_LAZY_LOOP_KEYS = 3;
var KEY_MARK = "\\u0002";
var whitespaceRE = /[ \t\n\r\f]+/g;
var xmlDoc;
if (typeof document !== "undefined") {
  xmlDoc = document.implementation.createDocument(null, null, null);
}
var LITERAL_RE = /^(?:'[^'\\]*'|"[^"\\]*"|`(?:[^`\\]|\\.)*`|-?\d[\d.e+-]*|true|false|null|undefined|\{.*\})$/s;
function isProp(tag, key) {
  switch (tag) {
    case "input":
      return key === "checked" || key === "indeterminate" || key === "value" || key === "readonly" || key === "readOnly" || key === "disabled";
    case "option":
      return key === "selected" || key === "disabled";
    case "textarea":
      return key === "value" || key === "readonly" || key === "readOnly" || key === "disabled";
    case "select":
      return key === "value" || key === "disabled";
    case "button":
    case "optgroup":
      return key === "disabled";
  }
  return false;
}
function propKey(name) {
  return /^[a-z_]+$/i.test(name) ? name : `'${name}'`;
}
function toStringExpression(str) {
  return `\`${escapeTemplateString(str)}\``;
}
var BlockDescription = class {
  varName;
  blockName;
  dynamicTagName = null;
  isRoot = false;
  hasDynamicChildren = false;
  children = [];
  data = [];
  // the code of the block's handlers, in the order of their data index
  handlers = [];
  dom;
  currentDom;
  target;
  type;
  parentVar = "";
  id;
  generateId;
  constructor(id, target, type, generateId) {
    this.id = id;
    this.generateId = generateId;
    this.varName = "b" + this.id;
    this.blockName = "block" + this.id;
    this.target = target;
    this.type = type;
  }
  insertData(str, prefix = "d") {
    const id = this.generateId(prefix);
    this.target.addLine(`let ${id} = ${str};`);
    return this.data.push(id) - 1;
  }
  // a handler's data is the context; its code is static, given with the block
  insertHandler(fn) {
    this.handlers.push(fn);
    return this.data.push("ctx") - 1;
  }
  insert(dom) {
    if (this.currentDom) {
      this.currentDom.appendChild(dom);
    } else {
      this.dom = dom;
    }
  }
  generateExpr(expr) {
    if (this.type === "block") {
      const hasChildren = this.children.length;
      let params = this.data.length ? `[${this.data.join(", ")}]` : hasChildren ? "[]" : "";
      if (hasChildren) {
        params += ", [" + this.children.map((c) => c.varName).join(", ") + "]";
      }
      if (this.handlers.length) {
        params += `${hasChildren ? "" : ", null"}, ${this.blockName}_handlers`;
      }
      if (this.dynamicTagName) {
        return `toggler(${this.dynamicTagName}, ${this.blockName}(${this.dynamicTagName})(${params}))`;
      }
      return `${this.blockName}(${params})`;
    } else if (this.type === "list") {
      return `list(c_block${this.id})`;
    }
    return expr;
  }
  asXmlString() {
    const t = xmlDoc.createElement("t");
    t.appendChild(this.dom);
    return t.innerHTML;
  }
};
function createContext(parentCtx, params) {
  return Object.assign(
    {
      block: null,
      index: 0,
      forceNewBlock: true,
      translate: parentCtx.translate,
      translationCtx: parentCtx.translationCtx,
      tKeyExpr: null,
      nameSpace: parentCtx.nameSpace,
      tModelSelected: parentCtx.tModelSelected,
      inPreTag: parentCtx.inPreTag
    },
    params
  );
}
var CodeTarget = class {
  name;
  indentLevel = 0;
  loopLevel = 0;
  loopCtxVars = [];
  // the loops being compiled, innermost last
  loops = [];
  // the loop levels whose item (or, for 0, whose function scope) a t-set writes
  writtenLevels = /* @__PURE__ */ new Set();
  // loop levels whose key is concatenated into a string key: they get a
  // `skey<level>` that tells object keys apart
  stringKeyLevels = /* @__PURE__ */ new Set();
  tSetVars = /* @__PURE__ */ new Map();
  // the loop levels whose item is memoized: a memo hit skips the item's body
  memoLevels = [];
  code = [];
  hasRoot = false;
  deferReturn = false;
  needsScopeProtection = false;
  on;
  constructor(name, on) {
    this.name = name;
    this.on = on || null;
  }
  addLine(line, idx) {
    const prefix = new Array(this.indentLevel + 2).join("  ");
    if (idx === void 0) {
      this.code.push(prefix + line);
    } else {
      this.code.splice(idx, 0, prefix + line);
    }
  }
  generateCode() {
    let result = [];
    result.push(`function ${this.name}(ctx, node, key = "") {`);
    if (this.needsScopeProtection) {
      result.push(`  ctx = Object.create(ctx);`);
    }
    for (let line of this.code) {
      result.push(line);
    }
    if (!this.hasRoot) {
      result.push(`return text('');`);
    }
    result.push(`}`);
    return result.join("\n  ");
  }
  // the key of a list's child: of the item of the innermost loop, which a
  // list's child is always in
  currentKey(ctx) {
    if (ctx.tKeyExpr) {
      return `\`\${${this.stringKey(this.loopLevel)}}${KEY_MARK}k\${${ctx.tKeyExpr}}\``;
    }
    return `key${this.loopLevel}`;
  }
  stringKey(level) {
    this.stringKeyLevels.add(level);
    return `skey${level}`;
  }
};
var TRANSLATABLE_ATTRS = [
  "alt",
  "aria-label",
  "aria-placeholder",
  "aria-roledescription",
  "aria-valuetext",
  "label",
  "placeholder",
  "title"
];
var translationRE = /^(\s*)([\s\S]+?)(\s*)$/;
var CodeGenerator = class {
  blocks = [];
  scopeSites = [];
  isDebug = false;
  targets = [];
  target = new CodeTarget("template");
  templateName;
  dev;
  translateFn;
  translatableAttributes = TRANSLATABLE_ATTRS;
  ast;
  staticDefs = [];
  hoistedHandlers = /* @__PURE__ */ new Map();
  helpers = /* @__PURE__ */ new Set();
  // per generator, so that generating a template (a translateFn may compile
  // another) never shifts the names of the one in progress
  nextBlockId = 1;
  nextDataIds = {};
  generateId = (prefix = "") => {
    const n = (this.nextDataIds[prefix] || 0) + 1;
    this.nextDataIds[prefix] = n;
    return prefix + n;
  };
  constructor(ast, options) {
    this.translateFn = options.translateFn || ((s) => s);
    if (options.translatableAttributes) {
      const attrs = new Set(TRANSLATABLE_ATTRS);
      for (let attr of options.translatableAttributes) {
        if (attr.startsWith("-")) {
          attrs.delete(attr.slice(1));
        } else {
          attrs.add(attr);
        }
      }
      this.translatableAttributes = [...attrs];
    }
    this.dev = options.dev || false;
    this.ast = ast;
    this.templateName = options.name;
    if (options.name) {
      const name = options.name.replace(/[^a-zA-Z0-9_$]/g, "_");
      this.target.name = options.name.startsWith("__") ? name : `template_${name}`;
    }
    if (options.hasGlobalValues) {
      this.helpers.add("__globals__");
    }
  }
  generateCode() {
    const ast = this.ast;
    this.isDebug = ast.type === ASTType.TDebug;
    this.compileAST(ast, {
      block: null,
      index: 0,
      forceNewBlock: false,
      translate: true,
      translationCtx: "",
      tKeyExpr: null
    });
    this.resolveScopes();
    let mainCode = [`  let { text, createBlock, list, multi, html, toggler } = bdom;`];
    if (this.helpers.size) {
      mainCode.push(`let { ${[...this.helpers].join(", ")} } = helpers;`);
    }
    if (this.templateName) {
      const name = JSON.stringify(this.templateName).replace(/[\u2028\u2029]/g, " ");
      mainCode.push(`// Template name: ${name}`);
    }
    for (let { id, expr } of this.staticDefs) {
      mainCode.push(`const ${id} = ${expr};`);
    }
    if (this.blocks.length) {
      mainCode.push(``);
      for (let block of this.blocks) {
        let xmlString = toStringExpression(block.asXmlString());
        if (block.dynamicTagName) {
          const name = block.dom.nodeName;
          const tag = `\${tag || '${name}'}`;
          const close = `</${name}>\``;
          xmlString = `\`<${tag}` + xmlString.slice(`\`<${name}`.length);
          if (xmlString.endsWith(close)) {
            xmlString = xmlString.slice(0, -close.length) + `</${tag}>\``;
          }
          if (block.handlers.length) {
            const types = `${block.blockName}_types`;
            mainCode.push(
              `const ${block.blockName}_handlers = [${block.handlers.join(", ")}];`,
              `const ${types} = Object.create(null);`,
              `let ${block.blockName} = tag => ${types}[tag] || (${types}[tag] = createBlock(${xmlString}, ${block.blockName}_handlers));`
            );
          } else {
            mainCode.push(`let ${block.blockName} = tag => createBlock(${xmlString});`);
          }
        } else {
          let handlers = "";
          if (block.handlers.length) {
            handlers = `, ${block.blockName}_handlers`;
            mainCode.push(`const ${block.blockName}_handlers = [${block.handlers.join(", ")}];`);
          }
          mainCode.push(`let ${block.blockName} = createBlock(${xmlString}${handlers});`);
        }
      }
    }
    if (this.targets.length) {
      for (let fn of this.targets) {
        mainCode.push("");
        mainCode = mainCode.concat(fn.generateCode());
      }
    }
    mainCode.push("");
    mainCode = mainCode.concat("return " + this.target.generateCode());
    const code = mainCode.join("\n  ");
    if (this.isDebug) {
      const msg = `[Owl Debug]
${code}`;
      console.log(msg);
    }
    return code;
  }
  compileInNewTarget(prefix, ast, ctx, on) {
    const name = this.generateId(prefix);
    const initialTarget = this.target;
    const target = new CodeTarget(name, on);
    this.targets.push(target);
    this.target = target;
    this.compileAST(ast, createContext(ctx, { tModelSelected: void 0 }));
    this.target = initialTarget;
    return name;
  }
  addLine(line, idx) {
    this.target.addLine(line, idx);
  }
  define(varName, expr) {
    this.addLine(`const ${varName} = ${expr};`);
  }
  scopeMarker(from, itemVar, varName, names) {
    const marker = `${SCOPE_MARK}${this.scopeSites.length}`;
    this.scopeSites.push({ marker, target: this.target, from, itemVar, varName, names });
    return marker;
  }
  /**
   * A context made under another one made in the same render (a loop item)
   * costs V8 about 1.6 us and 1.2 KB: the item becomes a prototype. A loop
   * item no t-set writes holds only its loop's names, set when it is made:
   * a context made under it can be made under the item's own prototype with
   * a copy of those names instead, which no later write can make stale. That
   * holds while nothing else writes a context: an expression assigning a
   * variable (`t-on-click="v = 1"`, a bare-name `t-model.proxy`) turns it off
   * for the whole template.
   */
  resolveScopes() {
    const sites = this.scopeSites;
    if (!sites.length) {
      return;
    }
    const code = [
      ...this.staticDefs.map((d) => d.expr),
      ...[this.target, ...this.targets].flatMap((t) => t.code)
    ].join("\n");
    const writesContext = CONTEXT_WRITE.test(code);
    const copiable = (loop, target) => !writesContext && !target.writtenLevels.has(loop.level);
    const base = (loop, target) => loop.parent && copiable(loop.parent, target) ? base(loop.parent, target) : loop.parentVar;
    const ownNames = (loop, target) => {
      const names = loop.parent && copiable(loop.parent, target) ? ownNames(loop.parent, target) : [];
      return [.../* @__PURE__ */ new Set([...names, ...loop.names])];
    };
    const resolved = /* @__PURE__ */ new Map();
    for (const { marker, target, from, itemVar, varName, names } of sites) {
      let expr = `Object.create(${itemVar})`;
      if (copiable(from, target)) {
        expr = `Object.create(${base(from, target)})`;
        for (const name of ownNames(from, target)) {
          if (!names.includes(name)) {
            const key = JSON.stringify(name);
            expr += `; ${varName}[${key}] = ${itemVar}[${key}]`;
          }
        }
      }
      resolved.set(marker, expr);
    }
    for (const t of [this.target, ...this.targets]) {
      t.code = t.code.map(
        (line) => line.includes(SCOPE_MARK) ? line.replace(SCOPE_MARKER_RE, (m) => resolved.get(m)) : line
      );
    }
  }
  insertAnchor(block) {
    const tag = `block-child-${block.children.length}`;
    const anchor = xmlDoc.createElement(tag);
    block.insert(anchor);
  }
  createBlock(parentBlock, type) {
    const hasRoot = this.target.hasRoot;
    const block = new BlockDescription(this.nextBlockId++, this.target, type, this.generateId);
    if (!hasRoot) {
      this.target.hasRoot = true;
      block.isRoot = true;
    }
    if (parentBlock) {
      if (parentBlock.type === "block") {
        this.insertAnchor(parentBlock);
      }
      parentBlock.children.push(block);
      if (parentBlock.type === "list") {
        block.parentVar = `c_block${parentBlock.id}`;
      }
    }
    return block;
  }
  // a dom block or a list builds its own expression
  insertBlock(block, ctx, expression) {
    let blockExpr = block.generateExpr(expression);
    if (block.parentVar) {
      let key = this.target.currentKey(ctx);
      this.helpers.add("withKey");
      this.addLine(`${block.parentVar}[${ctx.index}] = withKey(${blockExpr}, ${key});`);
      return;
    }
    if (ctx.tKeyExpr) {
      blockExpr = `toggler(${ctx.tKeyExpr}, ${blockExpr})`;
    }
    if (block.isRoot && !this.target.deferReturn) {
      this.emitRootReturn(blockExpr);
    } else {
      this.define(block.varName, blockExpr);
    }
  }
  emitRootReturn(expr) {
    if (this.target.on) {
      expr = this.wrapWithEventCatcher(expr, this.target.on);
    }
    this.addLine(`return ${expr};`);
  }
  translate(str, translationCtx) {
    if (!str.trim()) {
      return str;
    }
    const match = translationRE.exec(str);
    return match[1] + this.translateFn(match[2], translationCtx) + match[3];
  }
  /**
   * @returns the newly created block name, if any
   */
  compileAST(ast, ctx) {
    switch (ast.type) {
      case ASTType.Text:
        return this.compileText(ast, ctx);
      case ASTType.DomNode:
        return this.compileTDomNode(ast, ctx);
      case ASTType.TOut:
        return this.compileTOut(ast, ctx);
      case ASTType.TIf:
        return this.compileTIf(ast, ctx);
      case ASTType.TForEach:
        return this.compileTForeach(ast, ctx);
      case ASTType.TKey:
        return this.compileTKey(ast, ctx);
      case ASTType.Multi:
        return this.compileMulti(ast, ctx);
      case ASTType.TCall:
        return this.compileTCall(ast, ctx);
      case ASTType.TCallBlock:
        return this.compileTCallBlock(ast, ctx);
      case ASTType.TSet:
        return this.compileTSet(ast, ctx);
      case ASTType.TComponent:
        return this.compileComponent(ast, ctx);
      case ASTType.TDebug:
        return this.compileDebug(ast, ctx);
      case ASTType.TLog:
        return this.compileLog(ast, ctx);
      case ASTType.TCallSlot:
        return this.compileTCallSlot(ast, ctx);
      case ASTType.TTranslation:
        return this.compileTTranslation(ast, ctx);
      case ASTType.TTranslationContext:
        return this.compileTTranslationContext(ast, ctx);
    }
  }
  // a t-debug, t-log, t-translation or t-translation-context renders what it
  // wraps, if anything
  compileContent(content, ctx) {
    return content ? this.compileAST(content, ctx) : null;
  }
  compileDebug(ast, ctx) {
    this.addLine(`debugger;`);
    return this.compileContent(ast.content, ctx);
  }
  compileLog(ast, ctx) {
    this.addLine(`console.log(${compileExpr(ast.expr)});`);
    return this.compileContent(ast.content, ctx);
  }
  compileText(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    let value = ast.value;
    if (value && ctx.translate !== false) {
      value = this.translate(value, ctx.translationCtx);
    }
    if (!ctx.inPreTag) {
      value = value.replace(whitespaceRE, " ");
    }
    if (!block || forceNewBlock) {
      block = this.createBlock(block, "text");
      this.insertBlock(block, ctx, `text(${toStringExpression(value)})`);
    } else {
      block.insert(xmlDoc.createTextNode(value));
    }
    return block.varName;
  }
  // the static code of a handler, a function of (context, event); its
  // modifiers are read from its key at run time, checked here
  generateHandlerCode(rawEvent, handler) {
    eventModifierMask(rawEvent);
    const { expr: compiled, arrow } = processExpr(handler);
    if (!compiled.trim()) {
      return "null";
    }
    let hoistedExpr;
    if (arrow) {
      const params = arrow.params ? `ctx,${arrow.params}` : "ctx";
      hoistedExpr = `${arrow.isAsync ? "async " : ""}(${params})=>${arrow.body}`;
    } else {
      this.helpers.add("callHandler");
      hoistedExpr = `(ctx, ev) => callHandler(${compiled}, ctx, ev)`;
    }
    return this.hoistHandler(hoistedExpr);
  }
  // handlers are static functions of (context, event): one per distinct code
  hoistHandler(expr) {
    let id = this.hoistedHandlers.get(expr);
    if (!id) {
      id = this.generateId("hdlr_fn");
      this.hoistedHandlers.set(expr, id);
      this.staticDefs.push({ id, expr });
    }
    return id;
  }
  compileTDomNode(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const isNewBlock = !block || forceNewBlock || ast.dynamicTag !== null || ast.ns;
    let codeIdx = this.target.code.length;
    if (isNewBlock) {
      block = this.createBlock(block, "block");
      this.blocks.push(block);
      if (ast.dynamicTag) {
        const tagExpr = this.generateId("tag");
        this.helpers.add("checkTagName");
        this.define(tagExpr, `checkTagName(${compileExpr(ast.dynamicTag)})`);
        block.dynamicTagName = tagExpr;
      }
    }
    const attrs = {};
    let valueVar = null;
    for (let key in ast.attrs) {
      let expr, attrName;
      if (key.startsWith("t-att")) {
        const isFormat = key.startsWith("t-attf");
        attrName = isFormat ? key.slice(7) : key === "t-att" ? null : key.slice(6);
        expr = isFormat ? interpolate(ast.attrs[key]) : compileExpr(ast.attrs[key]);
        if (!attrName) {
          this.helpers.add("attrsValue");
          expr = `attrsValue(${expr})`;
        } else if (!LITERAL_RE.test(expr)) {
          this.helpers.add("attrValue");
          expr = `attrValue(${expr})`;
        }
        if (attrName && isProp(ast.tag, attrName)) {
          if (attrName === "readonly") {
            attrName = "readOnly";
          }
          const idx = block.insertData(expr, "prop");
          attrs[`block-sync-property-${idx}`] = attrName;
          if (attrName === "value") {
            valueVar = block.data[idx];
          }
        } else {
          const idx = block.insertData(expr, "attr");
          if (key === "t-att") {
            attrs[`block-attributes`] = String(idx);
          } else {
            attrs[`block-attribute-${idx}`] = attrName;
          }
          if (attrName === "value") {
            valueVar = block.data[idx];
          }
        }
      } else if (ctx.translate && this.translatableAttributes.includes(key)) {
        const attrTranslationCtx = ast.attrsTranslationCtx?.[key] || ctx.translationCtx;
        attrs[key] = this.translate(ast.attrs[key], attrTranslationCtx);
      } else {
        expr = JSON.stringify(ast.attrs[key]);
        attrName = key;
        attrs[key] = ast.attrs[key];
      }
      if (attrName === "value" && ctx.tModelSelected) {
        const { expr: selected, number } = ctx.tModelSelected;
        const value = key.startsWith("t-att") ? valueVar : expr;
        const target = number ? `toNumber(${value})` : value;
        let selectedId = block.insertData(`${selected} === ${target}`, "attr");
        attrs[`block-attribute-${selectedId}`] = "selected";
      }
    }
    let tModelSelected;
    if (ast.model) {
      const {
        hasDynamicChildren,
        expr,
        eventType,
        shouldNumberize,
        shouldTrim,
        targetAttr,
        specialInitTargetAttr,
        isProxy
      } = ast.model;
      let readExpr;
      let modelId = null;
      let valueCode = `ev.target.${targetAttr}`;
      valueCode = shouldTrim ? `${valueCode}.trim()` : valueCode;
      if (shouldNumberize) {
        this.helpers.add("toNumber");
        valueCode = `toNumber(${valueCode})`;
      }
      let handlerId;
      if (isProxy) {
        readExpr = compileExpr(expr);
        handlerId = this.hoistHandler(`(ctx, ev) => { ${readExpr} = ${valueCode}; }`);
      } else {
        modelId = this.generateId("expr");
        this.helpers.add("modelExpr");
        this.define(modelId, `modelExpr(${compileExpr(expr)})`);
        readExpr = `${modelId}()`;
        handlerId = this.hoistHandler(`(ctx, ev, model) => model.set(${valueCode})`);
      }
      let idx;
      if (specialInitTargetAttr) {
        let targetExpr = targetAttr in attrs ? JSON.stringify(attrs[targetAttr]) : valueVar || "false";
        if (shouldNumberize) {
          targetExpr = `toNumber(${targetExpr})`;
        }
        idx = block.insertData(`${readExpr} === ${targetExpr}`, "prop");
        attrs[`block-property-${idx}`] = specialInitTargetAttr;
      } else if (hasDynamicChildren) {
        const bValueId = this.generateId("bValue");
        tModelSelected = { expr: bValueId, number: shouldNumberize };
        this.define(bValueId, readExpr);
      } else {
        idx = block.insertData(readExpr, "prop");
        attrs[`block-property-${idx}`] = targetAttr;
      }
      idx = block.insertHandler(handlerId);
      attrs[`block-handler-${idx}`] = eventType;
      if (modelId) {
        const argIdx = block.data.push(modelId) - 1;
        attrs[`block-handler-arg-${argIdx}`] = String(idx);
      }
    }
    for (let ev in ast.on) {
      const idx = block.insertHandler(this.generateHandlerCode(ev, ast.on[ev]));
      attrs[`block-handler-${idx}`] = ev;
    }
    if (ast.ref) {
      const refExpr = compileExpr(ast.ref);
      this.helpers.add("createRef");
      const setRefStr = `createRef(${refExpr}, node)`;
      const idx = block.insertData(setRefStr, "ref");
      attrs["block-ref"] = String(idx);
    }
    const nameSpace = ast.ns || ctx.nameSpace;
    const dom = nameSpace ? xmlDoc.createElementNS(nameSpace, ast.tag) : xmlDoc.createElement(ast.tag);
    for (const [attr, val] of Object.entries(attrs)) {
      if (!(attr === "class" && val === "")) {
        dom.setAttribute(attr, val);
      }
    }
    block.insert(dom);
    if (ast.content.length) {
      const initialDom = block.currentDom;
      block.currentDom = dom;
      const children = ast.content;
      for (let i = 0; i < children.length; i++) {
        const child = ast.content[i];
        const subCtx = createContext(ctx, {
          block,
          forceNewBlock: false,
          tKeyExpr: ctx.tKeyExpr,
          nameSpace,
          tModelSelected: tModelSelected || ctx.tModelSelected,
          inPreTag: ctx.inPreTag || ast.tag === "pre"
        });
        this.compileAST(child, subCtx);
      }
      block.currentDom = initialDom;
    }
    if (isNewBlock) {
      this.insertBlock(block, ctx);
      if (block.children.length && block.hasDynamicChildren) {
        this.hoistChildDeclarations(block, codeIdx);
      }
    }
    return block.varName;
  }
  hoistChildDeclarations(block, codeIdx) {
    const code = this.target.code;
    const children = block.children.slice();
    let current = children.shift();
    for (let i = codeIdx; current && i < code.length; i++) {
      if (code[i].trimStart().startsWith(`const ${current.varName} `)) {
        code[i] = code[i].replace(`const ${current.varName}`, current.varName);
        current = children.shift();
      }
    }
    this.addLine(`let ${block.children.map((c) => c.varName).join(", ")};`, codeIdx);
  }
  compileZero(ast, ctx) {
    this.helpers.add("zero");
    this.helpers.add("zeroCtx");
    const key = this.scopeKey(ctx);
    let defaultContent = `text("")`;
    if (ast.body) {
      const bodyAst = { type: ASTType.Multi, content: ast.body };
      const name = this.compileInNewTarget("defaultContent", bodyAst, ctx);
      defaultContent = `${name}.call(this, ctx, node, ${key})`;
    }
    return `ctx[zero] ? ctx[zero].call(this, ctx[zeroCtx], node, ${key}) : ${defaultContent}`;
  }
  compileTOut(ast, ctx) {
    let { block } = ctx;
    block = this.createBlock(block, "html");
    let blockStr;
    if (ast.expr === "0") {
      blockStr = this.compileZero(ast, ctx);
    } else {
      const site = this.siteId();
      const keyExpr = ctx.tKeyExpr ? `key + \`${KEY_MARK}k\${${ctx.tKeyExpr}}\`` : "key";
      const level = this.target.loopLevel;
      let keyArgs;
      if (level <= MAX_LAZY_LOOP_KEYS) {
        if (this.dev) {
          for (let i = 1; i <= level; i++) {
            this.target.stringKey(i);
          }
        }
        const loopKeys = Array.from({ length: level }, (_, i) => `, key${i + 1}`).join("");
        keyArgs = `node, ${keyExpr}, "${site}"${level ? `, ${level}${loopKeys}` : ""}`;
      } else {
        keyArgs = `node, ${this.scopeKey(ctx, site)}, ""`;
      }
      const expr = compileExpr(ast.expr);
      this.helpers.add("safeOutput");
      if (ast.body) {
        const bodyAst = { type: ASTType.Multi, content: ast.body };
        const name = this.compileInNewTarget("defaultContent", bodyAst, ctx);
        const key = this.scopeKey(ctx, site);
        const value = this.generateId("out");
        this.define(value, expr);
        blockStr = `${value} === undefined || ${value} === null ? toggler("default", ${name}.call(this, ctx, node, ${key})) : safeOutput(${value}, ${keyArgs})`;
      } else {
        blockStr = `safeOutput(${expr}, ${keyArgs})`;
      }
    }
    this.insertBlock(block, ctx, blockStr);
    return block.varName;
  }
  compileTIfBranch(content, block, ctx) {
    this.target.indentLevel++;
    this.compileAST(content, createContext(ctx, { block, index: ctx.index }));
    this.target.indentLevel--;
  }
  compileTIf(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const codeIdx = this.target.code.length;
    const isNewBlock = !block || block.type !== "multi" && forceNewBlock;
    if (block) {
      block.hasDynamicChildren = true;
    }
    block = isNewBlock ? this.createBlock(block, "multi") : block;
    this.addLine(`if (${compileExpr(ast.condition)}) {`);
    this.compileTIfBranch(ast.content, block, ctx);
    if (ast.tElif) {
      for (let clause of ast.tElif) {
        this.addLine(`} else if (${compileExpr(clause.condition)}) {`);
        this.compileTIfBranch(clause.content, block, ctx);
      }
    }
    if (ast.tElse) {
      this.addLine(`} else {`);
      this.compileTIfBranch(ast.tElse, block, ctx);
    }
    this.addLine("}");
    if (isNewBlock) {
      if (block.children.length) {
        this.hoistChildDeclarations(block, codeIdx);
      }
      const args = block.children.map((c) => c.varName).join(", ");
      this.insertBlock(block, ctx, `multi([${args}])`);
    }
    return block.varName;
  }
  compileTForeach(ast, ctx) {
    const block = ast.hasNoRepresentation ? null : this.createBlock(ctx.block, "list");
    const id = block ? block.id : this.generateId("_");
    let memo = null;
    if (ast.memo !== void 0 && block) {
      memo = this.generateId("memo");
      this.helpers.add("memoPrevious");
      this.helpers.add("memoKeep");
      this.helpers.add("memoHit");
      this.define(`${memo}_site`, this.scopeKey(ctx));
      this.define(`${memo}_previous`, `memoPrevious(node, ${memo}_site)`);
      this.define(`${memo}_next`, `new Map()`);
    }
    this.target.loopLevel++;
    const loopVar = `i${this.target.loopLevel}`;
    const ctxVar = this.generateId("ctx");
    this.addLine(`const ${ctxVar} = ctx;`);
    this.target.loopCtxVars.push(ctxVar);
    const vals = `v_block${id}`;
    const keys = `k_block${id}`;
    const l = `l_block${id}`;
    const lists = block ? [keys, vals, l, `c_block${id}`] : [keys, vals, l];
    this.helpers.add("prepareList");
    this.define(`[${lists.join(", ")}]`, `prepareList(${compileExpr(ast.collection)})`);
    if (this.dev) {
      this.define(`keys${id}`, `new Set()`);
    }
    this.addLine(`for (let ${loopVar} = 0; ${loopVar} < ${l}; ${loopVar}++) {`);
    this.target.indentLevel++;
    const suffixes = [""];
    if (!(ast.noFlags & ForEachNoFlag.First)) {
      suffixes.push("_first");
    }
    if (!(ast.noFlags & ForEachNoFlag.Last)) {
      suffixes.push("_last");
    }
    if (!(ast.noFlags & ForEachNoFlag.Index)) {
      suffixes.push("_index");
    }
    if (!(ast.noFlags & ForEachNoFlag.Value)) {
      suffixes.push("_value");
    }
    const parentLoop = this.target.loops[this.target.loops.length - 1] || null;
    const loopScope = {
      level: this.target.loopLevel,
      parentVar: ctxVar,
      names: suffixes.map((suffix) => ast.elem + suffix),
      parent: parentLoop
    };
    const itemExpr = parentLoop ? this.scopeMarker(parentLoop, ctxVar, "ctx", loopScope.names) : `Object.create(${ctxVar})`;
    this.addLine(`let ctx = ${itemExpr};`);
    this.target.loops.push(loopScope);
    const loopVarName = (suffix) => JSON.stringify(ast.elem + suffix);
    this.addLine(`ctx[${loopVarName("")}] = ${keys}[${loopVar}];`);
    if (!(ast.noFlags & ForEachNoFlag.First)) {
      this.addLine(`ctx[${loopVarName("_first")}] = ${loopVar} === 0;`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Last)) {
      this.addLine(`ctx[${loopVarName("_last")}] = ${loopVar} === ${keys}.length - 1;`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Index)) {
      this.addLine(`ctx[${loopVarName("_index")}] = ${loopVar};`);
    }
    if (!(ast.noFlags & ForEachNoFlag.Value)) {
      this.addLine(`ctx[${loopVarName("_value")}] = ${vals}[${loopVar}];`);
    }
    const level = this.target.loopLevel;
    this.define(`key${level}`, compileExpr(ast.key));
    const keyIdx = this.target.code.length;
    const subCtx = createContext(ctx, { block, index: loopVar });
    if (memo) {
      this.target.memoLevels.push(level);
    }
    this.compileAST(ast.body, subCtx);
    if (memo) {
      this.target.memoLevels.pop();
    }
    const keyLines = [];
    let uniqueKey = `key${level}`;
    if (this.target.stringKeyLevels.delete(level)) {
      this.helpers.add("keyOf");
      keyLines.push(`const skey${level} = keyOf(key${level});`);
      uniqueKey = `skey${level}`;
    }
    if (this.dev) {
      this.helpers.add("OwlError");
      keyLines.push(
        `if (keys${id}.has(${uniqueKey})) { throw new OwlError(\`Got duplicate key in t-foreach: \${key${level}}\`)}`,
        `keys${id}.add(${uniqueKey});`
      );
    }
    if (memo) {
      const vnodes = `c_block${id}`;
      const entry = (content) => `{ deps: deps${level}, vnodes: ${vnodes}, index: ${loopVar}, content: ${content} }`;
      keyLines.push(
        `const deps${level} = ${compileExpr(ast.memo)};`,
        `const hit${level} = memoHit(${memo}_previous, ${uniqueKey}, deps${level}, node);`,
        `if (hit${level} !== undefined) {`,
        `  ${vnodes}[${loopVar}] = hit${level}.vnodes[hit${level}.index];`,
        `  ${memo}_next.set(${uniqueKey}, ${entry(`hit${level}.content`)});`,
        `  continue;`,
        `}`
      );
      if (ast.memoContent) {
        this.helpers.add("memoBegin");
        this.helpers.add("memoEnd");
        keyLines.push(`const outer${level} = memoBegin();`);
        this.addLine(`${memo}_next.set(${uniqueKey}, ${entry(`memoEnd(outer${level})`)});`);
      } else {
        this.addLine(`${memo}_next.set(${uniqueKey}, ${entry("null")});`);
      }
    }
    keyLines.forEach((line, i) => this.addLine(line, keyIdx + i));
    this.target.indentLevel--;
    this.target.loopLevel--;
    this.target.loopCtxVars.pop();
    this.target.loops.pop();
    for (const [name, level2] of this.target.tSetVars) {
      if (level2 > this.target.loopLevel) {
        this.target.tSetVars.delete(name);
      }
    }
    this.addLine(`}`);
    if (memo) {
      this.addLine(`memoKeep(node, ${memo}_site, ${memo}_next);`);
    }
    if (!block) {
      return null;
    }
    this.insertBlock(block, ctx);
    return block.varName;
  }
  compileTKey(ast, ctx) {
    const tKeyExpr = this.generateId("tKey_");
    this.helpers.add("keyOf");
    this.define(tKeyExpr, `keyOf(${compileExpr(ast.expr)})`);
    ctx = createContext(ctx, {
      tKeyExpr,
      block: ctx.block,
      index: ctx.index
    });
    return this.compileAST(ast.content, ctx);
  }
  compileMulti(ast, ctx) {
    let { block, forceNewBlock } = ctx;
    const isNewBlock = !block || forceNewBlock;
    let codeIdx = this.target.code.length;
    if (isNewBlock) {
      const n = ast.content.filter((c) => !c.hasNoRepresentation).length;
      let result = null;
      if (n <= 1) {
        const shouldDefer = !this.target.hasRoot && n === 1 && ast.content[ast.content.length - 1].hasNoRepresentation;
        if (shouldDefer) {
          this.target.deferReturn = true;
        }
        for (let child of ast.content) {
          const blockName = this.compileAST(child, ctx);
          result = result || blockName;
        }
        if (shouldDefer) {
          this.target.deferReturn = false;
          this.emitRootReturn(result);
        }
        return result;
      }
      block = this.createBlock(block, "multi");
    }
    let index = 0;
    for (let i = 0, l = ast.content.length; i < l; i++) {
      const child = ast.content[i];
      const forceNewBlock2 = !child.hasNoRepresentation;
      const subCtx = createContext(ctx, {
        block,
        index,
        forceNewBlock: forceNewBlock2
      });
      this.compileAST(child, subCtx);
      if (forceNewBlock2) {
        index++;
      }
    }
    if (isNewBlock) {
      if (block.hasDynamicChildren && block.children.length) {
        this.hoistChildDeclarations(block, codeIdx);
      }
      const args = block.children.map((c) => c.varName).join(", ");
      this.insertBlock(block, ctx, `multi([${args}])`);
    }
    return block.varName;
  }
  compileTCall(ast, ctx) {
    let { block } = ctx;
    const attrs = ast.attrs ? this.propEntries(ast.attrs, ast.attrsTranslationCtx, ctx) : [];
    const isDynamic = isInterpolated(ast.name);
    const subTemplate = isDynamic ? interpolate(ast.name) : toStringExpression(ast.name);
    block = this.createBlock(block, "multi");
    const zero = [];
    if (ast.body) {
      const name = this.compileInNewTarget("callBody", ast.body, ctx);
      this.helpers.add("zero");
      this.helpers.add("zeroCtx");
      zero.push(["[zero]", name], ["[zeroCtx]", "ctx"]);
    } else if (!ast.context) {
      this.helpers.add("zero");
      zero.push(["[zero]", "null"]);
    }
    let ctxExpr;
    if (ast.context) {
      const dynCtxVar = this.generateId("ctx");
      this.addLine(`const ${dynCtxVar} = ${compileExpr(ast.context)};`);
      const entries = [
        `this: ${dynCtxVar}`,
        ...attrs.map(([name, value]) => `${propKey(name)}: ${value}`),
        ...zero.map(([key2, value]) => `${key2}: ${value}`)
      ];
      ctxExpr = `Object.assign({}, ${dynCtxVar}, {${entries.join(", ")}})`;
    } else if (!attrs.length && !ast.body) {
      this.helpers.add("withoutZero");
      ctxExpr = `ctx[zero] ? withoutZero(ctx) : ctx`;
    } else {
      ctxExpr = this.generateId("ctx");
      const loop = this.target.loops[this.target.loops.length - 1];
      this.define(
        ctxExpr,
        loop ? this.scopeMarker(loop, "ctx", ctxExpr, [...attrs.map(([name]) => name)]) : `Object.create(ctx)`
      );
      for (const [name, value] of attrs) {
        this.addLine(`${ctxExpr}[${JSON.stringify(name)}] = ${value};`);
      }
      for (const [key2, value] of zero) {
        this.addLine(`${ctxExpr}${key2} = ${value};`);
      }
    }
    const key = this.scopeKey(ctx);
    this.helpers.add("callTemplate");
    this.insertBlock(
      block,
      ctx,
      `callTemplate(${subTemplate}, this, app, ${ctxExpr}, node, ${key})`
    );
    return block.varName;
  }
  compileTCallBlock(ast, ctx) {
    let { block } = ctx;
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, compileExpr(ast.name));
    return block.varName;
  }
  compileTSet(ast, ctx) {
    let value;
    if (ast.body) {
      this.helpers.add("LazyValue");
      const bodyAst = { type: ASTType.Multi, content: ast.body };
      const name2 = this.compileInNewTarget("value", bodyAst, ctx);
      value = `new LazyValue(${name2}, ctx, this, node, ${this.scopeKey(ctx)})`;
    } else if (ast.defaultValue) {
      value = toStringExpression(
        ctx.translate ? this.translate(ast.defaultValue, ctx.translationCtx) : ast.defaultValue
      );
    } else {
      value = ast.value ? compileExpr(ast.value) : "null";
    }
    if (ast.value && (ast.body || ast.defaultValue)) {
      this.helpers.add("withDefault");
      value = `withDefault(${compileExpr(ast.value)}, ${value})`;
    }
    const name = JSON.stringify(ast.name);
    const level = this.target.loopLevel;
    const defLevel = this.target.tSetVars.get(ast.name);
    if (defLevel !== void 0 && level > defLevel) {
      if (this.target.memoLevels.some((memoLevel) => memoLevel > defLevel)) {
        throw new OwlError(
          `t-set="${ast.name}" inside a t-memo item writes a variable of an enclosing scope, and a memo hit would skip the write`
        );
      }
      this.addLine(`${this.target.loopCtxVars[defLevel]}[${name}] = ${value};`);
      this.target.writtenLevels.add(defLevel);
    } else {
      if (!level) {
        this.target.needsScopeProtection = true;
      }
      this.addLine(`ctx[${name}] = ${value};`);
      this.target.writtenLevels.add(level);
      this.target.tSetVars.set(ast.name, level);
    }
    return null;
  }
  // the key of a site's content: the t-key around it, the site's id, then
  // the key of each open loop, each a segment of its own (see keyOf in the
  // runtime): no loop key, t-key or id can spell another, so two sites, or
  // two items of a site, never share a key in their component's children
  scopeKey(ctx, site = this.siteId()) {
    let suffix = ctx.tKeyExpr ? `${KEY_MARK}k\${${ctx.tKeyExpr}}${site}` : site;
    for (let i = 1; i <= this.target.loopLevel; i++) {
      suffix += `${KEY_MARK}:\${${this.target.stringKey(i)}}`;
    }
    return `key + \`${suffix}\``;
  }
  // a keyed site's id, unique in the template, as written in the generated code
  siteId() {
    return this.generateId(KEY_MARK);
  }
  /**
   * Formats a prop name and value into a string suitable to be inserted in the
   * generated code. For example:
   *
   * Name              Value            Result
   * ---------------------------------------------------------
   * "number"          "state"          "number: ctx['state']"
   * "something"       ""               "something: undefined"
   * "some-prop"       "state"          "'some-prop': ctx['state']"
   * "onClick.bind"    "onClick"        "onClick: bind(ctx, ctx['onClick'])"
   */
  formatProp(name, value, attrsTranslationCtx, ctx) {
    const [key, code] = this.propEntry(name, value, attrsTranslationCtx, ctx);
    return `${propKey(key)}: ${code}`;
  }
  /**
   * The name a prop or t-call attribute `name` (suffix stripped) defines, and
   * the code of its value.
   */
  propEntry(name, value, attrsTranslationCtx, ctx) {
    if (name.endsWith(".translate")) {
      const attrTranslationCtx = attrsTranslationCtx?.[name] || ctx.translationCtx;
      value = toStringExpression(ctx.translate ? this.translate(value, attrTranslationCtx) : value);
    } else {
      value = compileExpr(value);
    }
    if (name.includes(".")) {
      let [_name, suffix] = name.split(".");
      name = _name;
      switch (suffix) {
        case "bind":
          value = `(${value}).bind(this)`;
          break;
        case "alike":
        case "translate":
          break;
        default:
          throw new OwlError(`Invalid prop suffix: ${suffix}`);
      }
    }
    return [name, value || "undefined"];
  }
  formatPropObject(obj, attrsTranslationCtx, ctx) {
    return this.propEntries(obj, attrsTranslationCtx, ctx).map(([k, v]) => `${propKey(k)}: ${v}`);
  }
  propEntries(obj, attrsTranslationCtx, ctx) {
    return Object.entries(obj).map(([k, v]) => this.propEntry(k, v, attrsTranslationCtx, ctx));
  }
  getPropString(props, dynProps) {
    const entries = dynProps ? [`...${compileExpr(dynProps)}`, ...props] : props;
    return `{${entries.join(",")}}`;
  }
  compileComponent(ast, ctx) {
    let { block } = ctx;
    const hasSlotsProp = "slots" in (ast.props || {});
    const props = [];
    const propList = [];
    const signalProps = [];
    for (let p in ast.props || {}) {
      let [name, suffix] = p.split(".");
      if (suffix === "signal") {
        props.push(`${propKey(name)}: ${compileExpr(ast.props[p]) || void 0}`);
        signalProps.push(JSON.stringify(name));
        continue;
      }
      if (suffix) {
        props.push(this.formatProp(p, ast.props[p], ast.propsTranslationCtx, ctx));
        continue;
      }
      const { expr: compiledValue, freeVariables } = processExpr(ast.props[p]);
      props.push(`${propKey(name)}: ${compiledValue || void 0}`);
      if (freeVariables) {
        for (const varName of freeVariables) {
          const syntheticKey = `${name}.${varName}`;
          propList.push(`"${syntheticKey}"`);
          props.push(`"${syntheticKey}": ctx['${varName}']`);
        }
      } else {
        propList.push(`"${name}"`);
      }
    }
    let slotDef = "";
    if (ast.slots) {
      let slotStr = [];
      for (let slotName in ast.slots) {
        const slotAst = ast.slots[slotName];
        const params = [];
        if (slotAst.content) {
          const name = this.compileInNewTarget("slot", slotAst.content, ctx, slotAst.on);
          params.push(`__render: ${name}, __ctx: ctx, __owner: this`);
        }
        const scope = ast.slots[slotName].scope;
        if (scope) {
          params.push(`__scope: ${JSON.stringify(scope)}`);
        }
        if (ast.slots[slotName].attrs) {
          params.push(
            ...this.formatPropObject(
              ast.slots[slotName].attrs,
              ast.slots[slotName].attrsTranslationCtx,
              ctx
            )
          );
        }
        const slotInfo = `{${params.join(", ")}}`;
        slotStr.push(`${JSON.stringify(slotName)}: ${slotInfo}`);
      }
      slotDef = `{${slotStr.join(", ")}}`;
    }
    if (slotDef && !(ast.dynamicProps || hasSlotsProp)) {
      props.push(`slots: ${slotDef}`);
    }
    let propString = this.getPropString(props, ast.dynamicProps);
    let propVar;
    if (slotDef && (ast.dynamicProps || hasSlotsProp) || this.dev) {
      propVar = this.generateId("props");
      this.define(propVar, propString);
      propString = propVar;
    }
    if (slotDef && (ast.dynamicProps || hasSlotsProp)) {
      this.addLine(`${propVar}.slots = Object.assign(${slotDef}, ${propVar}.slots);`);
    }
    let expr;
    if (ast.isDynamic) {
      expr = this.generateId("Comp");
      this.define(expr, compileExpr(ast.name));
    } else {
      expr = `\`${ast.name}\``;
    }
    const keyArg = this.scopeKey(ctx);
    let id = this.generateId("comp");
    this.helpers.add("createComponent");
    this.staticDefs.push({
      id,
      expr: `createComponent(app, ${ast.isDynamic ? null : expr}, ${!ast.isDynamic}, ${!!ast.slots}, ${!!ast.dynamicProps}, [${propList}]${signalProps.length ? `, [${signalProps}]` : ""})`
    });
    let blockExpr = `${id}(${propString}, ${keyArg}, node, this, ${ast.isDynamic ? expr : null})`;
    if (ast.isDynamic) {
      blockExpr = `toggler(${expr}, ${blockExpr})`;
    }
    if (ast.on) {
      blockExpr = this.wrapWithEventCatcher(blockExpr, ast.on);
    }
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, blockExpr);
    return block.varName;
  }
  // a catcher's handlers are static, given with its spec; a render gives it
  // their context
  wrapWithEventCatcher(expr, on) {
    this.helpers.add("createCatcher");
    let name = this.generateId("catcher");
    let spec = {};
    let handlers = [];
    for (let ev in on) {
      spec[ev] = handlers.push(this.generateHandlerCode(ev, on[ev])) - 1;
    }
    this.staticDefs.push({
      id: name,
      expr: `createCatcher(${JSON.stringify(spec)}, [${handlers.join(", ")}])`
    });
    return `${name}(${expr}, ctx)`;
  }
  compileTCallSlot(ast, ctx) {
    this.helpers.add("callSlot");
    let { block } = ctx;
    let blockString;
    let slotName;
    let dynamic = false;
    if (isInterpolated(ast.name)) {
      dynamic = true;
      slotName = interpolate(ast.name);
    } else {
      slotName = JSON.stringify(ast.name);
    }
    const key = this.scopeKey(ctx);
    const props = ast.attrs ? this.formatPropObject(ast.attrs, ast.attrsTranslationCtx, ctx) : [];
    const scope = props.length || ast.dynamicProps ? this.getPropString(props, ast.dynamicProps) : "null";
    if (ast.defaultContent) {
      const name = this.compileInNewTarget("defaultContent", ast.defaultContent, ctx);
      blockString = `callSlot(ctx, node, ${key}, ${slotName}, ${dynamic}, ${scope}, ${name}, this)`;
    } else {
      if (dynamic) {
        let name = this.generateId("slot");
        this.define(name, slotName);
        blockString = `toggler(${name}, callSlot(ctx, node, ${key}, ${name}, ${dynamic}, ${scope}))`;
      } else {
        blockString = `callSlot(ctx, node, ${key}, ${slotName}, ${dynamic}, ${scope})`;
      }
    }
    if (ast.on) {
      blockString = this.wrapWithEventCatcher(blockString, ast.on);
    }
    block = this.createBlock(block, "multi");
    this.insertBlock(block, ctx, blockString);
    return block.varName;
  }
  compileTTranslation(ast, ctx) {
    return this.compileContent(ast.content, { ...ctx, translate: false });
  }
  compileTTranslationContext(ast, ctx) {
    return this.compileContent(ast.content, { ...ctx, translationCtx: ast.translationCtx });
  }
};

// ../owl-compiler/src/index.ts
function compile(template, options = {
  hasGlobalValues: false
}) {
  const ast = parse(template, options.customDirectives);
  const codeGenerator = new CodeGenerator(ast, options);
  const code = codeGenerator.generateCode();
  try {
    return new Function("app, bdom, helpers", code);
  } catch (originalError) {
    const { name } = options;
    const nameStr = name ? `template "${name}"` : "anonymous template";
    const err = new OwlError(
      `Failed to compile ${nameStr}: ${originalError.message}

generated code:
function(app, bdom, helpers) {
${code}
}`
    );
    err.cause = originalError;
    throw err;
  }
}

// ../owl-runtime/src/version.ts
var version = "3.0.0-alpha.49";

// ../owl-runtime/src/build_info.ts
var buildHash = "33bb67f1";

// src/compiler.ts
var registry = globalThis[/* @__PURE__ */ Symbol.for("@odoo/owl/compiler")] ||= /* @__PURE__ */ Object.create(null);
registry[`${version}+${buildHash}`] = { compile, parseXML, version, hash: buildHash, OwlError };
export {
  compile,
  parseXML
};
