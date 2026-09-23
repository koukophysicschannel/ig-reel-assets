# ig-reel-assets

物理解説チャンネルの既存ショート動画（YouTube Shorts）を、Instagramリールとして毎日1本自動投稿するための動画アセット＋投稿キュー＋GitHub Actionsワークフロー。

## 構成

- `reels/001.mp4` 〜 `reels/018.mp4` — 投稿対象の動画本体（GitHub Pagesで公開し、`video_url`としてInstagram Graph APIに渡す）
- `reels/queue.json` — 投稿キュー。先頭から`posted: false`の最初の1件を毎日1本消化する
- `scripts/publish_reel.py` — コンテナ作成→ステータス確認→公開の3ステップを実行し、成功したら`queue.json`を更新するスクリプト
- `.github/workflows/post-reel.yml` — 日次実行用のGitHub Actionsワークフロー（毎日 JST 18:00 に自動実行。手動実行も可能）
- `scripts/refresh_token.py` / `.github/workflows/refresh-token.yml` — 週次でアクセストークンをリフレッシュし、GitHub Secretsを自動更新するワークフロー（毎週月曜 JST 12:00）
- `state/token_status.json` — 最終リフレッシュ日時・失効予定日の記録（非シークレット）

## queue.json のcaption確認について（確認済み）

`_needs_review`フィールドが付いている3件（`006`/`017`の対応、`009`の対応、`018`のcaption未設定）は2026-09-23に清水さんが目視確認済みです。006/017・009の対応は正しいことを確認済み。018はYouTube未公開のためcaption未設定のまま投稿対象から除外しています（`_needs_review`フィールド自体は記録として残しています）。

## セットアップ状況

- [x] GitHubリポジトリ作成・動画18本を`reels/`に配置
- [x] `queue.json`の初期データ作成
- [x] 投稿スクリプト・ワークフロー作成
- [x] GitHub Actions Secrets（`IG_ACCESS_TOKEN` / `IG_USER_ID`）設定
- [x] GitHub Pages公開設定
- [x] `queue.json`のcaption内容を目視確認（3件とも確認済み、上記参照）
- [x] `workflow_dispatch`（`dry_run: true`）での動作確認
- [x] `workflow_dispatch`（`dry_run: false`）で001を実際に手動投稿して確認（https://www.instagram.com/reel/DdoDOx2CpaX/）
- [x] `schedule`を有効化（毎日 JST 18:00 / UTC 09:00, cron: `"0 9 * * *"`, 2026-09-23〜）
- [x] トークン自動リフレッシュのワークフロー・スクリプトを実装
- [ ] **`GH_PAT_SECRETS_ADMIN` シークレットの登録（要手動対応。下記参照）**
- [ ] 上記登録後、`refresh-token.yml`を`workflow_dispatch`で一度手動実行して疎通確認

## トークン自動リフレッシュのセットアップ（要手動対応・1回のみ）

`refresh-token.yml`がGitHub Secretsを書き換えるには、既定の`GITHUB_TOKEN`では権限が足りないため、専用のPersonal Access Token (PAT) が必要です。

1. github.com → 右上アイコン → **Settings → Developer settings → Fine-grained tokens** → Generate new token
2. Resource owner: `koukophysicschannel`、Repository access: **Only select repositories → ig-reel-assets**
3. Permissions → Repository permissions → **Secrets: Read and write** のみ付与
4. Expiration: 選べる最大期間（通常1年）を設定
5. 発行されたトークンを`GH_PAT_SECRETS_ADMIN`という名前でこのリポジトリのSecretsに登録

このPATには有効期限があるため、期限が近づいたら再発行・再登録が必要です（自動化不可、要カレンダーリマインダー）。

## トークン失効の監視の仕組み

- 毎週月曜、`IG_ACCESS_TOKEN`をリフレッシュし成功すれば失効予定日が常に約53日先に更新される
- リフレッシュ失敗時はワークフローが失敗し、GitHub標準の失敗通知メールが届く
- `state/token_status.json`の失効予定日までの残り日数が14日を切っている場合、リフレッシュの成否に関わらずワークフローを失敗させて警告する（直近数週間リフレッシュが失敗し続けているサイン）
- `publish_reel.py`側もOAuthException（トークン無効・失効）を検出した場合、ログに`🔑 TOKEN_ERROR:`のラベル付きで明示する

## 動画URLの形式

```
https://koukophysicschannel.github.io/ig-reel-assets/reels/001.mp4
```
