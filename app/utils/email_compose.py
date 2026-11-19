"""
app/utils/email_compose.py
Utilities to generate safe, URL-encoded email compose URLs for Gmail web and mailto links.

Does not call external APIs, OAuth, or auto-send emails.
Generates links that open compose views for manual human review and sending.
"""

from typing import Optional
from urllib.parse import quote


def generate_gmail_compose_url(
    recipient: Optional[str],
    subject: str,
    body: str,
) -> str:
    """
    Constructs a URL that opens the Gmail web compose interface with pre-filled fields.

    Format:
    https://mail.google.com/mail/?view=cm&fs=1&to=...&su=...&body=...
    """
    base_url = "https://mail.google.com/mail/?view=cm&fs=1"
    
    params = []
    if recipient and recipient.strip():
        params.append(f"to={quote(recipient.strip())}")
    
    if subject:
        params.append(f"su={quote(subject)}")
        
    if body:
        params.append(f"body={quote(body)}")
        
    query_string = "&".join(params)
    return f"{base_url}&{query_string}" if query_string else base_url


def generate_mailto_url(
    recipient: Optional[str],
    subject: str,
    body: str,
) -> str:
    """
    Constructs a standard mailto: URI for system default email clients.

    Format:
    mailto:recipient?subject=...&body=...
    """
    to_part = quote(recipient.strip()) if recipient and recipient.strip() else ""
    params = []
    
    if subject:
        params.append(f"subject={quote(subject)}")
    if body:
        params.append(f"body={quote(body)}")
        
    query = f"?{'&'.join(params)}" if params else ""
    return f"mailto:{to_part}{query}"
