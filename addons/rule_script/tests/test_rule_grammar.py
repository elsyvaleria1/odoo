import datetime

from odoo.tests import BaseCase, tagged

from ..tools.grammar import RuleSyntaxError, parse_rule
from ..tools.runtime import RuleContext, RuleRuntimeError, compile_rule, run_rule

HEADER = "RULE = 'x.rule'\nVALID_FROM = '2026-01-01'\nINPUTS = {'n': 'number', 'd': 'date'}\nOUTPUT = 'any'\n"


def rule(body):
    return (
        HEADER
        + "def evaluate(inputs, rules):\n"
        + "".join(f"    {line}\n" for line in body.splitlines())
    )


@tagged("at_install")
class TestRuleGrammar(BaseCase):
    def _run(self, source, **inputs):
        header, module = parse_rule(source)
        context = RuleContext(datetime.date(2026, 1, 1), None)
        return run_rule(
            compile_rule(module, "<test>"),
            header,
            {"n": 1, "d": "2026-03-31", **inputs},
            context,
        )

    def test_a_rule_reads_inputs_constants_and_helpers(self):
        source = "RATES = ((1000.0, 0.1), (None, 0.2))\n" + rule(
            "for _ in range(1):\n"
            "    pass\n"
            "for limit, rate in RATES:\n"
            "    if limit is None or inputs.n <= limit:\n"
            "        return {'tax': rules.round_half_up(inputs.n * rate, 2),"
            " 'next': rules.add_months(inputs.d, 1), 'year': inputs.d.year}"
        )

        self.assertEqual(
            self._run(source, n=1234.5),
            {"tax": 246.9, "next": datetime.date(2026, 4, 30), "year": 2026},
        )

    def test_the_grammar_refuses_what_could_escape_or_not_end(self):
        refused = {
            "dunder attribute": rule("return (1).__class__"),
            "private attribute": rule("return rules._resolve"),
            "throwaway read": rule("for _ in range(1):\n    pass\nreturn _"),
            "while": rule("while True:\n    pass"),
            "lambda": rule("return sorted([1], key=lambda x: x)"),
            "unknown call": rule("return getattr(rules, 'call')"),
            "f-string": rule("return f'{inputs.n}'"),
            "variable exponent": rule("return 2 ** inputs.n"),
            "reassigned builtin": rule("len = 1\nreturn len"),
            "dynamic rule call": rule("return rules.call(inputs.d)"),
            "self call": rule("return rules.call('x.rule')"),
            "keyword not allowed": rule("return round(inputs.n, ndigits=2)"),
            "bare expression": rule("rules.call('y')\nreturn 1"),
            "import": "import os\n" + rule("return 1"),
            "second function": rule("return 1")
            + "def other(inputs, rules):\n    return 2\n",
            "lowercase constant": "rate = 1\n" + rule("return 1"),
            "missing header": "RULE = 'x'\ndef evaluate(inputs, rules):\n    return 1\n",
            "bound method as key": rule("return sorted([1], key=inputs.d.replace)"),
            "format method as key": rule("return sorted([1], key='{0}'.format)"),
            "callable from a subscript as key": rule(
                "f = {'f': len}\nreturn sorted([1], key=f['f'])"
            ),
            "augmented variable exponent": rule("x = 2\nx **= inputs.n\nreturn x"),
        }
        for label, source in refused.items():
            with self.subTest(label), self.assertRaises(RuleSyntaxError):
                parse_rule(source)

    def test_the_runtime_refuses_methods_and_unbounded_sizes(self):
        refused = {
            "huge range": rule("return [x for x in range(10 ** 9)]"),
            "huge repetition": rule("return 'x' * 10 ** 9"),
            "nested loops": rule(
                "t = 0\nfor a in range(10000):\n    for b in range(10000):\n"
                "        t += 1\nreturn t"
            ),
            "nested comprehension": rule(
                "return sum(1 for a in range(10000) for b in range(10000))"
            ),
            "chained power": rule("x = 10\nx = x ** 64\nx = x ** 64\nreturn x"),
            "augmented power": rule(
                "x = 10\nfor _ in range(5):\n    x **= 64\nreturn x"
            ),
            "squared integer": rule(
                "x = 2 ** 64\nfor _ in range(100):\n    x = x * x\nreturn x"
            ),
            "augmented repetition": rule(
                "x = 'ab'\nfor _ in range(30):\n    x *= 2\nreturn x"
            ),
        }
        for label, source in refused.items():
            with self.subTest(label), self.assertRaises(RuleRuntimeError):
                self._run(source)

    def test_inputs_are_checked_against_the_signature(self):
        source = rule("return inputs.n")
        with self.assertRaises(TypeError):
            self._run(source, n="1")
        with self.assertRaises(TypeError):
            self._run(source, extra=1)
