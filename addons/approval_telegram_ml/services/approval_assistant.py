import json
import logging
from typing import TYPE_CHECKING, Any

from odoo import fields
from odoo.libs.json import loads as json_loads

from odoo.addons.integration_machine_learning.tools import MlRequest, get_router
from odoo.addons.speech_telegram.tools.assistant import BotAssistant

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_category import ApprovalCategory

_logger = logging.getLogger(__name__)

PURPOSE = "telegram.smart_approval"
TRANSCRIPTION_PURPOSE = "speech.transcription.approval"
_STRING = {"type": ["string", "null"]}
_NUMBER = {"type": ["number", "null"]}
_INTEGER = {"type": ["integer", "null"]}
_PAYMENT_KEYS = ("bank", "account", "clabe", "account_holder", "pay_from")
_ITEM_PROPERTIES = {
    "description": {"type": "string"},
    "quantity": _NUMBER,
    "price_unit": _NUMBER,
    "product_id": _INTEGER,
    "product_name": _STRING,
}
_CLASSIFICATION_PROPERTIES = {
    "category_id": {"type": "integer"},
    "confidence": {"type": "number"},
    "amount": _NUMBER,
    "partner_name": _STRING,
    "quantity": _NUMBER,
    "date": _STRING,
    "fiscal": {"type": ["boolean", "null"]},
    "items": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": _ITEM_PROPERTIES,
            "required": list(_ITEM_PROPERTIES),
            "additionalProperties": False,
        },
    },
    "reference": _STRING,
    "location": _STRING,
    "payment": {
        "type": "object",
        "properties": dict.fromkeys(_PAYMENT_KEYS, _STRING),
        "required": list(_PAYMENT_KEYS),
        "additionalProperties": False,
    },
    "reason": {"type": "string"},
}
CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": _CLASSIFICATION_PROPERTIES,
    "required": list(_CLASSIFICATION_PROPERTIES),
    "additionalProperties": False,
}

TRANSCRIBE_CONTEXT = "Transcripción de una solicitud de aprobación en Odoo AgroMarin."

_EXTRACTABLE_FIELDS = [
    ("has_amount", "monto"),
    ("has_partner", "contacto"),
    ("has_quantity", "cantidad"),
    ("has_date", "fecha"),
]


