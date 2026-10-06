from __future__ import annotations

import typing

from odoo.libs.field_class_names import PER_RECORD

from ..domain import Domain
from ..models.field_classes import anonymous_spec

if typing.TYPE_CHECKING:
    from collections.abc import Hashable

    from odoo.libs.field_class_names import Verdict

    from .._typing import ModelLike
    from ..models.field_classes import FieldAccessClasses
    from ..primitives import IdType
    from .access_memo import FieldVerdicts, PrincipalVerdicts
    from .environment import Environment


class AccessPolicy:
    __slots__ = ()

    def model_allowed(self, env: Environment, model_name: str, operation: str) -> bool:
        # the hot path of every model-level question: the environment keeps
        # its verdicts for as long as its principal's signature holds, and a
        # verdict it has not asked yet comes from the registry's, keyed on
        # that signature
        if env.su:
            return True
        principal = env._principal_verdicts
        registry = env.registry
        if (
            principal.epoch != registry.cache_epoch
            or not registry.ready
            or (principal.until is not None and env.cr.now() >= principal.until)
        ):
            principal = self._principal(env)
        verdicts = principal.get(operation)
        if verdicts is None:
            verdicts = principal[operation] = {}
        verdict = verdicts.get(model_name)
        if verdict is None:
            if registry.ready or principal.pinned:
                verdict = env[model_name]._access_verdict(operation)
            else:
                # the verdict's own cache keys read the signature again, twice;
                # the rows cannot change within the check, only between checks
                principal.pinned = True
                try:
                    verdict = env[model_name]._access_verdict(operation)
                finally:
                    principal.pinned = False
            verdicts[model_name] = verdict
        return verdict

    def _principal(self, env: Environment) -> PrincipalVerdicts:
        # the environment's principal, read again once a cache group was
        # cleared or its signature's validity ran out; not kept while modules
        # load, where the rows in play change without a clear
        principal = env._principal_verdicts
        if principal.pinned:
            return principal
        registry = env.registry
        epoch = registry.cache_epoch
        if (
            principal.epoch == epoch
            and registry.ready
            and (principal.until is None or env.cr.now() < principal.until)
        ):
            return principal
        principal.clear()
        access = env["ir.access"]
        principal.signature = access._policy_signature()
        principal.until = access._policy_expiry()
        principal.epoch = epoch if registry.ready else None
        return principal

    def model_denied_error(
        self, env: Environment, model_name: str, operation: str
    ) -> Exception:
        return env["ir.access"]._prepare_model_access_error(model_name, operation)

    def record_domain(
        self, env: Environment, model_name: str, operation: str
    ) -> Domain:
        if env.su:
            return Domain.TRUE
        return env[model_name]._access_domain(operation)

    def field_allowed(
        self, env: Environment, classes: FieldAccessClasses, operation: str
    ) -> bool:
        # the field's classes grant the operation to the principal, on some
        # records at least; each class verdict is computed once per principal
        # and transaction
        return self._field_verdict(env, classes, operation) is not False

    def field_domain(
        self,
        env: Environment,
        model_name: str,
        classes: FieldAccessClasses,
        operation: str,
    ) -> Domain | None:
        # the records of the model the field's classes grant the operation on,
        # when that differs from record to record; None when the verdict is
        # the same on every record
        if self._field_verdict(env, classes, operation) is not PER_RECORD:
            return None
        verdicts = env.transaction.access_memo.field_verdicts(env)
        slot = (model_name, operation, classes)
        domain = verdicts.domains.get(slot)
        if domain is None:
            keys, alternative = self._field_keys(classes, operation)
            domain = self._keys_domain(env, verdicts, model_name, keys, operation)
            if alternative:
                domain |= self._keys_domain(
                    env, verdicts, model_name, alternative, operation
                )
            verdicts.domains[slot] = domain
        return domain

    @staticmethod
    def _field_keys(
        classes: FieldAccessClasses, operation: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        if operation == "read":
            return classes.read, classes.read_alternative
        return classes.write, ()

    def _field_verdict(
        self, env: Environment, classes: FieldAccessClasses, operation: str
    ) -> Verdict:
        # the AND of the field's classes, or of its alternative classes; the
        # hot path of every field check, so the class loop is inlined
        if operation == "read":
            keys, alternative = classes.read, classes.read_alternative
        else:
            keys, alternative = classes.write, ()
        if not keys:
            return True
        verdicts = env.transaction.access_memo.field_verdicts(env)
        table = verdicts if operation == "read" else verdicts.write
        verdict: Verdict = True
        for key in keys:
            known = table.get(key)
            if known is None:
                known = table[key] = self._field_class_allowed(env, key, operation)
            if known is False:
                verdict = False
                break
            if known is not True:
                verdict = PER_RECORD
        if verdict is True or not alternative:
            return verdict
        other = self._field_classes_verdict(env, verdicts, alternative, operation)
        if other is True:
            return True
        return PER_RECORD if PER_RECORD in (verdict, other) else False

    def _keys_domain(
        self,
        env: Environment,
        verdicts: FieldVerdicts,
        model_name: str,
        keys: tuple[str, ...],
        operation: str,
    ) -> Domain:
        domain = Domain.TRUE
        for key in keys:
            verdict = self._class_verdict(env, verdicts, key, operation)
            if verdict is False:
                return Domain.FALSE
            if verdict is PER_RECORD:
                domain &= env["ir.access"]._field_class_domain(
                    key, operation, model_name
                )
        return domain

    def label_domain(
        self, env: Environment, model_name: str, label: str, operation: str
    ) -> Domain:
        # the records of the model whose label class grants the principal the
        # operation: unlabelled, labelled with a class it holds everywhere, or
        # with one it holds on some records, there only
        verdicts = env.transaction.access_memo.field_verdicts(env)
        access = env["ir.access"]
        everywhere = []
        somewhere = []
        for class_id, name in access._label_classes():
            verdict = self._class_verdict(env, verdicts, name, operation)
            if verdict is True:
                everywhere.append(class_id)
            elif verdict is PER_RECORD:
                somewhere.append(
                    Domain(label, "=", class_id)
                    & access._field_class_domain(name, operation, model_name)
                )
        return Domain.OR([Domain(label, "in", [False, *everywhere]), *somewhere])

    def _field_classes_verdict(
        self,
        env: Environment,
        verdicts: FieldVerdicts,
        keys: tuple[str, ...],
        operation: str,
    ) -> Verdict:
        result: Verdict = True
        for key in keys:
            verdict = self._class_verdict(env, verdicts, key, operation)
            if verdict is False:
                return False
            if verdict is not True:
                result = PER_RECORD
        return result

    def _class_verdict(
        self, env: Environment, verdicts: FieldVerdicts, key: str, operation: str
    ) -> Verdict:
        table = verdicts if operation == "read" else verdicts.write
        verdict = table.get(key)
        if verdict is None:
            verdict = table[key] = self._field_class_allowed(env, key, operation)
        return verdict

    def _field_class_allowed(
        self, env: Environment, key: str, operation: str
    ) -> Verdict:
        if "ir.access" not in env.registry:
            spec = anonymous_spec(key)
            return spec is not None and env.user.has_groups(spec)
        return env["ir.access"]._field_class_allowed(key, operation)

    def rule_context(self, env: Environment) -> tuple[Hashable, ...]:
        if "ir.access" not in env.registry:
            company_ids = env.context.get("allowed_company_ids")
            return (tuple(company_ids) if company_ids else company_ids,)
        return tuple(env["ir.access"]._get_access_context())

    def record_denied_error(
        self, env: Environment, operation: str, records: ModelLike
    ) -> Exception:
        return env["ir.access"]._prepare_record_access_error(records, operation)

    def access_signature(self, env: Environment) -> tuple[Hashable, ...]:
        return self._principal(env).signature

    def privilege_ids(self, env: Environment, names: tuple[str, ...]) -> frozenset[int]:
        return env["res.groups"]._privilege_ids(names)

    def note_privileged(
        self, env: Environment, model_name: str, operation: str, ids: tuple[IdType, ...]
    ) -> None:
        if "ir.access.log" in env.registry:
            env["ir.access.log"]._record_privileged(model_name, operation, ids)

    def verb_door(
        self,
        env: Environment,
        records: ModelLike,
        verb: str,
        call: typing.Callable[..., typing.Any],
    ) -> typing.Any:
        if "ir.access.obligation" not in env.registry:
            with env.transaction.admitting(records._name, verb, records._ids):
                return call(records)
        return env["ir.access.obligation"]._at_door(records, verb, call)

    def verb_checkpoint(self, env: Environment, records: ModelLike, verb: str) -> None:
        if "ir.access.obligation" in env.registry:
            env["ir.access.obligation"]._at_checkpoint(records, verb)

    def verb_landed(self, env: Environment, records: ModelLike, verb: str) -> None:
        if "ir.access.obligation" in env.registry:
            env["ir.access.obligation"]._after_move(records, verb)

    def bound_access_rows(
        self, env: Environment, model_name: str, operation: str
    ) -> tuple[list[Domain], list[Domain]]:
        return env["ir.access"]._bound_access_rows(model_name, operation)


# every registry decides from the ir.access model it hosts; an in-memory one
# that hosts none raises its tier's marker the moment a principal is checked
ACCESS_POLICY = AccessPolicy()
