import functools
import logging
import typing
from collections import defaultdict
from operator import itemgetter
from typing import Self

from odoo.exceptions import AccessError, MissingError, UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.reprs import unquote
from odoo.tools import ormcache
from odoo.tools.translate import LazyTranslate

from ... import decorators as api
from ...domain import Domain, DomainCondition, OptimizationLevel
from ...domain.constants import ACCESS_OPERATIONS
from ...fields.base import call_hook
from ...helpers import to_record_ids
from ...primitives import LOG_ACCESS_COLUMNS, NO_ACCESS, PREFETCH_MAX, SUPERUSER_ID
from ..field_classes import is_anonymous
from ._model_stubs import _ModelStubs

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterator

    from ..._typing import BaseModel, IdType, ModelLike
    from ...fields import Field
    from ...runtime.access_memo import RecordVerdicts
    from ._model_stubs import VerbTransitions

_lt = LazyTranslate("base")

_RESIDUAL_EXEMPT = frozenset(["id", "display_name", *LOG_ACCESS_COLUMNS])

_logger = logging.getLogger("odoo.models")
_debug = DebugLog(__name__)


class AccessMixin(_ModelStubs):
    __slots__ = ()

    @api.model
    def _access_field_class(self, field: Field[typing.Any]) -> str | None:
        # a class the model gives the field beside the field's own: here the
        # residual class, for a field that names none, but not the automatic
        # columns a search and a name always need. Asked once per field at
        # registry setup, as the other two hooks below
        if field.name in _RESIDUAL_EXEMPT or field.classification:
            return None
        return self._access_residual_class

    @api.model
    def _access_field_write_class(self, field: Field[typing.Any]) -> str | None:
        # a class needed to write the field, beside what reading it needs
        return None

    @api.model
    def _access_field_alternative_class(self, field: Field[typing.Any]) -> str | None:
        # a class that grants reading the field on its own, whatever else the
        # field requires (a user's own record)
        return None

    def _has_field_access(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> bool:
        classes = field.access_classes
        if classes is None or self.env.su:
            return True
        if not self.env.registry.access_policy.field_allowed(
            self.env, classes, operation
        ):
            return False
        if operation == "write" and classes.write_hook is not None:
            hook = self._fields[field.name].write_groups
            if callable(hook):
                return bool(call_hook(hook, self))
        return True

    @api.model
    def _check_fields_write_access(self, field_names: typing.Iterable[str]) -> None:
        # on a recordset, also refuses a field the principal may write on some
        # records only (a group held through a grant limited to some
        # companies) when the records reach outside them
        field_names = list(field_names)
        for field_name in field_names:
            field = self._fields.get(field_name)
            if field is None:
                raise ValueError(f"Invalid field {field_name!r} in {self._name!r}")
            self._check_field_access(field, "write")
        if self._ids:
            self._check_fields_write_records(field_names)

    def _check_fields_write_records(self, field_names: typing.Iterable[str]) -> None:
        # a field the principal may write on some records only, written on
        # others: the records of a write before it, those of a create after
        if self.env.su:
            return
        for field_name in field_names:
            field = self._fields[field_name]
            if field.access_classes is not None:
                self._check_field_access_records(field, "write")

    def _field_access_domain(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> Domain | None:
        # the records the principal may read (write) the field on, when its
        # verdict is record-level; None when it is the same on every record
        classes = field.access_classes
        if classes is None or self.env.su:
            return None
        return self.env.registry.access_policy.field_domain(
            self.env, self._name, classes, operation
        )

    def _field_empty_value(self, field: Field[typing.Any]) -> typing.Any:
        # what a masked field reads as on the records of self: its empty value,
        # an empty recordset for a relational one
        return field.convert_to_record(
            field.convert_to_cache(False, self, validate=False), self
        )

    def _filtered_field_access(
        self,
        field: Field[typing.Any],
        operation: typing.Literal["read", "write"] = "read",
    ) -> Self:
        # the records of self the principal may read (write) the field on;
        # the model-level verdict is the caller's to ask first
        outside = self._field_access_outside(field, operation)
        if not outside:
            return self
        return self.browse(
            [id_ for id_ in self._ids if id_ not in outside]
        ).with_prefetch(self._prefetch_ids)

    def _check_field_access_records(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> None:
        outside = self._field_access_outside(field, operation)
        if not outside:
            return
        _debug.logic(
            "access.field_denied_on_records",
            model=self._name,
            field=field.name,
            operation=operation,
            uid=self.env.uid,
            records=len(outside),
        )
        raise AccessError(
            self.env._(
                'You may not %(operation)s the field "%(field)s" on these records'
                " of %(model)s: %(records)s.",
                operation=operation,
                field=field.name,
                model=self._name,
                records=", ".join(map(str, list(outside)[:10])),
            )
        )

    def _field_masked_ids(self, field: Field[typing.Any]) -> set[IdType] | None:
        # the records of self the principal may not read the field on, when
        # its verdict is record-level
        outside = self._field_access_outside(field, "read")
        return None if outside is None else set(outside)

    def _field_access_outside(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> dict[IdType, None] | None:
        # the ids of self (in order) the principal may not read (write) the
        # field on; None when its verdict is the same on every record
        domain = self._field_access_domain(field, operation)
        if domain is None or not self._ids:
            return None
        env = self.env
        verdicts = env.transaction.access_memo.domain_verdicts(env, self._name, domain)
        if verdicts is not None:
            try:
                return dict.fromkeys(id_ for id_ in self._ids if not verdicts[id_])
            except KeyError:
                within = self._judge_field_domain(domain, verdicts)
        else:
            within = set(self.sudo().filtered_domain(domain)._ids)
        return dict.fromkeys(id_ for id_ in self._ids if id_ not in within)

    def _judge_field_domain(
        self, domain: Domain, verdicts: RecordVerdicts
    ) -> Collection[IdType]:
        # the ids of self within the domain. The real records not judged yet
        # are judged at once with as many of the prefetch set as a fetch
        # takes, and kept; a new record is judged on its values of the moment
        env = self.env
        ids = self._ids
        batch = dict.fromkeys(id_ for id_ in ids if id_ and id_ not in verdicts)
        asked = len(batch)
        for id_ in self._prefetch_ids:
            if len(batch) >= PREFETCH_MAX:
                break
            if id_ and id_ not in verdicts:
                batch[id_] = None
        within: set[IdType] = set()
        if batch:
            with _debug.perf(
                "access.field_domain_judged", model=self._name, uid=env.uid
            ) as span:
                try:
                    within = self._ids_within(domain, tuple(batch))
                except MissingError:
                    if len(batch) == asked:
                        raise
                    # a record of the prefetch set is gone: self's, as asked
                    batch = dict.fromkeys(tuple(batch)[:asked])
                    within = self._ids_within(domain, tuple(batch))
                span.set(asked=asked, judged=len(batch), within=len(within))
            memo = env.transaction.access_memo
            if memo.domain_verdicts(env, self._name, domain) is not verdicts:
                # judging recomputed a value the domain reads, which dropped
                # the verdicts read before it: self is judged whole, none kept
                return self._ids_within(domain, ids)
            for id_ in batch:
                verdicts[id_] = id_ in within
        if new_ids := tuple(id_ for id_ in ids if not id_):
            within.update(self._ids_within(domain, new_ids))
        within.update(id_ for id_ in ids if id_ and verdicts.get(id_))
        return within

    def _ids_within(self, domain: Domain, ids: tuple[IdType, ...]) -> set[IdType]:
        return set(self.browse(ids).sudo().filtered_domain(domain)._ids)

    def _check_field_access(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> None:
        if self._has_field_access(field, operation):
            return

        _logger.info(
            "Access Denied by ACLs for operation: %s, uid: %s, model: %s, field: %s",
            operation,
            self.env.uid,
            self._name,
            field.name,
        )
        _debug.logic(
            "access.field_denied",
            model=self._name,
            field=field.name,
            operation=operation,
            uid=self.env.uid,
            groups=field.groups,
            write_groups=bool(field.write_groups),
        )

        description = self.env.registry.metaschema.model_description(
            self.env, self._name
        )

        error_msg = self.env._(
            'You do not have enough rights to access the field "%(field)s"'
            " on %(document_kind)s (%(document_model)s). "
            "Please contact your system administrator."
            "\n\nOperation: %(operation)s",
            field=field.name,
            document_kind=description,
            document_model=self._name,
            operation=operation,
        )

        if self.env.user._has_group("base.group_no_one"):
            error_msg += self.env._(
                "\nUser: %(user)s\nGroups: %(allowed_groups_msg)s",
                user=self.env.uid,
                allowed_groups_msg=self._get_field_access_message(field, operation),
            )

        raise AccessError(error_msg)

    @api.model
    def _get_field_access_message(
        self, field: Field[typing.Any], operation: typing.Literal["read", "write"]
    ) -> str:
        if field.groups == NO_ACCESS:
            return self.env._("always forbidden")

        messages = []
        classes = field.access_classes
        keys = () if classes is None else classes.read
        if operation == "write" and classes is not None:
            keys = classes.write
        named = [key for key in keys if not is_anonymous(key)]
        if named:
            messages.append(self.env._("classes %(classes)s", classes=", ".join(named)))
        if field.groups:
            messages.append(self._get_group_spec_message(field.groups))
        if operation == "write" and field.write_groups:
            if field.write_groups == NO_ACCESS:
                messages.append(self.env._("write always forbidden"))
            elif callable(field.write_groups):
                messages.append(self.env._("write gated by a field predicate"))
            else:
                messages.append(
                    self.env._(
                        "write %(spec)s",
                        spec=self._get_group_spec_message(field.write_groups),
                    )
                )
        if not messages:
            return self.env._("custom field access rules")
        return ", ".join(messages)

    @api.model
    def _get_group_spec_message(self, group_spec: str) -> str:
        groups_list = []
        missing_xmlids = []
        for xmlid in group_spec.split(","):
            group = self.env.ref(xmlid.strip(), raise_if_not_found=False)
            if group is not None and group._name == "res.groups":
                groups_list.append(group)
            else:
                missing_xmlids.append(xmlid.strip())
        groups = self.env["res.groups"].union(*groups_list).sorted("id")
        if _debug.logic.enabled and missing_xmlids:
            _debug.logic(
                "access.group_spec_unresolved",
                model=self._name,
                spec=group_spec,
                missing=missing_xmlids,
            )
        return self.env._(
            "allowed for groups %s",
            ", ".join([repr(g.display_name) for g in groups] + missing_xmlids),
        )

    def check_access(self, operation: str) -> None:
        if self.env.su:
            return
        if result := self._check_access(operation):
            raise result[1]()  # noqa: RSE102  result[1] builds the exception, it is not the class
        if self.env.privileges and operation != "read" and self._ids:
            self.env.registry.access_policy.note_privileged(
                self.env, self._name, operation, self._ids
            )

    def has_access(self, operation: str) -> bool:
        return self.env.su or not self._check_access(operation)

    def _filtered_access(self, operation: str) -> Self:
        if self and not self.env.su and (result := self._check_access(operation)):
            return self - result[0]
        return self

    def _get_display_name_visible_ids(self) -> set[int]:
        return set()

    def _filtered_display_name_access(self) -> Self:
        readable = self._filtered_access("read")
        hidden = self - readable
        if not hidden:
            return readable
        visible_ids = hidden._get_display_name_visible_ids() & set(hidden._ids)
        allowed_ids = set(readable._ids) | visible_ids
        _debug.logic(
            "access.display_name_filtered",
            model=self._name,
            uid=self.env.uid,
            records=len(self),
            hidden=len(hidden),
            visible_by_name=len(visible_ids),
        )
        return self.browse(id_ for id_ in self._ids if id_ in allowed_ids)

    def _visible_display_names(self) -> dict[IdType, str | None]:
        # each of these existing records' display name where the current user
        # may see it, None where it is withheld: one access decision for the
        # batch, so one unreadable record never sends the rest one by one
        named = self._filtered_display_name_access()
        names = dict(zip(named._ids, named.sudo().mapped("display_name"), strict=True))
        return {id_: names.get(id_) for id_ in self._ids}

    def _check_access(
        self, operation: str
    ) -> tuple[Self, Callable[[], Exception]] | None:
        env = self.env
        policy = env.registry.access_policy
        if not self._ids:
            if policy.model_allowed(env, self._name, operation):
                return None
            return self._model_denied(operation)
        memo = env.transaction.access_memo
        cache = operation == "read" and not env.su
        verdicts = memo.cached_verdicts(env, self._name) if cache else None
        if verdicts and verdicts.get(0):
            if all(map(verdicts.get, filter(None, self._ids))):
                return None
        elif not policy.model_allowed(env, self._name, operation):
            return self._model_denied(operation)
        elif cache:
            verdicts = memo.read_verdicts(env, self._name)
            verdicts[0] = True

        # keep the prefetch ids: the rules' Python evaluation on one record
        # of a batch would otherwise fetch that record's row alone
        real_ids = tuple(id_ for id_ in self._ids if id_)
        if verdicts is not None:
            unknown = tuple(id_ for id_ in real_ids if id_ not in verdicts)
            refused = [id_ for id_ in real_ids if verdicts.get(id_) is False]
        else:
            unknown, refused = real_ids, []
        if unknown:
            unknown_self = (
                self
                if len(unknown) == len(self._ids)
                else self._spawn(env, unknown, self._prefetch_ids)
            )
            domain = policy.record_domain(env, self._name, operation)
            admitted: Collection[IdType] = unknown
            if domain:
                self._flush_access_facts(domain, cache)
                candidates = unknown_self.sudo().with_context(active_test=False)
                try:
                    admitted = set(candidates.filtered_domain(domain)._ids)
                except MissingError:
                    if self._auto:
                        raise
                    # a query-backed model may show each principal other rows
                    # (a report joining the companies in use): a row missing
                    # from the principal's view is refused, not read
                    admitted = set(candidates.exists().filtered_domain(domain)._ids)
                refused.extend(id_ for id_ in unknown if id_ not in admitted)
            if verdicts is not None:
                for id_ in unknown:
                    verdicts[id_] = id_ in admitted
        if refused:
            refused_ids = set(refused)
            forbidden = self.browse(
                dict.fromkeys(id_ for id_ in real_ids if id_ in refused_ids)
            )
            _debug.logic(
                "access.denied_by_rule",
                model=self._name,
                operation=operation,
                uid=env.uid,
                records=len(real_ids),
                forbidden=len(forbidden),
            )
            return forbidden, functools.partial(
                policy.record_denied_error, env, operation, forbidden
            )

        return None

    def _model_denied(self, operation: str) -> tuple[Self, Callable[[], Exception]]:
        env = self.env
        if _debug.logic.enabled:
            _debug.logic(
                "access.denied_by_acl",
                model=self._name,
                operation=operation,
                uid=env.uid,
                records=len(self),
            )
        return self, functools.partial(
            env.registry.access_policy.model_denied_error, env, self._name, operation
        )

    def _flush_access_facts(self, domain: Domain, cached: bool) -> None:
        # the rule is judged against the cache, and a stored field that depends
        # on context caches a pending write under the context that made it: a
        # principal reading from another context would see the flushed row.
        # Only those fields are flushed; any other pending write is visible
        # from every context already.
        env = self.env
        facts = (
            env.transaction.access_memo.read_facts(env, self._name)
            if cached
            else env.transaction.access_memo.domain_facts(env[self._name], domain)
        )
        if not facts:
            return
        by_context = env.registry.field_depends_context
        by_model: dict[str, list[str]] = {}
        for model_name, fname in facts:
            field = env[model_name]._fields[fname]
            if field.store and by_context.get(field):
                by_model.setdefault(model_name, []).append(fname)
        for model_name, fnames in by_model.items():
            env[model_name].flush_model(fnames)

    @api.model
    @ormcache("operation", "self.env.registry.access_policy.access_signature(self.env)")
    def _access_verdict(self, operation: str) -> bool:
        # the model-level answer for every principal of one signature, kept
        # for the registry as long as the domains it is read from
        return self.sudo(False)._access_allowed(operation)

    @api.model
    def _access_allowed(self, operation: str) -> bool:
        # the model-level answer: the principal holds a permission whose
        # domain can hold, with any 'access' condition resolved for it
        if self.env.su:
            return True
        domain = self._access_domain(operation)
        if domain.is_false():
            return False
        if not any(c.operator == "access" for c in domain.iter_conditions()):
            return True
        model = typing.cast("BaseModel", self.sudo())

        def resolve(condition: DomainCondition) -> Domain:
            if condition.operator != "access":
                return condition
            return condition._optimize(model, OptimizationLevel.DYNAMIC_VALUES)

        return not domain.map_conditions(resolve).optimize(model).is_false()

    @api.model
    @ormcache("operation", "self.env.registry.access_policy.access_signature(self.env)")
    def _access_domain(self, operation: str) -> Domain:
        # the records the principal may perform the operation on, from
        # ir.access: the OR of the permissions its groups hold, AND every guard
        # that binds it (all principals, or the members of the guard's group),
        # AND what each delegated parent allows through the delegate
        env = self.env
        if env.su and env.uid != SUPERUSER_ID:
            # the principal's domain whatever the caller's privilege: under
            # sudo a parent's access reads TRUE, and the cache, keyed on the
            # principal alone, would serve that to the unprivileged caller
            return self.sudo(False)._access_domain(operation)
        policy = env.registry.access_policy
        if operation not in ACCESS_OPERATIONS:
            verb = env.registry.model_verbs.get(self._name, {}).get(operation)
            if verb is None:
                raise ValueError(
                    f"Invalid access operation {operation!r}: expected one of "
                    f"{ACCESS_OPERATIONS} or a verb {self._name} declares."
                )
            permissions, guards = policy.bound_access_rows(env, self._name, operation)
            if not permissions:
                return Domain.FALSE
            return (
                Domain.OR(permissions)
                & Domain.AND(guards)
                & self._access_domain(verb.requires)
            )
        parents: list[Domain] = []
        if self._inherits_rules:
            for parent_model_name, parent_field_name in self._inherits.items():
                delegate = self._fields[parent_field_name]
                if not delegate.store and operation == "create":
                    # a computed delegate is settled after the row is inserted;
                    # the parent's own create checked the parent's access
                    continue
                if not (delegate.store or delegate.search or delegate.related):
                    raise ValueError(
                        f"{delegate} delegates {self._name} to {parent_model_name} "
                        f"without a column or a search: the parent's access "
                        f"cannot bind through it. Give it a search method, or "
                        f"set _inherits_rules = False and state what replaces it."
                    )
                parent_domain = policy.record_domain(env, parent_model_name, operation)
                if parent_domain.is_false():
                    return Domain.FALSE
                if not parent_domain.is_true():
                    parents.append(Domain(parent_field_name, "any", parent_domain))

        permissions, guards = policy.bound_access_rows(env, self._name, operation)
        _debug.logic(
            "access.domain_computed",
            model=self._name,
            operation=operation,
            uid=env.uid,
            permissions=len(permissions),
            guards=len(guards),
            parents=len(parents),
        )
        if not permissions:
            return Domain.FALSE
        if self._access_label_field:
            guards.append(self._access_label_guard(operation))
        return Domain.OR(permissions) & Domain.AND(
            [*guards, *parents, self._access_guard(operation)]
        )

    @api.model
    def _access_label_guard(self, operation: str) -> Domain:
        # a record labelled with a class reaches the principals that class
        # grants: to read it, reading the class; to change it, writing it. An
        # unlabelled record is left to the rows
        label = self._access_label_field or ""
        field = self._fields.get(label)
        if field is None or field.comodel_name != "ir.access.class":
            raise ValueError(
                f"{self._name}._access_label_field names {label!r}, which is not "
                f"a many2one to ir.access.class"
            )
        class_operation = "read" if operation == "read" else "write"
        return self.env.registry.access_policy.label_domain(
            self.env, self._name, label, class_operation
        )

    @api.model
    def _access_company_anchor(self) -> str | None:
        # the field whose company a record belongs to, which a grant limited
        # to some companies compiles against: declared in _access_anchors, or
        # the model's own company_id / company_ids; None for a model whose
        # records belong to no company
        anchor = self.env.registry.model_anchors.get(self._name, {}).get("company")
        return anchor.path if anchor else None

    def _verb_door(self, verb: str, call: Callable[[Self], typing.Any]) -> typing.Any:
        # a door of the verb: the principal must hold it, what it obliges is
        # asked, and the call runs admitted for its records
        self.check_access(verb)
        return self.env.registry.access_policy.verb_door(self.env, self, verb, call)

    def _verb_checkpoint(self, verb: str) -> tuple[int, ...]:
        # a funnel every door of the verb passes: what no door admitted is
        # checked here, and can be refused but never asked
        env = self.env
        admitted = env.transaction.admitted_ids(self._name, verb)
        pending = self.browse([id_ for id_ in self._ids if id_ not in admitted])
        if not pending:
            return ()
        pending.check_access(verb)
        env.registry.access_policy.verb_checkpoint(env, pending, verb)
        return pending._ids

    def _check_verb_transitions(
        self, vals: dict[str, typing.Any], transitions: VerbTransitions
    ) -> list[tuple[str, tuple[int, ...]]]:
        moves: list[tuple[str, tuple[int, ...]]] = []
        for fname, verbs in transitions.items():
            if fname not in vals:
                continue
            field = self._fields[fname]
            target = field.convert_to_cache(vals[fname], self, validate=False)
            before = {
                record.id: field.convert_to_cache(record[fname], record, validate=False)
                for record in self
            }
            for name, verb in verbs:
                moved = tuple(
                    id_ for id_, value in before.items() if verb.moves(value, target)
                )
                if moved:
                    self.browse(moved)._verb_checkpoint(name)
                    moves.append((name, moved))
        return moves

    def _anchors_before_write(
        self, vals: dict[str, typing.Any]
    ) -> dict[str, dict[int, typing.Any]] | None:
        env = self.env
        if env.su or not self._ids:
            return None
        moving = env.registry.moving_anchor_fields.get(self._name)
        if not moving:
            return None
        fnames = [
            fname for fname, triggers in moving.items() if not triggers.isdisjoint(vals)
        ]
        if not fnames:
            return None
        records = self.sudo().filtered("id")
        return {
            fname: {
                record.id: self._fields[fname].convert_to_cache(
                    record[fname], record, validate=False
                )
                for record in records
            }
            for fname in fnames
        }

    def _check_anchor_moves(self, before: dict[str, dict[int, typing.Any]]) -> None:
        # a write that moves a record to another owner, team or company is
        # judged where it lands, since an "own" row is judged on the record
        # before the write: a record still within the writer's write
        # permissions has not left their reach, and one that has is admitted
        # only where the writer could have made it. The guards stay out: they
        # state what writing or creating needs beside whose the record is
        env = self.env
        records = self.sudo()
        moved = sorted(
            {
                id_
                for fname, values in before.items()
                for id_, value in values.items()
                if self._fields[fname].convert_to_cache(
                    records.browse(id_)[fname], records.browse(id_), validate=False
                )
                != value
            }
        )
        if not moved:
            return
        policy = env.registry.access_policy
        permissions = [
            domain
            for operation in ("write", "create")
            for domain in policy.bound_access_rows(env, self._name, operation)[0]
        ]
        admitted: set[int] = set()
        if permissions:
            domain = Domain.OR(permissions)
            self._flush_access_facts(domain, False)
            admitted = set(
                records.browse(moved)
                .with_context(active_test=False)
                .filtered_domain(domain)
                ._ids
            )
        refused = [id_ for id_ in moved if id_ not in admitted]
        _debug.logic(
            "anchor_moved",
            model=self._name,
            uid=env.uid,
            fields=sorted(before),
            moved=len(moved),
            refused=len(refused),
        )
        if refused:
            raise policy.record_denied_error(env, "create", self.browse(refused))

    def _land_verb_transitions(self, moves: list[tuple[str, tuple[int, ...]]]) -> None:
        # what each obligation does once the move it checked has landed, for
        # every record that moved, admitted or not
        env = self.env
        for name, ids in moves:
            env.registry.access_policy.verb_landed(env, self.browse(ids), name)

    def _check_verb_creations(self, transitions: VerbTransitions) -> None:
        for fname, verbs in transitions.items():
            field = self._fields[fname]
            initial = field.convert_to_cache(
                field.default(self) if field.default else False,
                self,
                validate=False,
            )
            after = {
                record.id: field.convert_to_cache(record[fname], record, validate=False)
                for record in self
            }
            for name, verb in verbs:
                if not verb.at_create:
                    continue
                created = [
                    id_ for id_, value in after.items() if verb.moves(initial, value)
                ]
                if created:
                    self.browse(created)._verb_checkpoint(name)

    @api.model
    def _access_guard(self, operation: str) -> Domain:
        # what the model itself requires of every principal beside its rows,
        # typically an 'access' condition on the record it belongs to; read
        # with the rows, it is what the model-level answer, the searches and
        # the error that names the groups that would be allowed all see
        return Domain.TRUE

    def _note_readable(self) -> None:
        # the records a user's search or fetch returned passed the read rules
        env = self.env
        if env.su or not self._ids:
            return
        verdicts = env.transaction.access_memo.read_verdicts(env, self._name)
        for id_ in self._ids:
            verdicts[id_] = True

    def _check_company_domain(self, companies: typing.Any) -> Domain:
        if not companies:
            return Domain("company_id", "=", False)
        if isinstance(companies, unquote):
            return Domain("company_id", "in", unquote(f"{companies} + [False]"))
        return Domain("company_id", "in", to_record_ids(companies) + [False])

    def _get_company_check_candidates(
        self, regular_fields: list[str], property_fields: list[str]
    ) -> dict[
        tuple[str, tuple[int, ...]], list[tuple[int, ModelLike, BaseModel, typing.Any]]
    ]:
        groups: dict[
            tuple[str, tuple[int, ...]],
            list[tuple[int, ModelLike, BaseModel, typing.Any]],
        ] = defaultdict(list)
        property_company = self.env.company
        width = len(regular_fields) + len(property_fields)
        scopes = [(regular_fields, None), (property_fields, property_company)]

        for record_index, record_su in enumerate(self.sudo()):
            record = record_su.sudo(self.env.su)
            offset = 0
            for names, fixed_companies in scopes:
                if fixed_companies is None and names:
                    companies = (
                        record
                        if self._name == "res.company"
                        else record["company_id"]
                        if "company_id" in self
                        else record["company_ids"]
                    )
                else:
                    companies = fixed_companies
                for position, name in enumerate(names):
                    corecords = record_su[name]
                    if corecords:
                        groups[(name, tuple(companies.ids))].append(
                            (
                                record_index * width + offset + position,
                                record,
                                corecords,
                                companies,
                            )
                        )
                offset += len(names)
        _debug.pipeline(
            "access.company_candidates",
            model=self._name,
            records=len(self),
            regular_fields=len(regular_fields),
            property_fields=len(property_fields),
            groups=len(groups),
        )
        return groups

    def _get_company_violations(
        self,
        groups: dict[
            tuple[str, tuple[int, ...]],
            list[tuple[int, ModelLike, BaseModel, typing.Any]],
        ],
    ) -> Iterator[tuple[int, ModelLike, str, BaseModel]]:
        # one fetch per comodel, not one per field: stock's customer and
        # vendor locations are two fields on the same comodel
        prefetch: defaultdict[str, dict[IdType, None]] = defaultdict(dict)
        for entries in groups.values():
            for entry in entries:
                prefetch[entry[2]._name].update(dict.fromkeys(entry[2]._ids))
        for (name, _companies_ids), entries in groups.items():
            companies = entries[0][3]
            comodel = entries[0][2].browse()
            all_corecords = comodel.union(*(entry[2] for entry in entries))
            all_corecords = all_corecords.with_prefetch(tuple(prefetch[comodel._name]))
            domain = all_corecords._check_company_domain(companies)
            if not domain:
                continue
            allowed = set(
                all_corecords.with_context(active_test=False)
                .filtered_domain(domain)
                ._ids
            )
            for rank, record, corecords, _companies in entries:
                if not allowed.issuperset(corecords._ids):
                    yield rank, record, name, corecords

    def _check_company(self, fnames: Collection[str] | None = None) -> None:
        if fnames is None or "company_id" in fnames or "company_ids" in fnames:
            fnames = self._fields

        regular_fields = []
        property_fields = []
        for name in fnames:
            field = self._fields[name]
            if field.relational and field.check_company:
                if not field.company_dependent:
                    regular_fields.append(name)
                else:
                    property_fields.append(name)

        if not (regular_fields or property_fields):
            return

        if regular_fields and not (
            self._name == "res.company" or "company_id" in self or "company_ids" in self
        ):
            _logger.warning(
                "Skipping a company check for model %s. Its fields %s "
                "are set as company-dependent, but the model doesn't "
                "have a `company_id` or `company_ids` field!",
                self._name,
                regular_fields,
            )
            _debug.logic(
                "access.company_check_skipped",
                model=self._name,
                fields=regular_fields,
                reason="no_company_field",
            )
            return

        candidates = self._get_company_check_candidates(regular_fields, property_fields)
        inconsistencies = [
            (record, name, corecords)
            for _rank, record, name, corecords in sorted(
                self._get_company_violations(candidates), key=itemgetter(0)
            )
        ]

        if inconsistencies:
            _debug.logic(
                "access.company_inconsistent",
                model=self._name,
                records=len(self),
                violations=len(inconsistencies),
                fields=sorted({name for _record, name, _co in inconsistencies}),
            )
            lines = [self.env._("Uh-oh! You've got some company inconsistencies here:")]
            company_msg = _lt(
                "- Record is company \u201c%(company)s\u201d while \u201c%(field)s\u201d (%(fname)s: %(values)s) belongs to another company."
            )
            record_msg = _lt(
                "- \u201c%(record)s\u201d belongs to company \u201c%(company)s\u201d while \u201c%(field)s\u201d (%(fname)s: %(values)s) belongs to another company."
            )
            root_company_msg = _lt(
                "- Only a root company can be set on \u201c%(record)s\u201d. Currently set to \u201c%(company)s\u201d"
            )
            for record, name, corecords in inconsistencies[:5]:
                if record._name == "res.company":
                    msg, companies = company_msg, record
                elif record == corecords and name == "company_id":
                    msg, companies = root_company_msg, record["company_id"]
                else:
                    msg = record_msg
                    companies = (
                        record["company_id"]
                        if "company_id" in record
                        else record["company_ids"]
                    )
                field_string = self.env.registry.metaschema.field_strings(
                    self.env, self._name
                ).get(name, self._fields[name].string)
                lines.append(
                    str(msg)
                    % {
                        "record": record.display_name,
                        "company": ", ".join(
                            company.display_name or "" for company in companies
                        ),
                        "field": field_string,
                        "fname": name,
                        "values": ", ".join(
                            repr(rec.display_name) for rec in corecords
                        ),
                    }
                )
            lines.append(
                self.env._("To avoid a mess, no company crossover is allowed!")
            )
            raise UserError("\n".join(lines))
