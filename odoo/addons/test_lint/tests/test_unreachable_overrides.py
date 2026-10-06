import ast
import functools
import inspect
import re
import textwrap
from pathlib import Path
from unittest.mock import patch

from odoo.modules import Manifest
from odoo.modules.registry import Registry
from odoo.tests.common import get_db_name

from . import lint_case


def _walk_own_body(node):
    # a class nested in a method resolves its own super()
    for child in ast.iter_child_nodes(node):
        if not isinstance(child, ast.ClassDef):
            yield child
            yield from _walk_own_body(child)


@functools.cache
def _super_attributes(cls) -> tuple[tuple[str, bool], ...]:
    # each super().<name> in the class body, and whether that super() is the
    # bare form, which resolves from this class
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    except OSError, TypeError, SyntaxError:
        return ()
    return tuple(
        (node.attr, not node.value.args)
        for node in _walk_own_body(tree.body[0])
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "super"
    )


def _class_super_calls(cls) -> frozenset[str]:
    # the method names this class body extends through super(): in the method
    # of that name, or in a helper of the same class that calls it for them
    return frozenset(name for name, _bare in _super_attributes(cls))


def _is_method(value) -> bool:
    return inspect.isfunction(value)


def _has_source(cls) -> bool:
    try:
        inspect.getsource(cls)
    except OSError, TypeError:
        return False
    return True


# a wrapper the framework installs on a registry class (a verb door, an
# approval binding) reaches the rest of the MRO through the method it wraps
def _is_installed_wrapper(cls, name: str) -> bool:
    return getattr(vars(cls)[name], "__wrapped__", None) is not None and not (
        _has_source(cls)
    )


# definitions that end their chain on purpose: what they skip would be wrong
# or moot for their model. Named here, one reason each, so a new one is seen.
TERMINAL_BY_DESIGN = {
    (
        "write",
        "odoo.addons.base.models.auth_event.AuthEvent",
    ): "an authentication event is append-only: a write is refused",
    (
        "write",
        "odoo.addons.base.models.ir_access_log.IrAccessLog",
    ): "the authorization log is append-only: a write is refused",
    (
        "write",
        "odoo.addons.approval.models.approval_decision_log.ApprovalDecisionLog",
    ): "a decision log is append-only: a write is refused",
    (
        "write",
        "odoo.addons.sign.models.sign_log.SignLog",
    ): "a signature log is append-only: a write is refused",
    (
        "write",
        "odoo.addons.device_transport.models.device_transport_event.DeviceTransportEvent",
    ): "transport history is append-only: a write is refused",
    (
        "write",
        "odoo.addons.telegram.models.telegram_binding.TelegramBindingEvent",
    ): "a binding's history is append-only: a write is refused",
    (
        "unlink",
        "odoo.addons.base.models.res_partner_bank_account.ResPartnerBankAccount",
    ): "a bank account is archived, never deleted",
    (
        "get_base_url",
        "odoo.addons.website_slides.models.slide_slide.SlideSlide",
    ): "a slide's base URL is its channel's",
    (
        "action_send_mail",
        "odoo.addons.project.wizards.wizard_project_project_share.WizardProjectProjectShare",
    ): "sharing a project grants access and sends no portal link mail",
    (
        "_sale_get_order_map",
        "odoo.addons.project_sale_expense.models.account_move_line.AccountMoveLine",
    ): "the order map is the project's and the expense's, the expense winning",
}


def _qualified(cls) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def unreachable_findings(registry) -> list[str]:
    found = set()
    for model_name in registry.models:
        mro = [
            cls
            for cls in registry[model_name].__mro__
            if cls.__module__.startswith("odoo.")
        ]
        names = {
            name
            for cls in mro
            for name, value in vars(cls).items()
            if _is_method(value) and not name.startswith("__")
        }
        for name in names:
            defining = [cls for cls in mro if _is_method(vars(cls).get(name))]
            for index, ender in enumerate(defining[:-1]):
                if name in _class_super_calls(ender) or _is_installed_wrapper(
                    ender, name
                ):
                    continue
                if (name, _qualified(ender)) in TERMINAL_BY_DESIGN:
                    break
                for dead in defining[index + 1 :]:
                    if name in _class_super_calls(dead):
                        found.add(
                            f"{name}: {ender.__module__}.{ender.__qualname__} "
                            f"ends the chain before {dead.__module__}."
                            f"{dead.__qualname__}"
                        )
                break
    return sorted(found)


