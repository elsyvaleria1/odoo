// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { evaluateExpr, parseExpr } from "@web/core/py_js/py";
import { formatAST, toPyValue } from "@web/core/py_js/py_utils";

describe.current.tags("headless");

describe("py_js answers only what safe_eval answers", () => {
    test("a name is looked up on BUILTINS itself, not on Object.prototype", () => {
        for (const name of [
            "__proto__",
            "constructor",
            "valueOf",
            "toString",
            "hasOwnProperty",
            "isPrototypeOf",
            "propertyIsEnumerable",
            "toLocaleString",
        ]) {
            expect(() => evaluateExpr(name)).toThrow(
                new RegExp(`'${name}' is not defined`),
            );
        }
        expect(evaluateExpr("bool(1)")).toBe(true);
        expect(typeof evaluateExpr("today")).toBe("string");
    });

    test("a missing dict key raises KeyError", () => {
        expect(() => evaluateExpr("{'a': 1}['b']")).toThrow(/KeyError: 'b'/);
        expect(() => evaluateExpr("{'a': 1}['b'] == None")).toThrow(/KeyError: 'b'/);
        expect(evaluateExpr("{'a': 1}['a']")).toBe(1);
        expect(evaluateExpr("{'a': 1}.get('b')")).toBe(null);
        expect(evaluateExpr("{'a': 1}.get('b', 7)")).toBe(7);
    });

    test("an out-of-range index raises IndexError", () => {
        expect(() => evaluateExpr("[1, 2, 3][9]")).toThrow(/IndexError/);
        expect(() => evaluateExpr("[1, 2, 3][-9]")).toThrow(/IndexError/);
        expect(() => evaluateExpr("'abc'[9]")).toThrow(/IndexError/);
        expect(() => evaluateExpr("[1, 2, 3]['x']")).toThrow(
            /indices must be integers/,
        );
        expect(evaluateExpr("[1, 2, 3][0]")).toBe(1);
        expect(evaluateExpr("[1, 2, 3][-1]")).toBe(3);
        expect(evaluateExpr("'abc'[-1]")).toBe("c");
    });

    test("surplus arguments and unknown keywords are rejected", () => {
        expect(() => evaluateExpr("'abc'.strip('a', 'b')")).toThrow(
            /at most 1 argument/,
        );
        expect(() => evaluateExpr("'abc'.strip(bogus=1)")).toThrow(
            /unexpected keyword argument 'bogus'/,
        );
        expect(() => evaluateExpr("'abc'.strip('a', chars='b')")).toThrow(
            /multiple values for argument 'chars'/,
        );
        expect(evaluateExpr("'abc'.strip('a')")).toBe("bc");
        expect(evaluateExpr("'abc'.strip(chars='a')")).toBe("bc");
        expect(evaluateExpr("'a,b'.split(',', 1)")).toEqual(["a", "b"]);
    });

    test("replace() validates count before honouring a negative one", () => {
        expect(() => evaluateExpr("'aaa'.replace('a', 'b', -1.5)")).toThrow(
            /count must be an integer/,
        );
        expect(evaluateExpr("'aaa'.replace('a', 'b', -1)")).toBe("bbb");
        expect(evaluateExpr("'aaa'.replace('a', 'b', 2)")).toBe("bba");
        expect(evaluateExpr("'aaa'.replace('a', 'b')")).toBe("bbb");
    });

    test("title() capitalises non-ASCII letters", () => {
        expect(evaluateExpr("'éa'.title()")).toBe("Éa");
        expect(evaluateExpr("'ñandú test'.title()")).toBe("Ñandú Test");
        expect(evaluateExpr("'hello world-foo 2x'.title()")).toBe("Hello World-Foo 2X");
        expect(evaluateExpr('"it\'s a test".title()')).toBe("It'S A Test");
    });

    test("len() answers for sized values only", () => {
        expect(() => evaluateExpr("len(datetime.date(2020, 1, 1))")).toThrow(
            /has no len\(\)/,
        );
        expect(() => evaluateExpr("len(1)")).toThrow(/has no len\(\)/);
        expect(evaluateExpr("len({'a': 1, 'b': 2})")).toBe(2);
        expect(evaluateExpr("len([1, 2, 3])")).toBe(3);
        expect(evaluateExpr("len('abc')")).toBe(3);
        expect(evaluateExpr("len(set([1, 2]))")).toBe(2);
    });
});

