from __future__ import annotations

import typing
from collections import defaultdict
from contextlib import contextmanager

from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.libs.sql.builder import SQL
from odoo.tools.query import Query

from ..constants import READ_GROUP_NUMBER_GRANULARITY
from ..domain import Domain, DomainBool, DomainCondition, DomainNary, DomainNot
from ..domain.constants import SUBDOMAIN_OPERATORS
from ..domain.optimizations import access_condition_target
from ..primitives import COLLECTION_TYPES

if typing.TYPE_CHECKING:
    from collections.abc import Collection, Hashable, Iterator

    from odoo.libs.field_class_names import Verdict

    from ..fields import Field
    from ..models import BaseModel
    from ..models.field_classes import FieldAccessClasses
    from ..primitives import IdType
    from .environment import Environment
    from .registry import Registry

_debug = DebugLog(__name__)

_MAX_DEPTH = 8
_HIERARCHY_OPERATORS = frozenset(("child_of", "parent_of"))

type Fact = tuple[str, str]
type Facts = frozenset[Fact] | None
type VerdictKey = tuple[Hashable, ...]
type WatchEntry = VerdictKey | Field[typing.Any]


def domain_read_facts(model: BaseModel, domain: Domain) -> Facts:
    facts: set[Fact] = set()
    try:
        known = _collect_domain(model, domain, facts, 0)
    except KeyError, TypeError, ValueError:
        known = False
    return frozenset(facts) if known else None


def _collect_domain(
    model: BaseModel, domain: Domain, facts: set[Fact], depth: int
) -> bool:
    if isinstance(domain, DomainBool):
        return True
    if isinstance(domain, DomainNot):
        return _collect_domain(model, domain.child, facts, depth)
    if isinstance(domain, DomainNary):
        return all(_collect_domain(model, c, facts, depth) for c in domain.children)
    if isinstance(domain, DomainCondition):
        return _collect_condition(model, domain, facts, depth)
    return False


def _collect_condition(
    model: BaseModel, condition: DomainCondition, facts: set[Fact], depth: int
) -> bool:
    field = _collect_path(model, condition.field_expr, facts, depth)
    if field is False:
        return False
    if condition.operator == "access":
        return field is not None and _collect_access(
            model, field, condition, facts, depth
        )
    value = condition.value
    if condition.operator in _HIERARCHY_OPERATORS:
        return field is not None and _collect_hierarchy(
            model, field, value, facts, depth
        )
    if isinstance(value, Domain):
        subdomain = value
    elif condition.operator in SUBDOMAIN_OPERATORS and isinstance(value, list | tuple):
        subdomain = Domain(value, internal=True)
    else:
        return not isinstance(value, Query | SQL)
    if field is None or not field.relational:
        return False
    return _collect_domain(
        model.env[field._get_comodel_name()], subdomain, facts, depth + 1
    )


def _collect_hierarchy(
    model: BaseModel,
    field: Field[typing.Any],
    value: typing.Any,
    facts: set[Fact],
    depth: int,
) -> bool:
    values = value if isinstance(value, COLLECTION_TYPES) else (value,)
    if any(isinstance(v, str | Query | SQL) for v in values):
        return False
    owner = model.env[field.model_name]
    if field.relational:
        comodel = owner.env[field._get_comodel_name()]
        parent = field.name if comodel._name == owner._name else comodel._parent_name
    elif field.name == "id":
        comodel, parent = owner, owner._parent_name
    else:
        return False
    parent_field = comodel._fields.get(parent)
    if parent_field is None or not _collect_field(
        comodel, parent_field, facts, depth + 1
    ):
        return False
    if comodel._parent_store and parent == comodel._parent_name:
        facts.add((comodel._get_model_name(), "parent_path"))
    if field.is_many2many and comodel._active_name:
        facts.add((comodel._get_model_name(), comodel._active_name))
    return True


def _collect_access(
    model: BaseModel,
    field: Field[typing.Any],
    condition: DomainCondition,
    facts: set[Fact],
    depth: int,
) -> bool:
    if depth >= _MAX_DEPTH:
        return False
    owner = model.env[field.model_name]
    target = DomainCondition(field.name, "access", condition.value)
    comodel_name, operation = access_condition_target(target, owner)
    env = owner.sudo(False).env
    domain = env.registry.access_policy.record_domain(env, comodel_name, operation)
    return _collect_domain(env[comodel_name], domain, facts, depth + 1)


