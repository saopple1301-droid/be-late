# Be Late

大学生の「待ち合わせの遅刻」を、デポジット・位置情報共有・ダウト予想ゲームで解決する LINE Bot です。

## 解決したい課題

- 待つ側: 5〜10分でもその場を離れられず、突っ立って待つのがストレス
- 遅刻する側: 遅刻の深刻さに気づいていない

## 機能一覧（要件との対応）

| 要件 | 実装 |
| --- | --- |
| 待ち合わせる友達を選択し、デポジット金額を選択 | 「集合」コマンドのウィザード（メンバー選択→デポジット→場所→時刻） |
| 集合時間を登録 | ウィザードの時刻入力ステップ |
| 全員が時間に間に合った場合、デポジットは没収されない | 全員 `arrived_at` が集合時刻までに記録された場合、保留していたデポジットを解放（Stripe PaymentIntent をキャンセル） |
| 誰かが遅刻したらそのデポジットを他のメンバーがもらう | 遅刻者のデポジットを capture し、他の参加者に均等分配（Stripe Connect Transfer） |
| お互いの現在地共有 | LINE の位置情報メッセージを保存し、「位置」コマンドで最新位置をまとめて表示 |
| 到着ボタン | 集合場所ごとに個別トークへ届く「到着しました」ボタン |
| 遅刻時に「何分以内に到着するか」を入力 | 集合時刻を過ぎても未到着の人にクイックリプライで申告してもらう |
| 申告時間を過ぎたら追加ペナルティ | 申告した締切を過ぎると、デポジットに加えて同額の追加ペナルティを自動課金 |
| 集合2時間前の「ダウト」予想システム | 各メンバーへ 1:1 で「この人は遅刻すると思う？」を個別送信し、正解者に報酬を分配 |
| 誰が誰にダウトしたか分からない | 予想はグループに一切表示されず、DB上も個人ごとに秘匿。結果発表は「合計払戻額」のみ |

## アーキテクチャ

```
LINE グループ/個別チャット
        │  Webhook
        ▼
FastAPI (/callback) ── linebot v3 SDK でイベント解析
        │
        ├─ handlers/message_handler.py   … テキスト・位置情報メッセージ
        ├─ handlers/postback_handler.py  … ボタン操作（メンバー選択・到着・ダウト等）
        │
        ├─ services/*                    … ビジネスロジック（DB更新・通知組み立て）
        │     ├─ meetup_service   待ち合わせ作成ウィザード
        │     ├─ deposit_service  デポジット請求
        │     ├─ penalty_service  到着判定・ペナルティ・精算
        │     ├─ doubt_service    ダウト予想の記録
        │     └─ location_service 位置情報の保存・要約
        │
        ├─ payments.py                   … Stripe 連携（保留→capture/release, ペナルティ課金, Transfer）
        ├─ scheduler.py                  … APScheduler（T-2hダウト開始、集合時刻判定、申告締切判定）
        └─ models.py / database.py       … SQLModel + SQLite
```

詳細な設計判断は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) を参照してください。

## セットアップ

### 1. 依存関係

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # pytest を含む。本番は requirements.txt のみでOK
```

### 2. LINE Developers

1. Messaging API チャネルを作成
2. チャネルシークレット / チャネルアクセストークンを取得
3. Webhook URL に `https://<公開URL>/callback` を設定し、Webhookの利用をON

### 3. Stripe

1. https://dashboard.stripe.com/test/apikeys からテスト用シークレットキーを取得
2. Webhook（`checkout.session.completed`）を `https://<公開URL>/stripe/webhook` に設定し、Signing secret を取得
3. デポジットの払い戻しを受け取るメンバーは、Stripe Connect のアカウントを別途オンボーディングし、`User.stripe_account_id` に設定してください（未設定のメンバーへの分配は `payout_status="manual_required"` として記録され、アプリ外で手動精算する運用になります）

### 4. .env

`.env.example` をコピーして `.env` を作成し、上記の値を埋めてください。

### 5. 起動

```bash
uvicorn app.main:app --reload
# 別ターミナルで公開URLを発行（例: ngrok http 8000）
```

### 6. テスト

```bash
pytest
```

## 使い方（LINEでの操作）

1. ボットを LINE グループに招待し、参加者全員が一度何かメッセージを送る（ボットがメンバーを認識するために必要）
2. 各参加者は 1:1 でもボットを友だち追加しておく（遅刻申告・ダウト予想・到着ボタンなどは個別トークに届くため）
3. グループで「集合」と送信 → メンバー選択 → デポジット金額 → 集合場所 → 集合時刻 → 確認して確定
4. デポジットのカードが未登録の場合は「カード登録」で事前登録、または確定時に届くリンクから決済
5. 集合2時間前に、各メンバーへ個別に「ダウト」予想（他メンバーが遅刻するかどうか）が届く
6. 集合場所に着いたら「到着しました」ボタンを押す
7. 集合時刻を過ぎても未到着の場合、「何分以内に到着するか」を申告
8. 申告時間を過ぎると追加ペナルティが自動課金され、全員が確定した時点で精算結果が届く

## 既知の制約

- 時刻はサーバーのローカルタイムで解釈します（タイムゾーンを扱いたい場合は `TZ` 環境変数をサーバーに設定してください）
- デポジット・ペナルティの決済はカード情報をLINE上で直接扱えないため、初回は Stripe Checkout の決済リンクを送る形になります
- 払い戻し（Stripe Connect Transfer）は受取人が Connect アカウントを設定している場合のみ自動化されます。未設定の場合はアプリ外での手動精算が必要です
- ダウト予想の正解報酬率・分配ルールは要件に明記がなかったため、本実装では独自ルールを採用しています（詳細は ARCHITECTURE.md）
