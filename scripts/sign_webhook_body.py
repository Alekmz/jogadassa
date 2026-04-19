#!/usr/bin/env python3
"""Calcula X-Signature (hex HMAC-SHA256) para POST /payments/webhook — PAYMENT_PROVIDER=webhook_stub."""
import hashlib
import hmac
import json
import os
import sys

secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "webhook-secret-change").encode()
body = json.dumps(
    {"order_id": int(sys.argv[1]), "event": "paid", "extra": {}}
).encode()
sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
print(body.decode())
print("X-Signature:", sig)
