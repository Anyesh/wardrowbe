"""Title, picture and price of a shop page, read from its Open Graph / product meta tags.

The server fetches a URL the user typed, so every hop is checked against the network the
server sits in: only http(s) to public addresses, no redirect into the LAN, a small body and a
short timeout."""

import asyncio
import json
import re
import socket
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from ipaddress import IPv6Address, ip_address
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 1_500_000
TIMEOUT_SECONDS = 8
MAX_REDIRECTS = 4
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36 Wardrowbe-link-preview"
)


class PreviewError(Exception):
    """The page cannot be previewed; the message is safe to show."""


@dataclass
class LinkPreview:
    url: str
    title: str | None = None
    image_url: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    site: str | None = None


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self.json_ld: list[str] = []
        self._in_title = False
        self._in_json_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop") or ""
            key = key.strip().lower()
            if key and "content" in values and key not in self.meta:
                self.meta[key] = values["content"].strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self.json_ld.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_json_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif self._in_json_ld:
            self.json_ld[-1] += data


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    # "1.299,00" and "1,299.00" both mean 1299; a lone comma is a decimal comma.
    if "," in text and "." in text:
        text = (
            text.replace(".", "").replace(",", ".")
            if text.rfind(",") > text.rfind(".")
            else text.replace(",", "")
        )
    elif "," in text:
        text = text.replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        amount = Decimal(match.group(0))
    except InvalidOperation:
        return None
    return amount if 0 < amount < Decimal("1000000") else None


def _offer_from_json_ld(blocks: list[str]) -> tuple[Decimal | None, str | None, str | None]:
    for block in blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
                continue
            if not isinstance(node, dict):
                continue
            if "@graph" in node:
                stack.append(node["@graph"])
            offers = node.get("offers")
            if offers:
                for offer in offers if isinstance(offers, list) else [offers]:
                    if isinstance(offer, dict):
                        price = _decimal(offer.get("price") or offer.get("lowPrice"))
                        if price is not None:
                            image = node.get("image")
                            if isinstance(image, list):
                                image = image[0] if image else None
                            if isinstance(image, dict):
                                image = image.get("url")
                            return price, offer.get("priceCurrency"), image
    return None, None, None


def parse_preview(url: str, html: str) -> LinkPreview:
    parser = _MetaParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - a broken page still yields whatever was read before
        pass
    meta = parser.meta
    title = meta.get("og:title") or meta.get("twitter:title") or parser.title.strip() or None
    image = meta.get("og:image") or meta.get("og:image:url") or meta.get("twitter:image")
    price = _decimal(
        meta.get("product:price:amount") or meta.get("og:price:amount") or meta.get("price")
    )
    currency = meta.get("product:price:currency") or meta.get("og:price:currency")
    ld_price, ld_currency, ld_image = _offer_from_json_ld(parser.json_ld)
    if price is None:
        price, currency = ld_price, currency or ld_currency
    image = image or ld_image
    if image:
        image = urljoin(url, image)
        if urlsplit(image).scheme not in ("http", "https"):
            image = None
    return LinkPreview(
        url=url,
        title=(title or "")[:200] or None,
        image_url=image[:1000] if image else None,
        price=price,
        currency=(currency or "")[:3].upper() or None,
        site=meta.get("og:site_name") or urlsplit(url).hostname,
    )


async def ensure_public_host(host: str) -> None:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        raise PreviewError("This address cannot be found.") from None
    for info in infos:
        address = ip_address(info[4][0].split("%")[0])
        if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast:
            raise PreviewError("Only public web pages can be read.")


def validate_url(url: str) -> str:
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PreviewError("Enter a web address that starts with http:// or https://.")
    if parts.username or parts.password:
        raise PreviewError("Addresses with a user name or password are not supported.")
    return url


async def fetch_preview(url: str) -> LinkPreview:
    current = validate_url(url)
    async with httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await ensure_public_host(urlsplit(current).hostname or "")
            try:
                async with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise PreviewError("The page could not be read.")
                        current = validate_url(urljoin(current, location))
                        continue
                    if response.status_code >= 400:
                        raise PreviewError(f"The shop answered with error {response.status_code}.")
                    if "html" not in response.headers.get("content-type", "html"):
                        raise PreviewError("This link is not a web page.")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) >= MAX_BYTES:
                            break
                    encoding = response.encoding or "utf-8"
                    return parse_preview(current, bytes(body).decode(encoding, errors="replace"))
            except httpx.HTTPError:
                raise PreviewError("The page could not be reached.") from None
    raise PreviewError("Too many redirects.")
