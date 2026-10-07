"""Notification adapters. Only an explicit caller sends a notification."""

from typing import Any

import httpx


async def notify_slack(token: str, channel: str, text: str, client: httpx.AsyncClient) -> None:
    response = await client.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": text},
        timeout=15,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise ValueError("Slack rejected the notification.")


async def notify_teams(webhook_url: str, text: str, client: httpx.AsyncClient) -> None:
    if not webhook_url.startswith("https://"):
        raise ValueError("Teams workflow URL must use HTTPS.")
    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [{"type": "TextBlock", "text": text, "wrap": True}],
    }
    response = await client.post(
        webhook_url,
        json={
            "type": "message",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
            ],
        },
        timeout=15,
    )
    response.raise_for_status()


async def notify_email(
    token: str, sender: str, recipient: str, text: str, client: httpx.AsyncClient
) -> None:
    from urllib.parse import quote

    response = await client.post(
        f"https://graph.microsoft.com/v1.0/users/{quote(sender, safe='')}/sendMail",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": {
                "subject": "Agent action needs approval",
                "body": {"contentType": "Text", "content": text},
                "toRecipients": [{"emailAddress": {"address": recipient}}],
            }
        },
        timeout=15,
    )
    response.raise_for_status()
