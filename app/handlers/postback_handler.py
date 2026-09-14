from urllib.parse import parse_qs

from linebot.v3.webhooks import PostbackEvent

from app import flex_messages as fx
from app import line_client
from app.database import get_session
from app.models import User
from app.services import (
    deposit_service,
    doubt_service,
    identity_service,
    meetup_service,
    penalty_service,
)


def _parse(data: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(data).items()}


def handle_postback(event: PostbackEvent) -> None:
    params = _parse(event.postback.data)
    action = params.get("action")
    source = event.source

    with get_session() as session:
        user = identity_service.get_or_create_user(session, source.user_id)

        if action == "toggle_member":
            _toggle_member(session, event, source, user, params)
        elif action == "members_next":
            _members_next(session, event, source, user)
        elif action == "set_deposit":
            _set_deposit(session, event, source, user, params)
        elif action == "confirm_meetup":
            _confirm_meetup(session, event, source, user)
        elif action == "cancel_draft":
            _cancel_draft(session, event, source, user)
        elif action == "arrive":
            _arrive(session, event, params, user)
        elif action == "declare_late":
            _declare_late(session, event, params, user)
        elif action == "doubt":
            _doubt(session, event, params, user)


def _toggle_member(session, event, source, user, params) -> None:
    if source.type != "group":
        return
    group = identity_service.get_or_create_group(session, source.group_id)
    draft = meetup_service.get_draft(session, group, user)
    if not draft:
        line_client.reply(event.reply_token, [fx.text("先に「集合」と送って開始してください。")])
        return
    draft = meetup_service.toggle_member(session, draft, int(params["user_id"]))
    members = [m for m in identity_service.group_members(session, group) if m.id != user.id]
    member_pairs = [(m.id, m.display_name or "(名前未設定)") for m in members]
    selected = meetup_service.selected_member_ids(draft)
    line_client.reply(event.reply_token, [fx.member_select_flex(member_pairs, selected)])


def _members_next(session, event, source, user) -> None:
    if source.type != "group":
        return
    group = identity_service.get_or_create_group(session, source.group_id)
    draft = meetup_service.get_draft(session, group, user)
    if not draft:
        line_client.reply(event.reply_token, [fx.text("先に「集合」と送って開始してください。")])
        return
    if not meetup_service.selected_member_ids(draft):
        line_client.reply(event.reply_token, [fx.text("少なくとも1人選んでください。")])
        return
    meetup_service.advance_to_deposit(session, draft)
    line_client.reply(event.reply_token, [fx.text(
        "1人あたりのデポジット金額を選んでください。", quick_reply=fx.deposit_select_quick_reply()
    )])


def _set_deposit(session, event, source, user, params) -> None:
    if source.type != "group":
        return
    group = identity_service.get_or_create_group(session, source.group_id)
    draft = meetup_service.get_draft(session, group, user)
    if not draft:
        line_client.reply(event.reply_token, [fx.text("先に「集合」と送って開始してください。")])
        return
    meetup_service.set_deposit(session, draft, int(params["amount"]))
    line_client.reply(event.reply_token, [fx.text("集合場所を入力してください（例: 渋谷駅ハチ公口）")])


def _confirm_meetup(session, event, source, user) -> None:
    if source.type != "group":
        return
    group = identity_service.get_or_create_group(session, source.group_id)
    draft = meetup_service.get_draft(session, group, user)
    if not draft or not draft.scheduled_at:
        line_client.reply(event.reply_token, [fx.text("待ち合わせの情報が不足しています。最初からやり直してください。")])
        return

    meetup = meetup_service.confirm_draft(session, draft)
    participants = meetup_service.get_participants(session, meetup.id)

    from app.scheduler import schedule_meetup_jobs
    schedule_meetup_jobs(meetup.id, meetup.scheduled_at)

    line_client.reply(event.reply_token, [fx.text(
        f"待ち合わせ「{meetup.place_name}」を作成しました。各メンバーにデポジットを請求します。"
    )])

    deposit_service.request_all_deposits(session, meetup, participants)
    if deposit_service.activate_if_ready(session, meetup, participants):
        pass  # doubt phase job already scheduled; nothing else to do here

    for p in participants:
        member = session.get(User, p.user_id)
        line_client.push(member.line_user_id, [fx.arrival_button_flex(meetup.id, meetup.place_name)])
        line_client.push(member.line_user_id, [fx.location_share_prompt()])


def _cancel_draft(session, event, source, user) -> None:
    if source.type != "group":
        return
    group = identity_service.get_or_create_group(session, source.group_id)
    draft = meetup_service.get_draft(session, group, user)
    if draft:
        meetup_service.cancel_draft(session, draft)
    line_client.reply(event.reply_token, [fx.text("キャンセルしました。")])


def _arrive(session, event, params, user) -> None:
    meetup_id = int(params["meetup_id"])
    meetup = meetup_service.get_meetup(session, meetup_id)
    participant = meetup_service.get_participant(session, meetup_id, user.id)
    if not meetup or not participant:
        line_client.reply(event.reply_token, [fx.text("待ち合わせが見つかりませんでした。")])
        return
    if participant.arrived_at:
        line_client.reply(event.reply_token, [fx.text("すでに到着済みとして記録されています。")])
        return
    penalty_service.mark_arrived(session, meetup, participant)
    line_client.reply(event.reply_token, [fx.text("到着を記録しました！お疲れさまでした。")])


def _declare_late(session, event, params, user) -> None:
    meetup_id = int(params["meetup_id"])
    minutes = int(params["minutes"])
    meetup = meetup_service.get_meetup(session, meetup_id)
    participant = meetup_service.get_participant(session, meetup_id, user.id)
    if not meetup or not participant:
        line_client.reply(event.reply_token, [fx.text("待ち合わせが見つかりませんでした。")])
        return
    penalty_service.declare_late(session, meetup, participant, minutes)


def _doubt(session, event, params, user) -> None:
    meetup_id = int(params["meetup_id"])
    target_id = int(params["target_id"])
    predicted_late = params.get("predicted") == "1"
    doubt_service.record_prediction(session, meetup_id, user.id, target_id, predicted_late)
    line_client.reply(event.reply_token, [fx.doubt_ack_message()])
