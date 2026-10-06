from odoo.addons.ai.utils.llm_provider_handlers import register_provider_handler

from .anthropic_handler import AnthropicProviderHandler

register_provider_handler(AnthropicProviderHandler())
