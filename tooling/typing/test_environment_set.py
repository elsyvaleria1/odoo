import gc
import unittest
from typing import override
from weakref import ref

from odoo.libs.collections import frozendict
from odoo.orm.runtime.environment import Environment
from odoo.orm.runtime.transaction import _EnvironmentSet


def make_environment(number: int) -> Environment:
    # These tests isolate the collection from transaction interning and its
    # deliberate recent-environment references, which would delay collection.
    env = object.__new__(Environment)
    env.uid = number
    env.su = False
    env.context = frozendict({"number": number})
    env.privileges = frozenset()
    return env


class EnvironmentSetTests(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.first = make_environment(1)
        self.second = make_environment(2)
        self.third = make_environment(3)

    def assert_index(self, envs: _EnvironmentSet, *expected: Environment) -> None:
        self.assertEqual(list(envs), list(expected))
        for env in (self.first, self.second, self.third):
            indexed = envs.get_environment(
                envs.key(env.uid, env.su, env.context, env.privileges)
            )
            self.assertIs(indexed, env if env in expected else None)

    def test_mutations_update_the_index_and_preserve_order(self) -> None:
        envs = _EnvironmentSet([self.first, self.second])
        self.assert_index(envs, self.first, self.second)
        envs.update([self.first, self.third])
        self.assert_index(envs, self.first, self.second, self.third)
        envs.difference_update([self.second])
        self.assert_index(envs, self.first, self.third)
        envs.intersection_update([self.first])
        self.assert_index(envs, self.first)
        envs.symmetric_difference_update([self.first, self.second])
        self.assert_index(envs, self.second)
        self.assertIs(envs.pop(), self.second)
        self.assert_index(envs)
        with self.assertRaises(KeyError):
            envs.remove(self.first)
        envs.add(self.first)
        envs.remove(self.first)
        self.assert_index(envs)
        envs.update([self.second, self.third])
        envs.clear()
        self.assert_index(envs)

    def test_inplace_operators_keep_identity_and_index(self) -> None:
        envs = _EnvironmentSet([self.first])
        original = envs
        envs |= {self.second}
        self.assert_index(envs, self.first, self.second)
        envs &= {self.second}
        self.assert_index(envs, self.second)
        envs ^= {self.second, self.third}
        self.assert_index(envs, self.third)
        envs -= {self.third}
        self.assert_index(envs)

        self.assertIs(envs, original)
        envs.add(self.first)
        envs ^= envs
        self.assert_index(envs)

    def test_inplace_iterables_and_foreign_members_preserve_the_index(self) -> None:
        envs = _EnvironmentSet([self.first])
        original = envs
        envs |= iter([self.second])
        self.assert_index(envs, self.first, self.second)
        envs &= [self.second, "foreign"]
        self.assert_index(envs, self.second)
        envs ^= (env for env in [self.second, self.third])
        self.assert_index(envs, self.third)
        envs -= {"foreign"}
        self.assert_index(envs, self.third)
        envs -= (env for env in envs)
        self.assert_index(envs)
        self.assertIs(envs, original)

    def test_forward_operators_can_widen_without_touching_the_index(self) -> None:
        envs = _EnvironmentSet([self.first, self.second])
        union = envs | {self.third}
        self.assertIsInstance(union, set)
        self.assertEqual(set(union), {self.first, self.second, self.third})
        self.assertEqual(envs | {"extra"}, {self.first, self.second, "extra"})
        self.assertEqual(envs & {self.second}, {self.second})
        self.assertEqual(envs - {self.first}, {self.second})
        self.assert_index(envs, self.first, self.second)

    def test_members_and_index_do_not_keep_environments_alive(self) -> None:
        envs = _EnvironmentSet()
        temporary = make_environment(4)
        weak = ref(temporary)
        key = envs.key(
            temporary.uid, temporary.su, temporary.context, temporary.privileges
        )
        envs.add(temporary)
        del temporary
        gc.collect()
        self.assertIsNone(weak())
        self.assertEqual(len(envs), 0)
        self.assertEqual(list(envs), [])
        self.assertIsNone(envs.get_environment(key))
