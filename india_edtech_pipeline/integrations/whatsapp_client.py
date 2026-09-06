"""
whatsapp_client.py
Thin wrapper around Meta's WhatsApp Cloud API (Graph API) so the RAG /ask
pipeline can be reached over WhatsApp — the dominant channel for parents and
teachers in rural India, far more than a web app or a dedicated mobile app.
"""
import logging
import httpx

from config import WHATSAPP

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(self, config=WHATSAPP):
        self.access_token = config.access_token
        self.phone_number_id = config.phone_number_id
        self.base_url = f"https://graph.facebook.com/{config.graph_api_version}/{config.phone_number_id}/messages"

    async def send_text(self, to_number: str, body: str):
        """Sends a plain-text WhatsApp message to `to_number` (E.164 format, no '+')."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": body[:4096]},  # WhatsApp text messages cap at 4096 chars
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.base_url, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.error("WhatsApp send failed (%s): %s", response.status_code, response.text)
            return response

    @staticmethod
    def parse_incoming(payload: dict) -> dict | None:
        """
        Extracts {from, text, message_id} from a WhatsApp webhook payload,
        or None if the payload isn't a user text message (e.g. a delivery
        status callback, which WhatsApp also sends to the same webhook).
        """
        try:
            entry = payload["entry"][0]["changes"][0]["value"]
            messages = entry.get("messages")
            if not messages:
                return None  # status update, not a new message
            message = messages[0]
            if message.get("type") != "text":
                return None  # ignore images/audio/etc. for this bot
            return {
                "from": message["from"],
                "text": message["text"]["body"],
                "message_id": message["id"],
            }
        except (KeyError, IndexError, TypeError):
            return None