def _collect_path(
    model: BaseModel, path: str, facts: set[Fact], depth: int
) -> Field[typing.Any] | typing.Literal[False] | None:
    names = path.split(".")
    field = None
    for index, name in enumerate(names):
        field = model._fields.get(name)
        if field is None:
            if (
                index
                and index == len(names) - 1
                and name in READ_GROUP_NUMBER_GRANULARITY
            ):
                return None
            return False
        if not _collect_field(model, field, facts, depth):
            return False
        if index < len(names) - 1:
            if not field.relational:
                return False
            model = model.env[field._get_comodel_name()]
    return field


def _collect_field(
    model: BaseModel, field: Field[typing.Any], facts: set[Fact], depth: int
) -> bool:
    facts.add((model._get_model_name(), field.name))
    if field.is_x2many and not _collect_membership(model, field, facts, depth):
        return False
    if field.store:
        return True
    if depth >= _MAX_DEPTH:
        return False
    if field.related:
        return _collect_path(model, field.related, facts, depth + 1) is not False
    depends = model.pool.field_depends.get(field)
    if not depends:
        return False
    return all(
        _collect_path(model, dotted, facts, depth + 1) is not False
        for dotted in depends
    )


def _collect_membership(
    model: BaseModel, field: Field[typing.Any], facts: set[Fact], depth: int
) -> bool:
    if field.is_one2many:
        if field.comodel_name is None or field.inverse_name is None:
            return False
        facts.add((field.comodel_name, field.inverse_name))
    else:
        facts.update(_relation_siblings(model, field))
    comodel = model.env[field._get_comodel_name()]
    if comodel._active_name:
        facts.add((comodel._get_model_name(), comodel._active_name))
    domain = field.domain
    if callable(domain):
        return False
    if not domain or isinstance(domain, str):
        return True
    return _collect_domain(comodel, Domain(domain), facts, depth + 1)


def _relation_siblings(model: BaseModel, field: Field[typing.Any]) -> Iterator[Fact]:
    relation, column1, column2 = field.relation, field.column1, field.column2
    if not (relation and column1 and column2):
        return
    relations = model.pool.many2many_relations
    for columns in ((relation, column1, column2), (relation, column2, column1)):
        yield from relations.get(columns, ())


class FieldVerdicts(dict[str, "Verdict"]):
    __slots__ = ("domains", "write")

    def __init__(self) -> None:
        super().__init__()
        self.write: dict[str, Verdict] = {}
        self.domains: dict[tuple[str, str, FieldAccessClasses], Domain] = {}


def _reads_through(registry: Registry, facts: Facts, model_name: str) -> bool:
    if facts is None:
        return False
    for fact_model, fname in facts:
        field = registry[fact_model]._fields.get(fname)
        if field is not None and field.is_x2many and field.comodel_name == model_name:
            return True
    return False


class RecordVerdicts(dict["IdType", bool]):
    __slots__ = ("computed",)

    def __init__(self, computed: tuple[Field[typing.Any], ...] = ()) -> None:
        super().__init__()
        self.computed = computed


def _computed_inputs(registry: Registry, facts: Facts) -> tuple[Field[typing.Any], ...]:
    if facts is None:
        return ()
    return tuple(
        field
        for model_name, fname in facts
        if (field := registry[model_name]._fields.get(fname)) is not None
        and field.store
        and field.compute
    )


class PrincipalVerdicts(dict[str, dict[str, bool]]):
    __slots__ = ("epoch", "pinned", "signature", "until")

    def __init__(self) -> None:
        super().__init__()
        self.epoch: int | None = None
        self.pinned = False
        self.signature: tuple[Hashable, ...] = ()
        self.until: typing.Any = None


