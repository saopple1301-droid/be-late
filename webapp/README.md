# Be Late - webapp

「Be Late」LINE Bot の companion アプリ（React + Vite の PWA）。LINE Login (LIFF) でログインし、バックエンド（`../app`）の REST API (`/api/*`) を叩きます。

セットアップ・環境変数・使い方はリポジトリルートの [README.md](../README.md#スマホアプリwebapp-のセットアップ) を参照してください。

```bash
npm install
npm run dev     # http://localhost:5173
npm run build   # dist/ に静的ビルドを出力
npm run lint
```