describe("chained comparisons", () => {
    test("the middle operand is evaluated exactly once", () => {
        let reads = 0;
        const context = {
            get b() {
                reads++;
                return 2;
            },
        };
        expect(evaluateExpr("1 < b < 3", context)).toBe(true);
        expect(reads).toBe(1);
    });

    test("evaluation short-circuits on the first false comparison", () => {
        let reads = 0;
        const context = {
            get tail() {
                reads++;
                return 5;
            },
        };
        expect(evaluateExpr("1 < 0 < tail", context)).toBe(false);
        expect(reads).toBe(0);
    });

    test("results match CPython", () => {
        expect(evaluateExpr("1 < 2 < 3")).toBe(true);
        expect(evaluateExpr("1 < 3 < 2")).toBe(false);
        expect(evaluateExpr("3 < 2 < 1")).toBe(false);
        expect(evaluateExpr("1 < 2 <= 2 < 3")).toBe(true);
        expect(evaluateExpr("1 == 1 == 1")).toBe(true);
        expect(evaluateExpr("1 == 1 == 2")).toBe(false);
        expect(evaluateExpr("1 in [1, 2] and 2 not in [1]")).toBe(true);
        expect(evaluateExpr("'a' < 'b' < 'c'")).toBe(true);
    });

    test("the expression survives a round trip through formatAST", () => {
        for (const expr of ["1 < 2 < 3", "a < b <= c", "a == b != c"]) {
            expect(formatAST(parseExpr(expr))).toBe(expr);
        }
        expect(formatAST(parseExpr("(1 < 2 < 3) and x"))).toBe("1 < 2 < 3 and x");
    });

    test("a lone `not` cannot continue a chain", () => {
        expect(() => parseExpr("1 < 2 not 3")).toThrow();
    });
});

describe("the AST cache hands out immutable trees", () => {
    test("a cached AST is deeply frozen", () => {
        const ast = /** @type {any} */ (parseExpr("[('a', '=', 1)]"));
        expect(Object.isFrozen(ast)).toBe(true);
        expect(Object.isFrozen(ast.value)).toBe(true);
        expect(Object.isFrozen(ast.value[0])).toBe(true);
        expect(Object.isFrozen(ast.value[0].value[0])).toBe(true);
    });

    test("the same expression yields the same object, and writing to it throws", () => {
        const ast = /** @type {any} */ (parseExpr("a + 1"));
        expect(parseExpr("a + 1")).toBe(/** @type {any} */ (ast));
        expect(() => {
            ast.op = "-";
        }).toThrow(/read only|not extensible/);
    });
});

describe("py_js refuses arguments CPython refuses", () => {
    test("the no-argument str methods take no arguments", () => {
        for (const method of ["lower", "upper", "capitalize", "title"]) {
            expect(evaluateExpr(`'aBc'.${method}()`)).toBeOfType("string");
            expect(() => evaluateExpr(`'aBc'.${method}(1)`)).toThrow();
            expect(() => evaluateExpr(`'aBc'.${method}('x')`)).toThrow();
            expect(() => evaluateExpr(`'aBc'.${method}(nope=1)`)).toThrow();
        }
    });

    test("the no-argument str methods still answer correctly", () => {
        expect(evaluateExpr("'aBc'.lower()")).toBe("abc");
        expect(evaluateExpr("'aBc'.upper()")).toBe("ABC");
        expect(evaluateExpr("'aBc dEf'.capitalize()")).toBe("Abc def");
        expect(evaluateExpr("'aBc dEf'.title()")).toBe("Abc Def");
    });

    test("methods that do take arguments still bind them", () => {
        expect(evaluateExpr("'a,b'.split(',')")).toEqual(["a", "b"]);
        expect(evaluateExpr("' a '.strip()")).toBe("a");
        expect(evaluateExpr("'abc'.startswith(('x', 'a'))")).toBe(true);
        expect(evaluateExpr("{'a': 1}.get('x', {'b': 2})")).toEqual({ b: 2 });
    });
});

