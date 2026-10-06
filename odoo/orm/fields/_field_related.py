import logging
import typing

from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog

from .._recordset import is_recordset
from ..domain import Domain
from ..primitives import COLLECTION_TYPES
from ._field_sql import PYTHON_INEQUALITY_OPERATOR

if typing.TYPE_CHECKING:
    from types import NotImplementedType

    from .._typing import BaseModel, DomainType, IdType
    from .base import Field

_logger = logging.getLogger("odoo.fields")
_debug = DebugLog(__name__)


def setup_related(field: Field[typing.Any], model: BaseModel) -> None:
    assert isinstance(field.related, str), field.related

    field._related_names = related_names = tuple(field.related.split("."))

    field_seq: list[Field[typing.Any]] = []
    model_name = field.model_name
    for depth, name in enumerate(related_names, start=1):
        step = model.pool[model_name]._fields.get(name)
        if step is None:
            raise KeyError(
                f"Field {name} referenced in related field definition {field} does not exist."
            )
        if not step._setup_done:
            _debug.logic(
                "field.related.step_setup_forced",
                model=field.model_name,
                field=field.name,
                step=f"{model_name}.{name}",
            )
            step.setup(model.env[model_name])
        field_seq.append(step)
        if depth < len(related_names):
            if step.comodel_name is None:
                raise TypeError(
                    f"Field {step} in related field definition {field} is not "
                    f"relational, so {related_names[depth]} cannot be reached "
                    f"through it."
                )
            model_name = step.comodel_name

    field._related_field_seq = tuple(field_seq)
    related_field = field_seq[-1]

    # A one2one reads as one record, so a many2one may end on it.
    reads_one = field.is_many2one and related_field.is_one2one
    if _debug.logic.enabled and reads_one:
        _debug.logic(
            "field.related.many2one_over_one2one",
            model=field.model_name,
            field=field.name,
            target=str(related_field),
        )
    if field.type != related_field.type and not reads_one:
        raise TypeError(
            f"Type of related field {field} is inconsistent with {related_field}"
        )

    field.related_field = related_field
    # the join reads the parent's column under the child row's access, which
    # binds the parent's rules unless the model opts out: a sudo field there
    # would refuse what it is declared to read
    field.joins_delegation = field.inherited and not model._inherits_rules
    if field.inherited and field.fetched_with_row and not field.manual:
        # decided before the target was known: a delegated column travels
        # with the row like a stored one
        field.prefetch = True

    model.pool.field_setup_dependents.add(related_field, field)

    field.compute = field._compute_related
    if field.inherited or not (field.readonly or related_field.readonly):
        field.inverse = field._inverse_related
    if not field.store and all(f._description_searchable for f in field_seq):
        field.search = field._search_related
    _debug.logic(
        "field.related.setup",
        model=field.model_name,
        field=field.name,
        path=field.related,
        depth=len(related_names),
        inverse=field.inverse is not None,
        search=field.search is not None,
        store=field.store,
        inherited=field.inherited,
    )

    if field.default and field.readonly and not field.inverse:
        _logger.warning("Redundant default on %s", field)

    propagate_related_attrs(field, model, related_field)

    if field.inherited:
        field.inherited_field = related_field
        if related_field.required:
            field.required = True
        delegate_field = model._fields[related_names[0]]
        field._modules = tuple(
            {*field._modules, *delegate_field._modules, *related_field._modules}
        )


def propagate_related_attrs(
    field: Field[typing.Any], model: BaseModel, related_field: Field[typing.Any]
) -> None:
    for attr, prop in field.related_attrs:
        if attr not in field.__dict__:
            setattr(field, attr, getattr(related_field, prop))

    for attr in related_field._extra_keys__:
        if not hasattr(field, attr) and model._is_valid_field_parameter(field, attr):
            setattr(field, attr, getattr(related_field, attr))


def traverse_related(
    field: Field[typing.Any], record: BaseModel
) -> tuple[BaseModel, Field[typing.Any]]:
    for name in field._related_names[:-1]:
        corecord = record[name]
        record = next(iter(corecord), corecord)
    return record, field.related_field


