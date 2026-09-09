"""API Gateway HTTP API v2 to ASGI; no persistent process or local state assumed."""

from __future__ import annotations

import asyncio
import base64

from archon.web.api import app


async def invoke(event):
    http = event["requestContext"]["http"]
    payload = event.get("body") or ""
    body = base64.b64decode(payload) if event.get("isBase64Encoded") else payload.encode()
    headers = [(k.lower().encode(), v.encode()) for k, v in event.get("headers", {}).items()]
    if event.get("cookies"):
        headers.append((b"cookie", "; ".join(event["cookies"]).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "method": http["method"], "scheme": "https",
        "path": http["path"], "raw_path": http["path"].encode(), "root_path": "",
        "query_string": event.get("rawQueryString", "").encode(), "headers": headers,
        "server": ("lambda", 443), "client": (http.get("sourceIp", "127.0.0.1"), 0)}
    sent = False
    response = {"statusCode": 500, "headers": {}}
    output = bytearray()
    complete = asyncio.Event()

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await complete.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            response["statusCode"] = message["status"]
            response["headers"] = {k.decode(): v.decode() for k, v in message["headers"]}
        elif message["type"] == "http.response.body":
            output.extend(message.get("body", b""))
            if not message.get("more_body", False):
                complete.set()

    await app(scope, receive, send)
    response.update(body=output.decode(), isBase64Encoded=False)
    return response


def handler(event, context):
    return asyncio.run(invoke(event))