class ApprovalAssistant(BotAssistant):
    PURPOSE = PURPOSE
    TRANSCRIBE_CONTEXT = TRANSCRIBE_CONTEXT
    TRANSCRIPTION_PURPOSE = TRANSCRIPTION_PURPOSE
    SETTINGS = (
        "smart_approval_ai_enabled",
        "smart_approval_ai_provider_id",
        "smart_approval_ai_model_id",
    )

    def _chat_json(
        self, system: str, user: str, max_tokens: int, temperature: float
    ) -> str | None:
        try:
            result = get_router(self._env).run(
                "chat",
                MlRequest(
                    purpose=PURPOSE,
                    system=system,
                    prompt=user,
                    response_schema=CLASSIFICATION_SCHEMA,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ),
                model=self._chat_model(),
                company_id=self._company.id,
            )
        except Exception as error:
            _logger.warning(
                "%s returned no usable answer: %s", PURPOSE, error, exc_info=True
            )
            return None
        return json.dumps(result.data, ensure_ascii=False)

    def classify(
        self, narrative: str, categories: ApprovalCategory
    ) -> dict[str, Any] | None:
        if not self.available or not narrative or not categories:
            return None

        today = fields.Date.to_string(fields.Date.context_today(self._bot))
        raw = self._chat_json(
            self._get_system_prompt(categories, today),
            narrative,
            max_tokens=600,
            temperature=0.1,
        )
        if not raw:
            return None
        try:
            data = json_loads(raw)
        except ValueError:
            _logger.warning(
                "%s classification returned non-JSON: %s",
                self._label,
                raw[:200],
            )
            return None

        category_id = data.get("category_id")
        if category_id not in set(categories.ids):
            _logger.info(
                "%s returned out-of-range category_id %s",
                self._label,
                category_id,
            )
            return None

        try:
            confidence = float(data.get("confidence"))
        except TypeError, ValueError:
            confidence = 0.0

        fiscal = data.get("fiscal")
        if not isinstance(fiscal, bool):
            fiscal = None

        return {
            "category_id": category_id,
            "confidence": max(0.0, min(1.0, confidence)),
            "amount": data.get("amount"),
            "partner_name": data.get("partner_name"),
            "quantity": data.get("quantity"),
            "date": self._normalize_date(data.get("date")),
            "fiscal": fiscal,
            "items": self._normalize_items(data.get("items")),
            "reference": (data.get("reference") or "").strip() or None,
            "location": (data.get("location") or "").strip() or None,
            "payment": self._normalize_payment(data.get("payment")),
            "reason": (data.get("reason") or "").strip(),
        }

    _PAYMENT_KEYS = _PAYMENT_KEYS

    @classmethod
    def _normalize_payment(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        payment = {}
        for key in cls._PAYMENT_KEYS:
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                payment[key] = text.strip()
        return payment

    @staticmethod
    def _normalize_items(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items = []
        for entry in value:
            if not isinstance(entry, dict):
                continue
            description = (entry.get("description") or "").strip()
            if not description:
                continue
            product_id = entry.get("product_id")
            if not isinstance(product_id, int) or isinstance(product_id, bool):
                product_id = None
            items.append(
                {
                    "description": description,
                    "quantity": entry.get("quantity"),
                    "price_unit": entry.get("price_unit"),
                    "product_id": product_id,
                    "product_name": (entry.get("product_name") or "").strip() or None,
                }
            )
        return items

    @staticmethod
    def _normalize_date(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return fields.Date.to_string(fields.Date.to_date(value.strip()))
        except ValueError:
            return None

    @staticmethod
    def _get_system_prompt(categories: ApprovalCategory, today: str) -> str:
        lines = []
        for category in categories:
            fields_label = ApprovalAssistant._required_fields(category)
            description = (category.description or "").strip()
            line = f"- id={category.id} | {category.name}"
            if description:
                line += f" — {description}"
            if fields_label:
                line += f" | campos relevantes: {fields_label}"
            products_label = ApprovalAssistant._products_label(category)
            if products_label:
                line += f" | {products_label}"
            lines.append(line)
        return (
            "Eres un clasificador de solicitudes de aprobación para AgroMarin. "
            "Dada la descripción del usuario, elige la categoría MÁS adecuada de "
            "la lista según QUÉ se compra o gasta y su propósito, y extrae los "
            "campos que puedas inferir. Responde SOLO con JSON válido, sin texto "
            "extra.\n\n"
            "Guía para elegir categoría (usa el nombre/descripción más afín):\n"
            "- computadoras, laptops, impresoras, equipo de cómputo, monitores → "
            "categoría de hardware/cómputo/IT.\n"
            "- gasolina, casetas, viáticos, hospedaje, comidas de viaje → viajes "
            "o representación.\n"
            "- artículos de limpieza (jabón, cloro, escobas, trapeadores) → "
            "limpieza.\n"
            "- refacciones, llantas, aceite, reparación o mantenimiento de un "
            "vehículo → mantenimiento de vehículos.\n"
            "- insumos, materia prima o material que se compra a un proveedor "
            "(envases, garrafas, químicos, empaques) → compra/pago a proveedor.\n"
            "IMPORTANTE: si dudas entre dos categorías, pon 'confidence' por "
            "debajo de 0.7 para que el usuario elija manualmente.\n\n"
            "Categorías disponibles:\n"
            + "\n".join(lines)
            + "\n\n(* = campo requerido por la categoría)\n\n"
            f"La fecha de hoy es {today} (úsala como referencia). Para 'date': "
            "interpreta expresiones de tiempo en español y conviértelas a "
            "YYYY-MM-DD. Ejemplos: 'hoy' = la fecha de hoy; 'ayer' = un día "
            "antes; 'antier'/'anteayer' = dos días antes; 'el sábado'/'el "
            "sábado pasado' = el sábado más reciente ya transcurrido; 'el 12' o "
            "'el 12 de junio' = ese día del mes indicado (o del mes actual si "
            "no se especifica). Si no se menciona ninguna fecha, usa null.\n"
            "Para 'fiscal': true si hay o habrá factura/CFDI (compra formal a "
            "una empresa con comprobante fiscal); false si es sin factura (nota, "
            "informal, 'me lo vendió alguien', 'en la plaza'); null si no hay "
            "pistas suficientes.\n"
            "Para 'items': desglosa CADA producto o servicio comprado en una "
            "lista con su descripción, cantidad (quantity) y precio UNITARIO "
            "(price_unit, por pieza). Ejemplo: '2 computadoras de $23,000 cada "
            "una' -> quantity=2, price_unit=23000. Si solo hay un monto total "
            "sin desglose, devuelve un único item con quantity=1 y "
            "price_unit=el total.\n"
            "Para el 'product_id' de cada item: elige el id del producto MÁS "
            "adecuado de la lista 'productos válidos' de la categoría que "
            "elegiste (cada item puede tener un producto distinto: casetas vs "
            "comida vs gasolina). Si la categoría no lista productos, usa null.\n"
            "Para 'product_name' de cada item: el nombre del artículo tal como "
            "se menciona (ej. 'Garrafa ámbar 3800 ml R38'), para poder buscarlo "
            "en el catálogo.\n"
            "Para 'reference': una referencia corta o propósito (ej. número de "
            "orden de compra 'OC/...', folio, concepto).\n"
            "Para 'partner_name': el proveedor o beneficiario del pago. Si hay "
            "un bloque de datos bancarios del proveedor, usa el 'Nombre' del "
            "titular de la cuenta como proveedor.\n"
            "Para 'payment': si el mensaje incluye datos bancarios o de pago, "
            "extrae bank (banco), account (número de cuenta), clabe, "
            "account_holder (nombre del titular de la cuenta) y pay_from "
            "(empresa/persona/cuenta DESDE la que se paga, ej. 'Pagar desde "
            "X'). Cada campo null si no aparece.\n"
            "Para 'location': el lugar o destino si se menciona; si no, null.\n\n"
            "Formato de salida (JSON):\n"
            '{"category_id": <int de la lista>, "confidence": <0..1>, '
            '"amount": <number|null>, "partner_name": <string|null>, '
            '"quantity": <number|null>, "date": "<YYYY-MM-DD|null>", '
            '"fiscal": <true|false|null>, '
            '"items": [{"description": <string>, "quantity": <number>, '
            '"price_unit": <number>, "product_id": <int|null>, '
            '"product_name": "<string|null>"}], '
            '"reference": "<string|null>", "location": "<string|null>", '
            '"payment": {"bank": "<string|null>", "account": "<string|null>", '
            '"clabe": "<string|null>", "account_holder": "<string|null>", '
            '"pay_from": "<string|null>"}, '
            '"reason": "<resumen breve en español>"}'
        )

    @staticmethod
    def _products_label(category: ApprovalCategory) -> str:
        if category.has_product == "no" or not category.product_ids:
            return ""
        listed = ", ".join(
            f"[{product.id}] {product.display_name}" for product in category.product_ids
        )
        return f"productos válidos: {listed}"

    @staticmethod
    def _required_fields(category: ApprovalCategory) -> str:
        labels = []
        for field_name, label in _EXTRACTABLE_FIELDS:
            value = getattr(category, field_name, "no")
            if value == "required":
                labels.append(f"{label}*")
            elif value == "optional":
                labels.append(label)
        return ", ".join(labels)