def _defined_in_source(qualified: str) -> bool:
    module_path, _, class_name = qualified.rpartition(".")
    addon = module_path.removeprefix("odoo.addons.").partition(".")[0]
    manifest = Manifest.for_addon(addon)
    if manifest is None:
        return True  # its repository is not on this addons path
    relative = module_path.removeprefix(f"odoo.addons.{addon}.").replace(".", "/")
    source = Path(manifest.path, f"{relative}.py")
    return source.is_file() and bool(
        re.search(
            rf"^class {re.escape(class_name)}\b",
            source.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def stale_terminal_entries(registry) -> list[str]:
    classes = {
        _qualified(cls): cls
        for model_name in registry.models
        for cls in registry[model_name].__mro__
    }
    stale = []
    for name, qualified in TERMINAL_BY_DESIGN:
        cls = classes.get(qualified)
        if cls is None:
            # not installed here, or gone: only the second is stale
            if not _defined_in_source(qualified):
                stale.append(f"{name}: {qualified} is defined nowhere")
            continue
        if not _is_method(vars(cls).get(name)) or name in _class_super_calls(cls):
            stale.append(f"{name}: {qualified} no longer ends its chain")
    return sorted(stale)


def orphan_super_findings(registry) -> list[str]:
    orphaned: dict[tuple[str, str], set[str]] = {}
    for model_name in registry.models:
        mro = registry[model_name].__mro__
        # a mixin extends what it is mixed into; the models it is mixed into
        # are the ones that answer for its super()
        if getattr(registry[model_name], "_abstract", False):
            continue
        for index, cls in enumerate(mro):
            if not cls.__module__.startswith("odoo."):
                continue
            for name, bare in _super_attributes(cls):
                if bare and not any(name in vars(later) for later in mro[index + 1 :]):
                    orphaned.setdefault((name, _qualified(cls)), set()).add(model_name)
    return sorted(
        f"{name}: {qualified} calls super().{name}(), which nothing after it "
        f"defines in {', '.join(sorted(models))}"
        for (name, qualified), models in orphaned.items()
    )


class TestUnreachableOverrides(lint_case.LintCase):
    def test_no_terminal_by_design_entry_is_stale(self):
        self.assertEqual(stale_terminal_entries(Registry(get_db_name())), [])

    def test_every_override_is_reachable(self):
        self.assert_ratchet(
            unreachable_findings(Registry(get_db_name())),
            "unreachable_override",
            "override(s) that extend a method through super() behind a "
            "definition that does not",
            "An override that calls super() and sits after, in the MRO, a "
            "definition of the same method that does not, never runs. List a "
            "mixin whose override must run before the model it extends first "
            "in _inherit (coding guidelines, mixin order), or make the ending "
            "definition call super().",
        )

    def test_every_super_call_reaches_a_definition(self):
        self.assert_ratchet(
            orphan_super_findings(Registry(get_db_name())),
            "orphan_super",
            "override(s) whose super() resolves to nothing",
            "An override whose super().<name>() no later class of the model "
            "defines is never called under that name, and raises "
            "AttributeError if it is: a parent renamed or dropped the method. "
            "Rename the override to the parent's name (coding guidelines, "
            "§2.2.4).",
        )


class _Root:
    def act(self):
        return "root"


class _Ender(_Root):
    def act(self):
        return "ended"


class _Extension(_Root):
    def act(self):
        return super().act()


class _Relay(_Root):
    def act(self):
        return self._relay()

    def _relay(self):
        return super().act()


class _Planted(_Ender, _Extension):
    pass


class _Relayed(_Relay, _Extension):
    pass


def _wrapper_like_a_door(cls, name):
    @functools.wraps(getattr(cls, name))
    def door(self, *args, **kwargs):
        return getattr(super(cls, cls), name)(self, *args, **kwargs)

    return door


_Doored = type("_Doored", (_Extension,), {})
_Doored.act = _wrapper_like_a_door(_Doored, "act")


def _decorated(function):
    @functools.wraps(function)
    def call(self):
        return function(self)

    return call


class _DecoratedEnder(_Root):
    @_decorated
    def act(self):
        return "ended"


class _DecoratedPlanted(_DecoratedEnder, _Extension):
    pass


class _Renamed(_Root):
    def renamed(self):
        return super().renamed()


class _Nesting(_Root):
    def act(self):
        class _Inner(_Root):
            def elsewhere(self):
                return super().act()

        return _Inner


class _Mixin:
    _abstract = True

    def act(self):
        return super().act()


class _Registry(dict):
    @property
    def models(self):
        return list(self)


class TestUnreachableOverridesSeesItsFaults(lint_case.LintCase):
    def test_an_extension_behind_an_ending_definition(self):
        findings = unreachable_findings(_Registry(planted=_Planted))

        self.assertEqual(len(findings), 1)
        self.assertIn("_Ender ends the chain before", findings[0])
        self.assertIn("_Extension", findings[0])

    def test_a_helper_calling_super_continues_the_chain(self):
        self.assertEqual(unreachable_findings(_Registry(relayed=_Relayed)), [])

    def test_a_wrapper_installed_on_the_registry_class_continues_the_chain(self):
        self.assertEqual(_Doored().act(), "root")
        self.assertEqual(unreachable_findings(_Registry(doored=_Doored)), [])

    def test_a_named_terminal_definition_is_not_a_finding(self):
        named = {("act", _qualified(_Ender)): "planted"}
        with patch.dict(TERMINAL_BY_DESIGN, named, clear=True):
            self.assertEqual(unreachable_findings(_Registry(planted=_Planted)), [])
        self.assertEqual(len(unreachable_findings(_Registry(planted=_Planted))), 1)

    def test_a_named_definition_that_extends_again_is_stale(self):
        named = {
            ("act", _qualified(_Ender)): "planted",
            ("act", _qualified(_Extension)): "planted",
        }
        with patch.dict(TERMINAL_BY_DESIGN, named, clear=True):
            self.assertEqual(
                stale_terminal_entries(_Registry(planted=_Planted)),
                [f"act: {_qualified(_Extension)} no longer ends its chain"],
            )

    def test_a_named_definition_whose_class_is_gone_is_stale(self):
        gone = "odoo.addons.base.models.ir_access_log.RemovedLog"
        with patch.dict(TERMINAL_BY_DESIGN, {("write", gone): "planted"}, clear=True):
            self.assertEqual(
                stale_terminal_entries(_Registry(planted=_Planted)),
                [f"write: {gone} is defined nowhere"],
            )

    def test_a_decorated_definition_in_source_still_ends_the_chain(self):
        findings = unreachable_findings(_Registry(planted=_DecoratedPlanted))

        self.assertEqual(len(findings), 1)
        self.assertIn("_DecoratedEnder ends the chain before", findings[0])

    def test_a_super_call_to_a_name_no_parent_defines(self):
        self.assertEqual(
            orphan_super_findings(_Registry(renamed=_Renamed)),
            [
                (
                    f"renamed: {_qualified(_Renamed)} calls super().renamed(), "
                    "which nothing after it defines in renamed"
                )
            ],
        )

    def test_a_super_call_the_parent_answers_is_not_an_orphan(self):
        self.assertEqual(orphan_super_findings(_Registry(relayed=_Relayed)), [])

    def test_a_nested_class_answers_for_its_own_super(self):
        self.assertEqual(orphan_super_findings(_Registry(nesting=_Nesting)), [])
        self.assertNotIn("act", _class_super_calls(_Nesting))

    def test_a_mixin_is_judged_where_it_is_mixed_in(self):
        self.assertEqual(orphan_super_findings(_Registry(mixin=_Mixin)), [])
