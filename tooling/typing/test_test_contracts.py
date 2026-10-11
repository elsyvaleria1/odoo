import unittest
from typing import override

from odoo.exceptions import AccessError
from odoo.orm.models import BaseModel
from odoo.tests.benchmark import BenchmarkCase
from odoo.tests.transaction_case import BaseCase


class AssertionContractTests(unittest.TestCase):
    def test_benchmark_mixin_preserves_cooperative_base_orders(self) -> None:
        calls: list[str] = []

        class Host(unittest.TestCase):
            @classmethod
            @override
            def setUpClass(cls) -> None:
                calls.append(cls.__name__)
                super().setUpClass()

        class Before(Host, BenchmarkCase):
            pass

        class After(BenchmarkCase, Host):
            pass

        Before.setUpClass()
        After.setUpClass()
        self.assertEqual(calls, ["Before", "After"])
        self.assertFalse(hasattr(Before, "all_results"))
        self.assertEqual(After.all_results, [])

    def test_unnamed_framework_prototypes_keep_the_none_sentinel(self) -> None:
        self.assertIsNone(BaseModel._name)
        with self.assertRaisesRegex(TypeError, "not a named registry model"):
            BaseModel._get_model_name()

    def test_context_preserves_unittest_assertion_object(self) -> None:
        case = BaseCase()
        context = case.assertRaises((ValueError, AccessError))
        with context as caught:
            self.assertIsNot(caught, context)
            raise ValueError("expected")
        self.assertIsInstance(caught.exception, ValueError)
        self.assertEqual(str(caught.exception), "expected")

    def test_callback_keyword_names_are_forwarded(self) -> None:
        case = BaseCase()

        def raise_error(*, expected_exception: str, callable: str) -> None:  # noqa: A002 -- reproduce forwarded callback keywords
            self.assertEqual((expected_exception, callable), ("exception", "callback"))
            raise ValueError("expected")

        case.assertRaises(
            ValueError, raise_error, expected_exception="exception", callable="callback"
        )

    def test_context_changes_apply_to_the_actual_assertion(self) -> None:
        case = BaseCase()
        with self.assertRaisesRegex(AssertionError, "changed message"):
            with case.assertRaises(ValueError) as context:
                context.msg = "changed message"
        with case.assertRaises(ValueError) as context:
            context.expected = TypeError
            raise TypeError("changed exception")

    def test_callable_and_unexpected_exceptions(self) -> None:
        case = BaseCase()

        def raise_error(message: str) -> None:
            raise ValueError(message)

        self.assertIsNone(case.assertRaises(ValueError, raise_error, "expected"))
        self.assertIsNone(
            case.assertRaises(ValueError, func=raise_error, message="expected")
        )
        self.assertIsNone(
            case.assertRaises(
                exception=ValueError, func=raise_error, message="expected"
            )
        )
        with case.assertRaises(exception=ValueError):
            raise ValueError("legacy keyword")
        with self.assertRaises(TypeError):
            with case.assertRaises(ValueError):
                raise TypeError("unexpected")
        with self.assertRaisesRegex(AssertionError, "missing"):
            with case.assertRaises(ValueError, msg="missing"):
                pass

    def test_database_state_is_optional_until_setup(self) -> None:
        case = BaseCase()
        self.assertIsNone(case.env)
        self.assertIsNone(case.registry)
        self.assertIsNone(case.cr)
        for getter in (case._get_env, case._get_registry, case._get_cr):
            with self.assertRaisesRegex(RuntimeError, "requires a database"):
                getter()