describe("py_js compares sets the way CPython compares them", () => {
    test("set equality is a bijection, not a per-member lookup", () => {
        expect(evaluateExpr("set([1, True]) == set([1, 2])")).toBe(false);
        expect(evaluateExpr("set([1, True]) != set([1, 2])")).toBe(true);
        expect(evaluateExpr("set([1]) == set([True])")).toBe(true);
        expect(evaluateExpr("set([1, 2]) == set([2, 1])")).toBe(true);
        expect(evaluateExpr("set([1, 2]) == set([1, 3])")).toBe(false);
        expect(evaluateExpr("set([]) == set([])")).toBe(true);
        expect(evaluateExpr("set([1]) == [1]")).toBe(false);
    });

    test("<, <=, > and >= over sets are inclusion, not an ordering", () => {
        expect(evaluateExpr("set([1]) < set([1, 2])")).toBe(true);
        expect(evaluateExpr("set([1, 2]) < set([1])")).toBe(false);
        expect(evaluateExpr("set([1]) < set([1])")).toBe(false);
        expect(evaluateExpr("set([1]) <= set([1])")).toBe(true);
        expect(evaluateExpr("set([1]) <= set([1, 2])")).toBe(true);
        expect(evaluateExpr("set([1, 2]) > set([1])")).toBe(true);
        expect(evaluateExpr("set([1, 2]) >= set([1, 2])")).toBe(true);
        expect(evaluateExpr("set([1]) >= set([1, 2])")).toBe(false);
        expect(evaluateExpr("set([1]) < set([2])")).toBe(false);
        expect(evaluateExpr("set([2]) < set([1])")).toBe(false);
    });

    test("ordering a set against a non-set raises rather than answering", () => {
        expect(() => evaluateExpr("set([1]) < 2")).toThrow(
            /'<' not supported between instances of 'set' and 'int'/,
        );
        expect(() => evaluateExpr("set([1]) > 2")).toThrow(
            /'>' not supported between instances of 'set' and 'int'/,
        );
    });

    test("the operator and the operand ORDER in the message are CPython's", () => {
        expect(() => evaluateExpr("2 > set([1])")).toThrow(
            /'>' not supported between instances of 'int' and 'set'/,
        );
        expect(() => evaluateExpr("2 < set([1])")).toThrow(
            /'<' not supported between instances of 'int' and 'set'/,
        );
        expect(() =>
            evaluateExpr("datetime.date(2024, 1, 1) > datetime.datetime(2024, 1, 1)"),
        ).toThrow(/'>' not supported between instances of 'date' and 'datetime'/);
        expect(() =>
            evaluateExpr("datetime.datetime(2024, 1, 1) < datetime.date(2024, 1, 1)"),
        ).toThrow(/'<' not supported between instances of 'datetime' and 'date'/);
    });
});

describe("unary + answers an int for a bool, as CPython's does", () => {
    test("+True is 1 and +False is 0, not the bool itself", () => {
        expect(evaluateExpr("+True")).toBe(1);
        expect(evaluateExpr("+False")).toBe(0);
        expect(evaluateExpr("str(+(not D))", { D: { k: 7 } })).toBe("0");
        expect(evaluateExpr("repr([+True, -True])")).toBe("[1, -1]");
        expect(evaluateExpr("+2.5")).toBe(2.5);
    });
});