def compute_related(field: Field[typing.Any], records: BaseModel) -> None:
    values = list(records)
    for name in field._related_names[:-1]:
        try:
            values = [next(iter(val := value[name]), val) for value in values]
        except AccessError as e:
            description = records.env.registry.metaschema.model_description(
                records.env, records._name
            )
            env = records.env
            _debug.logic(
                "field.related.access_denied_through",
                model=field.model_name,
                field=field.name,
                step=name,
                records=len(records),
            )
            raise AccessError(
                env._(
                    "%(previous_message)s\n\nImplicitly accessed through '%(document_kind)s' (%(document_model)s).",
                    previous_message=e.args[0],
                    document_kind=description,
                    document_model=records._name,
                )
            ) from e
    # one assignment per distinct value; a monetary rounds per record's
    # currency and an x2many assigns commands, so only their empty value is
    # shared
    groupable = not (field.is_monetary or field.is_x2many)
    groups: dict[tuple[type[object], typing.Any], tuple[typing.Any, list[IdType]]] = {}
    ungrouped = 0  # debuglog
    related_name = field.related_field.name
    for record, value in zip(records, values, strict=True):
        processed = field._process_related(value[related_name], record.env)
        if groupable or not processed:
            try:
                group = groups.setdefault((type(processed), processed), (processed, []))
            except TypeError:
                pass
            else:
                group[1].append(record.id)
                continue
        ungrouped += 1  # debuglog
        record[field.name] = processed
    for processed, ids in groups.values():
        records.browse(ids)[field.name] = processed
    _debug.pipeline(
        "field.related.computed",
        model=field.model_name,
        field=field.name,
        records=len(records),
        groups=len(groups),
        ungrouped=ungrouped,
    )


def inverse_related(field: Field[typing.Any], records: BaseModel) -> None:
    record_value = {record: record[field.name] for record in records}
    latest: dict[
        tuple[str, IdType, str], tuple[BaseModel, Field[typing.Any], typing.Any]
    ] = {}
    for record in records:
        target, target_field = field.traverse_related(record)
        if target and bool(target.id) == bool(record.id):
            latest[target._name, target.id, target_field.name] = (
                target,
                target_field,
                record_value[record],
            )

    groups: dict[
        tuple[str, str, str, typing.Any],
        tuple[BaseModel, Field[typing.Any], typing.Any, list[IdType]],
    ] = {}
    ungrouped: list[tuple[BaseModel, Field[typing.Any], typing.Any]] = []
    for target, target_field, value in latest.values():
        key = (
            target._name,
            target_field.name,
            type(value).__name__,
            value._ids if is_recordset(value) else value,
        )
        try:
            hash(key)
        except TypeError:
            ungrouped.append((target, target_field, value))
            continue
        if key in groups:
            groups[key][3].append(target.id)
        else:
            groups[key] = (target, target_field, value, [target.id])

    _debug.pipeline(
        "field.related.inversed",
        model=field.model_name,
        field=field.name,
        records=len(records),
        targets=len(latest),
        groups=len(groups),
        ungrouped=len(ungrouped),
    )
    as_owner = field.inherited and field.compute_sudo and not field.is_x2many
    for target, target_field, value, ids in groups.values():
        target = target.browse(ids)
        (target.sudo() if as_owner else target)[target_field.name] = value
    for target, target_field, value in ungrouped:
        (target.sudo() if as_owner else target)[target_field.name] = value


def _holds_on_missing_step(
    field: Field[typing.Any], records: BaseModel, operator: str, value: typing.Any
) -> bool:
    # a record whose path stops at an empty many2one or one2one reads the
    # field's falsy value, and a column holding that value answers as here
    positive = Domain.NEGATIVE_OPERATORS.get(operator, operator)
    falsy_value = field.falsy_value
    if pyop := PYTHON_INEQUALITY_OPERATOR.get(positive):
        if falsy_value is None:
            holds = False
        else:
            try:
                comparand = field._get_inequality_comparand(value, records)
                holds = bool(pyop(falsy_value, comparand))
            except ValueError, TypeError:
                holds = False
    elif isinstance(value, COLLECTION_TYPES):
        holds = any(val is False or val is None or val == falsy_value for val in value)
    else:
        holds = value is False or value is None or value == falsy_value
    return holds if positive == operator else not holds


def search_related(
    field: Field[typing.Any], records: BaseModel, operator: str, value: typing.Any
) -> DomainType | NotImplementedType:
    can_be_null = _holds_on_missing_step(field, records, operator, value)
    if operator in Domain.NEGATIVE_OPERATORS and can_be_null:
        # answered as the complement of the positive condition, which holds
        # where a step is empty exactly when this one does not
        _debug.logic(
            "field.related.search_unsupported",
            model=field.model_name,
            field=field.name,
            operator=operator,
        )
        unsupported: DomainType | NotImplementedType = NotImplemented
        return unsupported

    field_seq = field._related_field_seq
    domain = Domain(field_seq[-1].name, operator, value)
    null_steps = 0  # debuglog
    for step in reversed(field_seq[:-1]):
        domain = Domain(step.name, "any!" if field.compute_sudo else "any", domain)
        if can_be_null and (
            (step.is_many2one and not step.required) or step.is_one2one
        ):
            domain |= Domain(step.name, "=", False)
            null_steps += 1  # debuglog
    _debug.logic(
        "field.related.search_domain",
        model=field.model_name,
        field=field.name,
        operator=operator,
        steps=len(field_seq) - 1,
        sudo=bool(field.compute_sudo),
        null_steps=null_steps,
    )
    return domain
