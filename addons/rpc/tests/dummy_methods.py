from odoo import api, models
from odoo.api import Self


class DummyMethods:
    def one_arg(self, a: int) -> int:
        return a

    one_arg.expected = {
        "signature": "(a) -> int",
        "parameters": {
            "a": {"annotation": "int", "doc": "<p>an int.</p>"},
        },
        "return": {"annotation": "int", "doc": "<p>an int.</p>"},
        "doc": """
        <div class="document">
        <p>A simple dummy identity function.</p>
        </div>""",
    }

    def multiple_args_and_error(
        self, a: int, b: list[int], c: dict[str, list[str]]
    ) -> int:
        return a

    multiple_args_and_error.expected = {
        "signature": "(a, b, c) -> int",
        "parameters": {
            "a": {"annotation": "int", "doc": "<p>an int.</p>"},
            "b": {"annotation": "list[int]", "doc": "<p>a list of int.</p>"},
            "c": {
                "annotation": "dict[str, list[str]]",
                "doc": "<p>a dict of lists.</p>",
            },
        },
        "raise": {
            "ValueError": '<p>raise an error if <tt class="docutils literal">a</tt> is greater than <tt class="docutils literal">len(b)</tt>.</p>'
        },
        "return": {
            "annotation": "int",
            "doc": '<p>returns the element of <tt class="docutils literal">b</tt> at index <tt class="docutils literal">a</tt>.</p>',
        },
        "doc": """
        <div class="document">
        <p>Another dummy function.</p>
        </div>""",
    }

    def docstring_but_no_hints(self, a, b):
        pass

    docstring_but_no_hints.expected = {
        "signature": "(a, b)",
        "parameters": {
            "a": {"doc": "<p>an A</p>"},
            "b": {"doc": "<p>a B</p>"},
        },
        "doc": '<div class="document"></div>',
    }

    def no_docstring_but_hints(self, a: int) -> int:
        return a

    no_docstring_but_hints.expected = {
        "signature": "(a) -> int",
        "parameters": {"a": {"annotation": "int"}},
        "return": {"annotation": "int"},
    }

    def self_method(self, a):
        pass

    self_method.expected = {
        "signature": "(a)",
        "parameters": {"a": {"doc": "<p>an A</p>"}},
        "doc": '<div class="document"></div>',
    }

    def returns_base_model(self) -> models.BaseModel:
        return object.__new__(models.BaseModel)

    returns_base_model.expected = {
        "signature": "() -> list[int]",
        "parameters": {},
        "return": {"annotation": "list[int]"},
        "doc": '<div class="document"></div>',
    }

    def returns_model(self) -> models.Model:
        return object.__new__(models.Model)

    returns_model.expected = {
        "signature": "() -> list[int]",
        "parameters": {},
        "return": {"annotation": "list[int]"},
        "doc": '<div class="document"></div>',
    }

    def returns_self(self) -> Self:
        return self

    returns_self.expected = {
        "signature": "() -> list[int]",
        "parameters": {},
        "return": {"annotation": "list[int]"},
        "doc": '<div class="document"></div>',
    }

    @api.model
    def api_model_decorator(self):
        pass

    api_model_decorator.expected = {
        "api": ["model"],
        "parameters": {},
        "signature": "()",
    }

    @api.readonly
    def api_readonly_decorator(self):
        pass

    api_readonly_decorator.expected = {
        "api": ["readonly"],
        "parameters": {},
        "signature": "()",
    }

    @api.model
    @api.readonly
    def multiple_decorators(self):
        pass

    multiple_decorators.expected = {
        "signature": "()",
        "parameters": {},
        "api": ["model", "readonly"],
    }

    def bulletpoints(self):
        pass

    bulletpoints.expected = {
        "signature": "()",
        "parameters": {},
        "doc": """
        <div class="document">
        <p>Some bulletpoints:</p>
        <ul class="simple">
        <li>beep</li>
        <li>boop</li>
        </ul>
        <p>a bit more text</p>
        </div>""",
    }

    def type_field_only(self, a):
        pass

    type_field_only.expected = {
        "signature": "(a)",
        "parameters": {"a": {"annotation": "SomeCustomType", "doc": "<p>an A</p>"}},
        "doc": '<div class="document"></div>',
    }

    def every_parameter_kind(self, pos, /, normal, *args, kw_only=1, **kwargs):
        pass

    every_parameter_kind.expected = {
        "signature": "(pos, /, normal, *args, kw_only=1, **kwargs)",
        "parameters": {
            "pos": {"kind": "POSITIONAL_ONLY", "doc": "<p>positional-only</p>"},
            "normal": {},
            "args": {"kind": "VAR_POSITIONAL"},
            "kw_only": {"kind": "KEYWORD_ONLY", "default": 1},
            "kwargs": {"kind": "VAR_KEYWORD", "doc": "<p>the rest</p>"},
        },
        "doc": '<div class="document"></div>',
    }

    def deferred_annotation(self, names: Sequence[str]) -> Sequence[int]:  # noqa: F821 -- Fixture tests documentation of unresolved deferred annotations.
        pass

    deferred_annotation.expected = {
        "signature": "(names) -> Sequence[int]",
        "parameters": {"names": {"annotation": "Sequence[str]"}},
        "return": {"annotation": "Sequence[int]"},
    }

    @classmethod
    def class_method(cls):
        pass

    @staticmethod
    def static_method():
        pass

    @api.private
    def private_method(self):
        pass

    def _underscope_method(self):
        pass


DOCSTRING_FIXTURES = {
    "one_arg": "\n        A simple dummy identity function.\n\n        :param int a: an int.\n        :returns: an int.\n        :rtype: int\n        ",
    "multiple_args_and_error": "\n        Another dummy function.\n\n        :param int a: an int.\n        :param list[int] b: a list of int.\n        :param dict[str, list[str]] c: a dict of lists.\n        :raises ValueError: raise an error if ``a`` is greater than ``len(b)``.\n        :returns: returns the element of ``b`` at index ``a``.\n        :rtype: int\n        ",
    "docstring_but_no_hints": "\n        :param a: an A\n        :param b: a B\n        ",
    "self_method": "\n        :param self:\n        :param a: an A\n        ",
    "returns_base_model": "\n        :rtype: BaseModel\n        ",
    "returns_model": "\n        :rtype: Model\n        ",
    "returns_self": "\n        :rtype: Self\n        ",
    "bulletpoints": "\n        Some bulletpoints:\n\n        * beep\n        * boop\n\n        a bit more text\n        ",
    "type_field_only": "\n        :param a: an A\n        :type a: SomeCustomType\n        ",
    "every_parameter_kind": "\n        :param pos: positional-only\n        :param kwargs: the rest\n        ",
}