describe("ordering an unorderable pair raises TypeError, as CPython does", () => {
    test("None orders against nothing, not even None", () => {
        expect(() => evaluateExpr("None < 1")).toThrow(
            /'<' not supported between instances of 'NoneType' and 'int'/,
        );
        expect(() => evaluateExpr("1 > None")).toThrow(
            /'>' not supported between instances of 'int' and 'NoneType'/,
        );
        expect(() => evaluateExpr("None <= None")).toThrow(
            /'<=' not supported between instances of 'NoneType' and 'NoneType'/,
        );
        expect(() => evaluateExpr("x >= 0", { x: null })).toThrow(
            /'>=' not supported between instances of 'NoneType' and 'int'/,
        );
        expect(() => evaluateExpr("False < None")).toThrow(
            /'<' not supported between instances of 'bool' and 'NoneType'/,
        );
    });

    test("str against a number, and containers against other kinds", () => {
        expect(() => evaluateExpr("'a' < 1")).toThrow(
            /'<' not supported between instances of 'str' and 'int'/,
        );
        expect(() => evaluateExpr("1 >= 'a'")).toThrow(
            /'>=' not supported between instances of 'int' and 'str'/,
        );
        expect(() => evaluateExpr("[1] < 1")).toThrow(
            /'<' not supported between instances of 'list' and 'int'/,
        );
        expect(() => evaluateExpr("[1] < (1,)")).toThrow(
            /'<' not supported between instances of 'list' and 'tuple'/,
        );
        expect(() => evaluateExpr("{} <= {}")).toThrow(
            /'<=' not supported between instances of 'dict' and 'dict'/,
        );
        expect(() => evaluateExpr("x > 0", { x: [1] })).toThrow(
            /'>' not supported between instances of 'list' and 'int'/,
        );
        expect(() => evaluateExpr("datetime.date(2020, 1, 1) < '2020-01-02'")).toThrow(
            /'<' not supported between instances of 'date' and 'str'/,
        );
        expect(() => evaluateExpr("datetime.timedelta(1) < 1")).toThrow(
            /'<' not supported between instances of 'timedelta' and 'int'/,
        );
    });

    test("a sequence names the first unequal elements, and equal elements never order", () => {
        expect(() => evaluateExpr("[None] < [1]")).toThrow(
            /'<' not supported between instances of 'NoneType' and 'int'/,
        );
        expect(() => evaluateExpr("(1, 2) > (1, 'a')")).toThrow(
            /'>' not supported between instances of 'int' and 'str'/,
        );
        expect(evaluateExpr("[1, None] <= [1, None]")).toBe(true);
        expect(evaluateExpr("[1, None] < [1, None]")).toBe(false);
        expect(evaluateExpr("(1, 'a') < (2, None)")).toBe(true);
    });

    test("a chain raises at the first unorderable link it reaches", () => {
        expect(() => evaluateExpr("1 < 2 < 'a'")).toThrow(
            /'<' not supported between instances of 'int' and 'str'/,
        );
        expect(evaluateExpr("1 > 2 < 'a'")).toBe(false);
    });

    test("max, min and sorted raise with CPython's operator", () => {
        expect(() => evaluateExpr("max(1, 'a')")).toThrow(
            /'>' not supported between instances of 'str' and 'int'/,
        );
        expect(() => evaluateExpr("min(None, 1)")).toThrow(
            /'<' not supported between instances of 'int' and 'NoneType'/,
        );
        expect(() => evaluateExpr("sorted([1, None])")).toThrow(
            /'<' not supported between instances of/,
        );
        expect(evaluateExpr("max(True, 0.5)")).toBe(true);
    });

    test("an unset field (False) still orders before a string, as views rely on", () => {
        const today = "2020-01-01";
        expect(
            evaluateExpr("date_deadline < current", {
                date_deadline: false,
                current: today,
            }),
        ).toBe(true);
        expect(
            evaluateExpr("date_deadline > current", {
                date_deadline: false,
                current: today,
            }),
        ).toBe(false);
        expect(
            evaluateExpr("date_deadline <= current", {
                date_deadline: false,
                current: today,
            }),
        ).toBe(true);
        expect(
            evaluateExpr("current >= date_deadline", {
                date_deadline: false,
                current: today,
            }),
        ).toBe(true);
        expect(evaluateExpr("x > 0", { x: false })).toBe(false);
        expect(evaluateExpr("0 < True")).toBe(true);
    });

    test("str ordering is by code point, not by UTF-16 unit", () => {
        expect(evaluateExpr("'\\uffff' < '\\U0001F600'")).toBe(true);
        expect(evaluateExpr("max('\\uffff', '\\U0001F600')")).toBe("\u{1F600}");
        expect(evaluateExpr("sorted(['\\U0001F600', '\\uffff'])")).toEqual([
            "\uffff",
            "\u{1F600}",
        ]);
    });
});

