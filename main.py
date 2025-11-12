import logging
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

# ------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------
# FastAPI App Setup
# ------------------------------------------------------
app = FastAPI(
    title="Webhook Test API",
    version="1.0",
    description="Simple FastAPI app to test incoming webhook POST requests.",
)


# ------------------------------------------------------
# Root Route (Health Check)
# ------------------------------------------------------
@app.get("/")
async def root():
    return {"message": "Webhook Test API is running on port 8004 🚀"}


# ------------------------------------------------------
# Webhook Test Endpoint
# ------------------------------------------------------
@app.post(
    "/api/v1/webhook/test",
    summary="Test webhook receiver",
    description="Receive webhook POSTs for testing — logs headers, URL, and payload and returns a simple acknowledgement.",
)
async def webhook_test(request: Request):
    """
    Simple webhook endpoint for testing incoming payloads.
    Logs URL, headers, and payload (attempts JSON decode, falls back to text/bytes).
    """
    try:
        # Capture request metadata
        url = str(request.url)
        headers = dict(request.headers)
        content_type = headers.get("content-type", "")
        payload = None

        # Parse body safely
        if "application/json" in content_type:
            try:
                payload = await request.json()
            except Exception:
                raw = await request.body()
                payload = raw.decode("utf-8", errors="replace")
        else:
            raw = await request.body()
            payload = raw.decode("utf-8", errors="replace")

        # ✅ Log full details
        logger.info("=== WEBHOOK TEST RECEIVED ===")
        logger.info("URL: %s", url)
        logger.info("Headers: %s", headers)
        logger.info("Payload: %s", payload)
        logger.info("=== END WEBHOOK ===")

        return JSONResponse(
            {
                "success": True,
                "received": True,
                "note": "Logged URL, headers, and payload on server",
                "url": url,
            },
            status_code=200,
        )

    except Exception as exc:
        logger.exception("Error handling webhook test: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook handler error",
        )