class AccessMemo:
    __slots__ = (
        "_epoch",
        "_everything",
        "_facts",
        "_field_verdicts",
        "_observed",
        "_observing",
        "_registered",
        "_rewatch",
        "_translated",
        "_verdicts",
        "_watchers",
    )

    def __init__(self) -> None:
        self._epoch: int | None = None
        self._observing: list[tuple[str, set[Fact]]] = []
        self.clear()

    def clear(self) -> None:
        self._facts: dict[VerdictKey, Facts] = {}
        self._verdicts: dict[VerdictKey, RecordVerdicts] = {}
        self._field_verdicts: dict[VerdictKey, FieldVerdicts] = {}
        self._watchers: defaultdict[str, set[WatchEntry]] = defaultdict(set)
        self._everything: set[WatchEntry] = set()
        self._registered: dict[
            tuple[Field[typing.Any], VerdictKey], tuple[Environment, bool]
        ] = {}
        self._rewatch: list[tuple[Field[typing.Any], Environment, bool]] = []
        self._observed: defaultdict[str, set[Fact]] = defaultdict(set)
        self._translated: dict[tuple[typing.Any, str], bool] = {}

    def _sync(self, registry: Registry) -> None:
        epoch = registry.cache_epoch
        if epoch == self._epoch:
            return
        if self._epoch is not None and (self._verdicts or self._registered):
            _debug.lifecycle(
                "access_memo.cache_epoch_changed",
                verdicts=len(self._verdicts),
                x2many=len(self._registered),
            )
        rewatch = self._rewatch + [
            (key[0], env, everything)
            for key, (env, everything) in self._registered.items()
        ]
        observed = self._observed
        self.clear()
        self._observed = observed
        self._rewatch = rewatch
        self._epoch = epoch

    def _flush_rewatch(self) -> None:
        rewatch, self._rewatch = self._rewatch, []
        for field, env, everything in rewatch:
            self.watch_x2many(env, field, everything)

    @staticmethod
    def domain_facts(model: BaseModel, domain: Domain) -> Facts:
        return domain_read_facts(model, domain)

    def read_facts(self, env: Environment, model_name: str) -> Facts:
        key = (env._read_access_key, model_name)
        try:
            return self._facts[key]
        except KeyError:
            pass
        domain = env.registry.access_policy.record_domain(env, model_name, "read")
        facts = self._facts[key] = domain_read_facts(env[model_name], domain)
        if facts is None:
            _debug.logic("access_memo.rule_untrackable", model=model_name, uid=env.uid)
        return facts

    def reads_translated(self, env: Environment, model_name: str) -> bool:
        self._sync(env.registry)
        key = (env._read_access_key, model_name)
        try:
            return self._translated[key]
        except KeyError:
            pass
        facts = self.read_facts(env, model_name)
        registry = env.registry
        answer = self._translated[key] = facts is None or any(
            (field := registry[fact_model]._fields.get(fname)) is not None
            and bool(field.translate)
            for fact_model, fname in facts
        )
        return answer

    def _watch(self, entry: WatchEntry, facts: Facts, models: Collection[str]) -> None:
        if facts is None:
            self._everything.add(entry)
            return
        for model_name in {model_name for model_name, _fname in facts} | set(models):
            self._watchers[model_name].add(entry)

    def _verdicts_key(
        self, env: Environment, model_name: str
    ) -> tuple[typing.Any, str, str | None]:
        lang = env.lang
        if lang == "en_US" or (lang and not self.reads_translated(env, model_name)):
            lang = None
        return (env._read_access_key, model_name, lang)

    def read_verdicts(self, env: Environment, model_name: str) -> RecordVerdicts:
        self._sync(env.registry)
        key = self._verdicts_key(env, model_name)
        verdicts = self._fresh_verdicts(env, key)
        if verdicts is None:
            facts = self._facts[key] = self.read_facts(env, model_name)
            verdicts = self._verdicts[key] = RecordVerdicts(
                _computed_inputs(env.registry, facts)
            )
            self._watch(key, facts, ())
        return verdicts

    def _fresh_verdicts(
        self, env: Environment, key: VerdictKey
    ) -> RecordVerdicts | None:
        verdicts = self._verdicts.get(key)
        if verdicts is None or not verdicts.computed:
            return verdicts
        core = env.core
        if core.has_pending() and any(map(core.has_pending_field, verdicts.computed)):
            del self._verdicts[key]
            return None
        return verdicts

    def field_verdicts(self, env: Environment) -> FieldVerdicts:
        if self._epoch != env.registry.cache_epoch:
            self._sync(env.registry)
        key = env._read_access_key
        verdicts = self._field_verdicts.get(key)
        if verdicts is None:
            verdicts = self._field_verdicts[key] = FieldVerdicts()
        return verdicts

    def domain_verdicts(
        self, env: Environment, model_name: str, domain: Domain
    ) -> RecordVerdicts | None:
        self._sync(env.registry)
        key = (
            env._read_access_key,
            model_name,
            domain,
            env.context.get("active_test", True),
            env.lang,
        )
        verdicts = self._fresh_verdicts(env, key)
        if verdicts is not None:
            return verdicts
        try:
            facts = self._facts[key]
        except KeyError:
            facts = self._facts[key] = domain_read_facts(env[model_name], domain)
            if facts is None:
                _debug.logic(
                    "access_memo.field_domain_untrackable",
                    model=model_name,
                    uid=env.uid,
                )
        if facts is None:
            return None
        verdicts = self._verdicts[key] = RecordVerdicts(
            _computed_inputs(env.registry, facts)
        )
        self._watch(key, facts, ())
        return verdicts

    def cached_verdicts(
        self, env: Environment, model_name: str
    ) -> RecordVerdicts | None:
        if self._epoch != env.registry.cache_epoch:
            return None
        return self._fresh_verdicts(env, self._verdicts_key(env, model_name))

    def watch_x2many(
        self, env: Environment, field: Field[typing.Any], everything: bool
    ) -> None:
        self._sync(env.registry)
        key = (field, env._read_access_key)
        if key in self._registered:
            return
        self._registered[key] = (env, everything)
        try:
            facts = (
                None if everything else self.read_facts(env, field._get_comodel_name())
            )
        except AccessError:
            facts = None
        self._watch(field, facts, self._observed_models(field._get_comodel_name()))

    def _observed_models(self, model_name: str) -> set[str]:
        return {name for name, _fname in self._observed.get(model_name, ())}

    def observed_facts(self, model_name: str) -> Collection[Fact]:
        return self._observed.get(model_name, ())

    @contextmanager
    def observing(self, model_name: str) -> Iterator[None]:
        seen: set[Fact] = set()
        self._observing.append((model_name, seen))
        try:
            yield
        finally:
            self._observing.pop()
            new = seen - self._observed[model_name]
            if new:
                self._observed[model_name] |= new
                models = {name for name, _fname in new}
                for field, _scope in self._registered:
                    if field.comodel_name == model_name:
                        self._watch(field, frozenset(), models)

    def note_search(self, model_name: str, query: Query) -> None:
        if not self._observing:
            return
        seen = self._observing[-1][1]
        seen.add((model_name, "id"))
        for sql in (query.from_clause, query.where_clause):
            seen.update((field.model_name, field.name) for field in sql.to_flush)

    def written(
        self,
        env: Environment,
        model_name: str,
        fnames: Collection[str] | None,
        *,
        created: bool = False,
    ) -> list[Field[typing.Any]]:
        self._sync(env.registry)
        if self._rewatch:
            self._flush_rewatch()
        entries = self._entries(model_name)
        if not entries:
            return []
        self._drop_verdicts(entries, model_name, fnames, created, env.registry)
        return [entry for entry in entries if not isinstance(entry, tuple)]

    def forget(
        self, registry: Registry, model_name: str, fnames: Collection[str] | None
    ) -> None:
        if not self._verdicts or self._epoch != registry.cache_epoch:
            return
        if fnames is None:
            for key in [key for key in self._verdicts if key[1] == model_name]:
                del self._verdicts[key]
        if entries := self._entries(model_name):
            self._drop_verdicts(entries, model_name, fnames, False, registry)

    def _entries(self, model_name: str) -> Collection[WatchEntry]:
        watchers = self._watchers.get(model_name)
        everything = self._everything
        if not watchers:
            return everything
        return watchers | everything if everything else watchers

    def _drop_verdicts(
        self,
        entries: Collection[WatchEntry],
        model_name: str,
        fnames: Collection[str] | None,
        created: bool,
        registry: Registry,
    ) -> None:
        dropped = 0
        for entry in entries:
            if not isinstance(entry, tuple) or entry not in self._verdicts:
                continue
            facts = self._facts.get(entry)
            if (
                created
                and entry[1] == model_name
                and not _reads_through(registry, facts, model_name)
            ):
                continue
            if (
                facts is None
                or fnames is None
                or any((model_name, fname) in facts for fname in fnames)
            ):
                del self._verdicts[entry]
                dropped += 1
        if dropped and _debug.logic.enabled:
            _debug.logic(
                "access_memo.verdicts_dropped",
                model=model_name,
                fields=None if fnames is None else sorted(fnames),
                dropped=dropped,
            )