describe("list, tuple and dict are builtins, as in safe_eval", () => {
    test("list() and tuple() build from any iterable", () => {
        expect(evaluateExpr("list()")).toEqual([]);
        expect(evaluateExpr("list('ab')")).toEqual(["a", "b"]);
        expect(evaluateExpr("list((1, 2))")).toEqual([1, 2]);
        expect(evaluateExpr("list({'a': 1, 'b': 2})")).toEqual(["a", "b"]);
        expect(evaluateExpr("list(set([3]))")).toEqual([3]);
        expect(evaluateExpr("list({1: 'a'})")).toEqual([1]);
        expect(evaluateExpr("repr(tuple([1]))")).toBe("(1,)");
        expect(evaluateExpr("tuple(L) + (3,) == (1, 2, 3)", { L: [1, 2] })).toBe(true);
        expect(evaluateExpr("tuple('ab') == ('a', 'b')")).toBe(true);
        expect(evaluateExpr("list((1,)) == [1]")).toBe(true);
    });

    test("list() and tuple() reject what CPython rejects", () => {
        expect(() => evaluateExpr("list(1)")).toThrow(/'int' object is not iterable/);
        expect(() => evaluateExpr("tuple(None)")).toThrow(
            /'NoneType' object is not iterable/,
        );
        expect(() => evaluateExpr("list(1, 2)")).toThrow(
            /list expected at most 1 argument, got 2/,
        );
        expect(() => evaluateExpr("tuple(x=1)")).toThrow(
            /tuple\(\) takes no keyword arguments/,
        );
    });

    test("dict() copies a mapping, reads pairs and takes keywords", () => {
        expect(evaluateExpr("dict()")).toEqual({});
        expect(evaluateExpr("dict(a=1)")).toEqual({ a: 1 });
        expect(evaluateExpr("dict(context, b=2)", { context: { a: 1 } })).toEqual({
            a: 1,
            b: 2,
        });
        expect(evaluateExpr("dict([('a', 1), ['b', 2]])")).toEqual({ a: 1, b: 2 });
        expect(evaluateExpr("dict(['ab'])")).toEqual({ a: "b" });
        expect(evaluateExpr("dict(a=1).get('b', 3)")).toBe(3);
        expect(evaluateExpr("repr(dict([(1, 'a')]))")).toBe("{1: 'a'}");
        expect(() => evaluateExpr("dict(a=1).a")).toThrow(
            /AttributeError: 'dict' object has no attribute 'a'/,
        );
    });

    test("dict() rejects what CPython rejects", () => {
        expect(() => evaluateExpr("dict([('a', 1, 2)])")).toThrow(
            /dictionary update sequence element #0 has length 3; 2 is required/,
        );
        expect(() => evaluateExpr("dict([1])")).toThrow(
            /cannot convert dictionary update sequence element #0 to a sequence/,
        );
        expect(() => evaluateExpr("dict(1)")).toThrow(/'int' object is not iterable/);
        expect(() => evaluateExpr("dict({}, {})")).toThrow(
            /dict expected at most 1 argument, got 2/,
        );
    });

    test("type is not a builtin, as safe_eval has none", () => {
        expect(() => evaluateExpr("type(1)")).toThrow(/Name 'type' is not defined/);
    });
});

describe("a number dict key stays a number", () => {
    test("repr and str print it unquoted", () => {
        expect(evaluateExpr("repr({1: 'a'})")).toBe("{1: 'a'}");
        expect(evaluateExpr("str({1: 'a', 'b': 2})")).toBe("{1: 'a', 'b': 2}");
        expect(evaluateExpr("repr({1.5: 'x'})")).toBe("{1.5: 'x'}");
        expect(evaluateExpr("repr({'1': 'a'})")).toBe("{'1': 'a'}");
        expect(evaluateExpr("'%s' % ({'k': {2: 3}},)")).toBe("{'k': {2: 3}}");
        expect(evaluateExpr("{1: 'a'}[1]")).toBe("a");
    });

    test("formatAST prints it unquoted, and the result reparses to the same dict", () => {
        expect(formatAST(parseExpr("{1: 'a', 'b': 2}"))).toBe('{1: "a", "b": 2}');
        expect(formatAST(parseExpr("{'1': 'a'}"))).toBe('{"1": "a"}');
        expect(formatAST(parseExpr("{1: 'a', '1': 'b'}"))).toBe('{"1": "b"}');
        const src = "{2: [1, {3: 4}]}";
        expect(parseExpr(formatAST(parseExpr(src)))).toEqual(parseExpr(src));
    });
});

