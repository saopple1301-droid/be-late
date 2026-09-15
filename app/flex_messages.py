"""Builders for every bot -> user message. Postback `data` is always a
`urlencode`d query string like `action=arrive&meetup_id=3` so handlers can
parse it with `urllib.parse.parse_qs`.
"""
from __future__ import annotations

from urllib.parse import urlencode

from linebot.v3.messaging.models import (
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexMessage,
    FlexText,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    TextMessage,
)


def _pb(**kwargs) -> str:
    return urlencode(kwargs)


def text(msg: str, quick_reply: QuickReply | None = None) -> TextMessage:
    return TextMessage(text=msg, quickReply=quick_reply)


# ---------------------------------------------------------------- wizard --

def member_select_flex(members: list[tuple[int, str]], selected_ids: set[int]) -> FlexMessage:
    """members: [(user_id, display_name), ...]"""
    rows = []
    for uid, name in members:
        mark = "✅ " if uid in selected_ids else "⬜ "
        rows.append(
            FlexButton(
                style="secondary" if uid in selected_ids else "link",
                action=PostbackAction(label=f"{mark}{name}"[:20], data=_pb(action="toggle_member", user_id=uid)),
            )
        )
    rows.append(
        FlexButton(style="primary", color="#00b900",
                    action=PostbackAction(label="次へ（デポジット選択）", data=_pb(action="members_next")))
    )
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text="一緒に待ち合わせる友達を選んでください", weight="bold", wrap=True),
                FlexBox(layout="vertical", margin="md", spacing="sm", contents=rows),
            ],
        )
    )
    return FlexMessage(altText="メンバーを選択してください", contents=bubble)


def deposit_select_quick_reply() -> QuickReply:
    amounts = [100, 300, 500, 1000, 2000]
    items = [
        QuickReplyItem(action=PostbackAction(label=f"¥{a}", data=_pb(action="set_deposit", amount=a)))
        for a in amounts
    ]
    return QuickReply(items=items)


def confirm_flex(place: str, scheduled_at_str: str, deposit: int, member_names: list[str]) -> FlexMessage:
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text="この内容で待ち合わせを作成します", weight="bold", wrap=True),
                FlexText(text=f"場所: {place}", wrap=True, margin="md"),
                FlexText(text=f"集合時刻: {scheduled_at_str}", wrap=True),
                FlexText(text=f"デポジット: ¥{deposit}", wrap=True),
                FlexText(text="メンバー: " + "、".join(member_names), wrap=True, size="sm", color="#888888"),
                FlexBox(
                    layout="horizontal", margin="lg", spacing="md",
                    contents=[
                        FlexButton(style="primary", color="#00b900",
                                    action=PostbackAction(label="確定してデポジット請求", data=_pb(action="confirm_meetup"))),
                        FlexButton(style="secondary",
                                    action=PostbackAction(label="キャンセル", data=_pb(action="cancel_draft"))),
                    ],
                ),
            ],
        )
    )
    return FlexMessage(altText="待ち合わせの確認", contents=bubble)


# ---------------------------------------------------------------- arrive --

def arrival_button_flex(meetup_id: int, place: str) -> FlexMessage:
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text=f"「{place}」に到着したらボタンを押してください", wrap=True, weight="bold"),
                FlexButton(
                    style="primary", color="#00b900", margin="lg",
                    action=PostbackAction(label="到着しました", data=_pb(action="arrive", meetup_id=meetup_id)),
                ),
            ],
        )
    )
    return FlexMessage(altText="到着ボタン", contents=bubble)


def location_share_prompt() -> TextMessage:
    return text("下の「+」から位置情報を送ると、他のメンバーと現在地を共有できます。")


def location_summary_text(entries: list[str]) -> TextMessage:
    body = "\n\n".join(entries) if entries else "まだ誰も位置情報を共有していません。"
    return text("現在のメンバーの位置:\n\n" + body)


# ----------------------------------------------------------------- late --

def late_minutes_quick_reply(meetup_id: int) -> QuickReply:
    options = [5, 10, 15, 20, 30, 60]
    items = [
        QuickReplyItem(action=PostbackAction(
            label=f"{m}分以内", data=_pb(action="declare_late", meetup_id=meetup_id, minutes=m)))
        for m in options
    ]
    return QuickReply(items=items)


def late_notice_message(meetup_id: int, place: str) -> TextMessage:
    return text(
        f"集合時刻になりましたが「{place}」にまだ到着していません。\n"
        "何分以内に到着できますか？",
        quick_reply=late_minutes_quick_reply(meetup_id),
    )


def late_declared_ack(minutes: int) -> TextMessage:
    return text(f"{minutes}分以内の到着で登録しました。この時間を過ぎるとペナルティが発生します。")


def group_late_announcement(name: str, minutes: int) -> TextMessage:
    return text(f"{name} さんが遅刻中です。{minutes}分以内に到着すると申告しました。")


def penalty_charged_announcement(name: str, amount: int) -> TextMessage:
    return text(f"{name} さんは申告した時間内に到着できなかったため、追加ペナルティ ¥{amount} が発生しました。")


def deposit_forfeited_announcement(name: str, amount: int) -> TextMessage:
    return text(f"{name} さんは遅刻したため、デポジット ¥{amount} は他のメンバーで分配されます。")


def settlement_summary(entries: list[str]) -> TextMessage:
    return text("待ち合わせが終了しました。精算結果:\n\n" + "\n".join(entries))


# ---------------------------------------------------------------- doubt --

def doubt_prediction_flex(meetup_id: int, target_id: int, target_name: str) -> FlexMessage:
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(text="ダウト予想タイム！", weight="bold", color="#ff334b"),
                FlexText(text=f"{target_name} さんは今日、遅刻すると思いますか？", wrap=True, margin="md"),
                FlexText(text="予想は他のメンバーには一切わかりません。", size="xs", color="#888888", wrap=True, margin="sm"),
                FlexBox(
                    layout="horizontal", margin="lg", spacing="md",
                    contents=[
                        FlexButton(style="primary", color="#ff334b",
                                    action=PostbackAction(label="遅刻すると思う", data=_pb(
                                        action="doubt", meetup_id=meetup_id, target_id=target_id, predicted="1"))),
                        FlexButton(style="secondary",
                                    action=PostbackAction(label="時間通りだと思う", data=_pb(
                                        action="doubt", meetup_id=meetup_id, target_id=target_id, predicted="0"))),
                    ],
                ),
            ],
        )
    )
    return FlexMessage(altText=f"{target_name} さんについてのダウト予想", contents=bubble)


def doubt_ack_message() -> TextMessage:
    return text("予想を受け付けました（誰にもわかりません）。")


def doubt_reward_announcement(reward: int) -> TextMessage:
    return text(f"ダウト予想が的中しました！報酬 ¥{reward} を獲得しました。")
