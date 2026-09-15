import logging

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import LocationMessageContent, MessageEvent, PostbackEvent, TextMessageContent

from app import line_client, scheduler
from app.api import router as api_router
from app.config import settings
from app.database import init_db
from app.handlers.message_handler import handle_message
from app.handlers.postback_handler import handle_postback

logger = logging.getLogger("be_late")

app = FastAPI(title="Be Late")

_origins = ["*"] if settings.cors_allow_origins == "*" else [
    o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    scheduler.start()


@app.post("/callback")
async def line_callback(request: Request, x_line_signature: str = Header(default="")):
    body = await request.body()
    try:
        events = line_client.parser.parse(body.decode("utf-8"), x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="invalid signature")

    for event in events:
        try:
            if isinstance(event, MessageEvent) and isinstance(
                event.message, (TextMessageContent, LocationMessageContent)
            ):
                handle_message(event)
            elif isinstance(event, PostbackEvent):
                handle_postback(event)
        except Exception:
            logger.exception("failed to handle LINE event")

    return "OK"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