describe("`in` against a non-container raises, except an unset field", () => {
    test("a value that is no container raises TypeError, as CPython does", () => {
        expect(() => evaluateExpr("'x' in None")).toThrow(
            /TypeError: argument of type 'NoneType' is not a container or iterable/,
        );
        expect(() => evaluateExpr("x in context.get('missing')", { x: "a" })).toThrow(
            /argument of type 'NoneType'/,
        );
        expect(() => evaluateExpr("1 in 5")).toThrow(/argument of type 'int'/);
        expect(() => evaluateExpr("False in True")).toThrow(/argument of type 'bool'/);
        expect(() => evaluateExpr("1 in 'abc'")).toThrow(
            /'in <string>' requires string as left operand, not int/,
        );
        expect(() => evaluateExpr("[1] in {'a': 1}")).toThrow(
            /cannot use 'list' as a dict key \(unhashable type: 'list'\)/,
        );
    });

    test("an unset field (False) is in nothing and contains nothing, as views rely on", () => {
        const unset = {
            fiscal_country_codes: false,
            state: false,
            parent: { move_type: false },
        };
        expect(evaluateExpr("'UZ' not in fiscal_country_codes", unset)).toBe(true);
        expect(evaluateExpr("'UZ' in fiscal_country_codes", unset)).toBe(false);
        expect(evaluateExpr("state in ('draft')", unset)).toBe(false);
        expect(evaluateExpr("state not in 'draft'", unset)).toBe(true);
        expect(evaluateExpr("'in_' in parent.move_type", unset)).toBe(false);
        expect(evaluateExpr("'in_' in parent.move_type", { parent: {} })).toBe(false);
        expect(
            evaluateExpr("'UZ' in fiscal_country_codes", {
                fiscal_country_codes: "UZ,KZ",
            }),
        ).toBe(true);
    });
});

describe("a dict keeps its insertion order", () => {
    test("formatAST keeps integer-like keys where they were written", () => {
        expect(formatAST(parseExpr("{'b': 1, '10': 2, '9': 3}"))).toBe(
            '{"b": 1, "10": 2, "9": 3}',
        );
        expect(formatAST(parseExpr("{10: 'a', 'b': 1, 9: 'c'}"))).toBe(
            '{10: "a", "b": 1, 9: "c"}',
        );
        const src = "{'z': 1, '3': [{'b': 1, '0': 2}]}";
        expect(parseExpr(formatAST(parseExpr(src)))).toEqual(parseExpr(src));
    });

    test("toPyValue of an evaluated dict keeps its order and its number keys", () => {
        const dict = evaluateExpr("{'b': 1, 10: 2, '9': 3}");
        expect(formatAST(toPyValue(dict))).toBe('{"b": 1, 10: 2, "9": 3}');
    });

    test("the evaluated dict stays a plain object for its consumers", () => {
        const dict = evaluateExpr("{'b': 1, '10': 2}");
        expect(Object.getPrototypeOf(dict)).toBe(Object.prototype);
        expect(dict).toEqual({ b: 1, 10: 2 });
    });

    test("a unary number key parses, as CPython folds it", () => {
        expect(formatAST(parseExpr("{-1: 'a'}"))).toBe('{-1: "a"}');
        expect(formatAST(parseExpr("{~1: 'a', +2: 'b'}"))).toBe('{-2: "a", 2: "b"}');
        expect(() => parseExpr("{-'a': 1}")).toThrow(/parsing error/);
    });
});
