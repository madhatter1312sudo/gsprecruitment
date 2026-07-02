"""
Talent OS — Email Service
Uses Google Gmail API (OAuth2) to send transactional emails.
Uses the existing Google OAuth credentials already configured in .env.
"""

import logging
import base64
from email.mime.text import MIMEText
from typing import Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
import httpx
from core.config import settings

logger = logging.getLogger("talent_os.email")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class EmailService:
    """Handles sending emails via Gmail API using existing OAuth credentials."""

    def __init__(self):
        self._credentials = None

    def _get_credentials(self) -> Optional[Credentials]:
        """Build credentials from the stored OAuth tokens in .env."""
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_refresh_token:
            logger.warning("Google OAuth credentials not fully configured")
            return None

        try:
            creds = Credentials(
                token=None,
                refresh_token=settings.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=SCOPES,
            )
            # Force refresh to get a valid access token
            creds.refresh(GoogleRequest())
            return creds
        except Exception as e:
            logger.error(f"Failed to refresh Google OAuth token: {e}")
            return None

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        to_name: Optional[str] = None,
    ) -> bool:
        """Send an email via Gmail API."""
        creds = self._get_credentials()
        if not creds:
            logger.error("Cannot send email: no valid Google credentials")
            return False

        msg = MIMEText(body_text, "plain", "utf-8")
        msg["To"] = to_email
        msg["From"] = "GSP Recruitment <info@gsprecruitment.nl>"
        msg["Subject"] = subject

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json={"raw": raw},
                )
                if response.status_code == 200:
                    logger.info(f"Email sent to {to_email}: {subject}")
                    return True
                else:
                    logger.error(f"Gmail API error: {response.status_code} {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send email via Gmail API: {e}")
            return False


email_service = EmailService()
