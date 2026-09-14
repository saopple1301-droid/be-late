from linebot.v3.webhooks import LocationMessageContent, MessageEvent, TextMessageContent

from app import flex_messages as fx
from app import line_client, payments
from app.database import get_session
from app.services import identity_service, location_service, meetup_service

HELP_TEXT = (
    "Be Late の使い方:\n"
    "「集合」と送るとメンバー・デポジット・場所・時刻を選んで待ち合わせを作成します。\n"
    "「位置」でメンバーの現在地を確認できます。\n"
    "位置情報メッセージを送ると、あなたの現在地が共有されます。\n"
    "集合時刻になっても到着していない場合、遅刻を申告するボタンが届きます。\n"
    "「カード登録」で、デポジット・ペナルティ決済用のカードを事前登録できます。"
)


def handle_message(event: MessageEvent) -> None:
    if isinstance(event.message, LocationMessageContent):
        _handle_location(event)
        return
    if isinstance(event.message, TextMessageContent):
        _handle_text(event)


def _handle_text(event: MessageEvent) -> None:
    text_in = event.message.text.strip()
    source = event.source

    with get_session() as session:
        user = identity_service.get_or_create_user(session, source.user_id)

        group = None
        if source.type == "group":
            group = identity_service.get_or_create_group(session, source.group_id)
            identity_service.ensure_membership(session, group, user)

        if text_in in ("集合", "/meetup", "待ち合わせ"):
            if not group:
                line_client.reply(event.reply_token, [fx.text("この機能はグループ内で使ってください。")])
                return
            members = [u for u in identity_service.group_members(session, group) if u.id != user.id]
            if not members:
                line_client.reply(event.reply_token, [fx.text(
                    "まだ他のメンバーがこのグループでボットと話していません。"
                    "全員が一度グループでメッセージを送ってからもう一度お試しください。"
                )])
                return
            draft = meetup_service.start_draft(session, group, user)
            member_pairs = [(m.id, m.display_name or "(名前未設定)") for m in members]
            line_client.reply(event.reply_token, [fx.member_select_flex(member_pairs, set())])
            return

        if text_in in ("位置", "位置情報"):
            meetup = None
            if group:
                meetup = meetup_service.find_active_meetup_for_group(session, group.id)
            if not meetup:
                meetup = meetup_service.find_active_meetup_for_user(session, user.id)
            if not meetup:
                line_client.reply(event.reply_token, [fx.text("進行中の待ち合わせがありません。")])
                return
            lines = location_service.build_summary_lines(session, meetup.id)
            line_client.reply(event.reply_token, [fx.location_summary_text(lines)])
            return

        if text_in in ("カード登録", "カード", "card"):
            url = payments.create_card_setup_checkout_url(user, "/stripe/setup-return")
            session.add(user)
            session.commit()
            line_client.reply(event.reply_token, [fx.card_setup_message(url)])
            return

        if group:
            draft = meetup_service.get_draft(session, group, user)
            if draft and draft.step == "select_place":
                meetup_service.set_place(session, draft, text_in)
                line_client.reply(event.reply_token, [fx.text("集合時刻を入力してください（例: 19:30）")])
                return
            if draft and draft.step == "select_time":
                parsed = meetup_service.parse_time_text(text_in)
                if not parsed:
                    line_client.reply(event.reply_token, [fx.text("時刻の形式が正しくありません。例: 19:30")])
                    return
                draft = meetup_service.set_time(session, draft, parsed)
                from app.models import User as UserModel
                member_names = [
                    session.get(UserModel, uid).display_name or "(名前未設定)"
                    for uid in meetup_service.selected_member_ids(draft)
                ]
                member_names.append(user.display_name or "(あなた)")
                line_client.reply(event.reply_token, [fx.confirm_flex(
                    draft.place_name, parsed.strftime("%Y-%m-%d %H:%M"), draft.deposit_amount or 0, member_names
                )])
                return

        if text_in in ("ヘルプ", "help", "使い方"):
            line_client.reply(event.reply_token, [fx.text(HELP_TEXT)])
            return

        line_client.reply(event.reply_token, [fx.text(HELP_TEXT)])


def _handle_location(event: MessageEvent) -> None:
    source = event.source
    with get_session() as session:
        user = identity_service.get_or_create_user(session, source.user_id)
        meetup = meetup_service.find_active_meetup_for_user(session, user.id)
        if not meetup:
            line_client.reply(event.reply_token, [fx.text(
                "進行中の待ち合わせが見つかりませんでした。「集合」で作成してから送ってください。"
            )])
            return
        location_service.record_location(session, meetup.id, user.id, event.message.latitude, event.message.longitude)
        line_client.reply(event.reply_token, [fx.text("現在地を共有しました。「位置」でメンバーの現在地を確認できます。")])
