"""TLS transport with pinning against the Enexoma root certificate."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import ssl
from contextlib import suppress
from typing import Final

from .exceptions import SmartFriendsCertificateError, SmartFriendsConnectionError

_LOGGER = logging.getLogger(__name__)

ROOT_CERT_PEM: Final = """-----BEGIN CERTIFICATE-----
MIIDpTCCAo2gAwIBAgIICt0RIQj4rs4wDQYJKoZIhvcNAQENBQAwYDEWMBQGA1UE
AwwNZW5leG9tYS1yb290MjETMBEGA1UECgwKZW5leG9tYSBBRzEWMBQGA1UEBwwN
T2VybGluZ2hhdXNlbjEMMAoGA1UECAwDTlJXMQswCQYDVQQGEwJERTAeFw0xNjEw
MjcwNzU4MjZaFw0zNjEwMjcwNzU4MjZaMGAxFjAUBgNVBAMMDWVuZXhvbWEtcm9v
dDIxEzARBgNVBAoMCmVuZXhvbWEgQUcxFjAUBgNVBAcMDU9lcmxpbmdoYXVzZW4x
DDAKBgNVBAgMA05SVzELMAkGA1UEBhMCREUwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQC2vOt1yNINfhjmbNvRgi3jqTOYvlpyN0Av1GTKpSPNOOPgAGk+
eHSmp0hYTv3nBlRVii9Nk01JGPqJ9lwChzqWiTsd4P16RIzd+zD844ali36ErgJF
cexPWsQr0S3pCj9f42DGXaKj6oyh5E4DRkCBQVSpMq1N6+PvaE3OFQ22feFdogoK
Q5UAyTFUbiUSegkYYA0BmFT/s8EuCR/brkzsnuGZayEuOzsr43mnM4K+vhoYcfQJ
ure+bxmX6IdCk9hmPWuTWiia0FU9D8ji76FYHvqcCbcmuF5OMPKZMfvI/ZUUpAdk
daE0EF/c98cmlUH7ENSgrCTm87r4OqfAc3nHAgMBAAGjYzBhMA8GA1UdEwEB/wQF
MAMBAf8wHwYDVR0jBBgwFoAUtfMSXYZtNoCKmyteKTbltqhiYn8wHQYDVR0OBBYE
FLXzEl2GbTaAipsrXik25baoYmJ/MA4GA1UdDwEB/wQEAwIBhjANBgkqhkiG9w0B
AQ0FAAOCAQEAWulfbz+++2h5UenfIkEvY8p5Ye1Nsk7rkNUAROCrsleeoJgGDF/i
mJSZ2yIhIpZISesW0T96pqzHJYzKucO4lct+K2nPrxXdF7vK9U61fp5tdCQqRwop
evPKYAfdhyLERPV01xaFwPzO2xnXBcZHk25L7Yrhuwd2rjRPJ9ObVlfgBqQGvJie
IyZ6XzsoAOHbEXdeodRg8LJSU5cWKgSqJ2PjVc+sVsixao0keNcKX0nwKRSRUvCd
aEnBwKdjQdoUYqfnfCKrMwZRHn/ILuZ1qMWrsVPUlfwDGJf7GybvqVxIJjrDjF7+
SwrYYoRq7ApJQPkqU0Gt8UIGW7Hluh8QzQ==
-----END CERTIFICATE-----"""
ROOT_CERT_SHA256: Final = "E1:15:BE:FD:D2:F0:9A:BA:64:A6:09:E9:6A:4C:8A:63:7D:7C:3B:4B:11:3E:EF:C0:35:49:EF:60:8F:76:D5:C1"
MAX_FRAME_SIZE: Final = 16 * 1024 * 1024


def _root_pem_bytes() -> bytes:
    return ROOT_CERT_PEM.encode("ascii")


def _fingerprint(der: bytes) -> str:
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def create_pinned_ssl_context(root_cert: bytes | None = None) -> ssl.SSLContext:
    """Create a TLS client context that trusts exactly the pinned root."""

    pem_bytes = root_cert if root_cert is not None else _root_pem_bytes()
    try:
        pem_text = pem_bytes.decode("ascii")
        der = ssl.PEM_cert_to_DER_cert(pem_text)
    except (UnicodeDecodeError, ValueError) as err:
        raise SmartFriendsCertificateError("The pinned root certificate is invalid") from err

    actual = _fingerprint(der)
    if actual != ROOT_CERT_SHA256:
        raise SmartFriendsCertificateError("The pinned root certificate fingerprint does not match")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # The box certificate uses CN=homeserver and is addressed by IP. Chain,
    # signature and validity are verified against the pinned root, but hostname
    # matching intentionally cannot succeed for an IP literal.
    context.check_hostname = False
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=pem_text)
    return context


def normalize_host(host: str) -> str:
    value = host.strip()
    if value.startswith("[") and value.endswith("]"):
        return value[1:-1]
    return value


class BoxTransport:
    """One TCP/TLS stream to a box."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.host = host
        self.port = port

    @classmethod
    async def open(
        cls,
        host: str,
        port: int,
        *,
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = 12.0,
    ) -> BoxTransport:
        normalized = normalize_host(host)
        context = ssl_context if ssl_context is not None else create_pinned_ssl_context()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    normalized,
                    port,
                    ssl=context,
                    server_hostname=normalized,
                    limit=MAX_FRAME_SIZE + 1,
                ),
                timeout=timeout,
            )
        except TimeoutError as err:
            raise SmartFriendsConnectionError("Timeout while connecting to the box") from err
        except ssl.SSLCertVerificationError as err:
            raise SmartFriendsCertificateError(
                "The box certificate could not be verified against the pinned root"
            ) from err
        except ssl.SSLError as err:
            raise SmartFriendsCertificateError("TLS handshake with the box failed") from err
        except OSError as err:
            raise SmartFriendsConnectionError("Connection to the box failed") from err
        _LOGGER.debug("TLS connection established to %s:%s", normalized, port)
        return cls(reader, writer, normalized, port)

    async def send(self, data: bytes) -> None:
        try:
            self.writer.write(data)
            await self.writer.drain()
        except (ConnectionError, OSError, RuntimeError) as err:
            raise SmartFriendsConnectionError("Sending to the box failed") from err

    async def read(self, size: int = 65536) -> bytes:
        try:
            return await self.reader.read(size)
        except (ConnectionError, OSError, RuntimeError) as err:
            raise SmartFriendsConnectionError("Reading from the box failed") from err

    async def close(self) -> None:
        writer = self.writer
        writer.close()
        with suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)

    @property
    def is_closing(self) -> bool:
        return self.writer.is_closing()
