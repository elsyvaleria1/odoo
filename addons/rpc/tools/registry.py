
import logging

from odoo.exceptions import AccessError
from odoo.libs.docstring import parse_signature, render_docstring
from odoo.service.model import get_public_method

logger = logging.getLogger(__name__)

RPC_RECORDSET_ANNOTATIONS = frozenset(
    {
        "Self",
        "typing.Self",
        "BaseModel",
        "Model",
        "models.BaseModel",
        "models.Model",
    }
)


def normalize_rpc_return(annotation):
    return "list[int]" if annotation in RPC_RECORDSET_ANNOTATIONS else annotation


def is_public_method(model, name) -> bool:
    try:
        method = get_public_method(model, name)
    except AttributeError, AccessError:
        return False
    return not hasattr(method, "__deprecated__")


def public_method_names(model) -> list:
    return [name for name in dir(model) if is_public_method(model, name)]


def _definers(model_cls, method_name) -> list:
    return [cls for cls in model_cls.__mro__ if method_name in cls.__dict__]


def _describing_docstring(definers, method_name):
    for cls in definers:
        if doc := getattr(cls, method_name).__doc__:
            return doc
    return None


def reflect_callable(method, docstring=None):
    signature = parse_signature(
        method, docstring=docstring, normalize_return=normalize_rpc_return
    )
    signature.api = _api_flags(method)
    return signature


def describe_method(model, method_name):
    model_cls = type(model)
    definers = _definers(model_cls, method_name)
    introducing = definers[-1] if definers else model_cls
    implementation = getattr(introducing, method_name)

    try:
        described = reflect_callable(
            implementation,
            docstring=_describing_docstring(definers, method_name),
        ).as_dict()
    except Exception as exc:
        logger.warning(
            "rpc/doc: could not reflect %s.%s (%s): %s",
            model._name,
            method_name,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        described = {
            "signature": "(...)",
            "parameters": {},
            "doc": f"Signature could not be introspected ({type(exc).__name__}: {exc}).",
        }

    return described | {
        "model": getattr(introducing, "_name", None) or "core",
        "module": getattr(introducing, "_module", None) or "core",
    }


def _api_flags(method):
    api = []
    if getattr(method, "_api_model", False):
        api.append("model")
    if getattr(method, "_readonly", False):
        api.append("readonly")
    return api


def describe_model_doc(model):
    for cls in type(model).__mro__:
        if getattr(cls, "_name", None) != model._name:
            continue
        if doc := cls.__dict__.get("__doc__"):
            return render_docstring(doc)
    return None
