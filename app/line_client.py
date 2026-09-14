from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
)
from linebot.v3.messaging.models import Message
from linebot.v3.webhook import WebhookParser

from app.config import settings

_configuration = Configuration(access_token=settings.line_channel_access_token)
parser = WebhookParser(settings.line_channel_secret)


def _client() -> MessagingApi:
    return MessagingApi(ApiClient(_configuration))


def reply(reply_token: str, messages: list[Message]) -> None:
    with ApiClient(_configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


def push(to: str, messages: list[Message]) -> None:
    with ApiClient(_configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=to, messages=messages)
        )
