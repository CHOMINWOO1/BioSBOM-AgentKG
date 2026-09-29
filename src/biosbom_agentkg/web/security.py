"""Local-origin browser boundary; not a multi-user authentication system."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie

from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class BrowserBoundary:
    def __init__(self, app, *, port, secret):
        self.app = app
        self.hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
        self.secret = secret

    def csrf(self, session):
        return hmac.new(self.secret, session.encode(), hashlib.sha256).hexdigest()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        origin = headers.get("origin")

        async def reject(status, code):
            await JSONResponse({"error": code}, status_code=status)(scope, receive, send)

        if host not in self.hosts:
            return await reject(403, "host_refused")
        if headers.get("sec-fetch-site") == "cross-site" or (
            origin is not None and origin != "http://" + host
        ):
            return await reject(403, "origin_refused")
        cookies = SimpleCookie()
        try:
            cookies.load(headers.get("cookie", ""))
        except Exception:
            return await reject(403, "session_required")
        token = cookies.get("biosbom_session")
        session = token.value if token else ""
        # Signed stateless random sessions survive across tabs but not server restarts.
        parts = session.split(".")
        valid = len(parts) == 2 and hmac.compare_digest(parts[1], self.csrf(parts[0]))
        if scope["path"].startswith("/api/") and not valid:
            return await reject(403, "session_required")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            if not valid or not hmac.compare_digest(
                headers.get("x-biosbom-csrf", ""), self.csrf(session)
            ):
                return await reject(403, "csrf_refused")
            if headers.get("content-type", "").split(";")[0] != "application/json":
                return await reject(415, "json_required")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 2_000_000:
                    return await reject(413, "request_too_large")
                if not message.get("more_body", False):
                    break

            async def replay():
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            downstream_receive = replay
        else:
            downstream_receive = receive
        if scope["path"] == "/" and not valid:
            nonce = secrets.token_hex(32)
            session = nonce + "." + self.csrf(nonce)
        scope["biosbom_csrf"] = self.csrf(session)

        async def secure_send(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self'; img-src 'self' data:; connect-src 'self'; "
                        b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
                    ),
                ]
                if scope["path"] == "/" and not valid:
                    extra.append(
                        (
                            b"set-cookie",
                            (
                                f"biosbom_session={session}; HttpOnly; SameSite=Strict; Path=/"
                            ).encode(),
                        )
                    )
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, downstream_receive, secure_send)
