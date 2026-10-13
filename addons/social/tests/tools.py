from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from odoo.modules.registry import Registry
from odoo.tests.common import get_db_name


def _void(*args, **kwargs):
    return None


def _no_post_access(record):
    return False


EXTERNAL_CALLS = {
    "social_facebook": (
        ("social.account", "_update_statistics", _void),
        ("social.account", "_create_default_stream_facebook", _void),
        ("social.live.post", "_post_facebook", _void),
        ("social.stream", "_sync_stream_data", _void),
    ),
    "social_instagram": (
        ("social.account", "_update_statistics", _void),
        ("social.account", "_create_default_stream_instagram", _void),
        ("social.live.post", "_post_instagram", _void),
        ("social.post", "_check_post_access", _no_post_access),
        ("social.stream", "_sync_stream_data", _void),
    ),
    "social_linkedin": (
        ("social.account", "_update_statistics", _void),
        ("social.account", "_create_default_stream_linkedin", _void),
        ("social.live.post", "_post_linkedin", _void),
        ("social.stream", "_sync_stream_data", _void),
    ),
    "social_twitter": (
        ("social.account", "_update_statistics", _void),
        ("social.account", "_create_default_stream_twitter", _void),
        ("social.live.post", "_post_twitter", _void),
        ("social.stream", "_sync_stream_data", _void),
    ),
    "social_youtube": (
        ("social.account", "_create_default_stream_youtube", _void),
        ("social.live.post", "_post_youtube", _void),
        ("social.stream", "_sync_stream_data", _void),
    ),
}


def _definitions(registry, module, model, method):
    if model not in registry:
        return
    for cls in type.mro(registry[model]):
        if getattr(cls, "_module", None) == module and method in vars(cls):
            yield cls


@contextmanager
def mock_void_external_calls():
    registry = Registry(get_db_name())
    with ExitStack() as stack:
        for module, calls in EXTERNAL_CALLS.items():
            for model, method, replacement in calls:
                for cls in _definitions(registry, module, model, method):
                    stack.enter_context(patch.object(cls, method, replacement))
        yield
