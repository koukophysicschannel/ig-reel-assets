# ig-reel-assets

物理解説チャンネルの既存ショート動画（YouTube Shorts）を、Instagramリールとして毎日1本自動投稿するための動画アセット＋投稿キュー＋GitHub Actionsワークフロー。

## 構成

- `reels/001.mp4` 〜 `reels/018.mp4` — 投稿対象の動画本体（GitHub Pagesで公開し、`video_url`としてInstagram Graph APIに渡す）
- `reels/queue.json` — 投稿キュー。先頭から`posted: false`の最初の1件を毎日1本消化する
- `scripts/publish_reel.py` — コンテナ作成→ステータス確認→公開の3ステップを実行し、成功したら`queue.json`を更新するスクリプト
- `.github/workflows/post-reel.yml` — 日次実行用のGitHub Actionsワークフロー（毎日 JST 18:07 に自動実行。手動実行も可能）
- `scripts/refresh_token.py` / `.github/workflows/refresh-token.yml` — 週次でアクセストークンをリフレッシュし、GitHub Secretsを自動更新するワークフロー（毎週月曜 JST 12:00）
- `scripts/diagnose_token.py` / `.github/workflows/diagnose.yml` — 読み取り専用の診断ワークフロー。投稿失敗時に`gh workflow run diagnose.yml`で実行し、トークン・権限・レート制限のどれが原因かを切り分ける
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
- [x] `schedule`を有効化（2026-09-23〜）
- [x] トークン自動リフレッシュのワークフロー・スクリプトを実装
- [x] `GH_PAT_SECRETS_ADMIN` シークレットの登録（2026-09-23完了）
- [x] `refresh-token.yml`の疎通確認（2026-09-23、実際にトークンがリフレッシュされ失効予定日が更新されたことを確認済み）
- [x] 読み取り専用の診断ワークフロー（`diagnose.yml`）を追加

### 既知の問題と対応履歴

- **2026-09-24: `schedule`（cron `"0 9 * * *"`）が一度も発火しなかった。** GitHub Actions側では`workflow`の`state`は`active`、YAML構文・デフォルトブランチとも正常であることを確認済みだが、原因不明のまま丸1日発火せず、その日の投稿（`002`）は`workflow_dispatch`で手動実行して対応した。GitHub公式ドキュメントに「毎時0分ちょうどのcronは高負荷時に遅延・未発火しやすい」とあるため、cronを`"7 9 * * *"`（JST 18:07）に変更した。次回以降の発火有無を観察中
- **2026-09-24: 投稿APIが一時的に`OAuthException code=200 "API access blocked"`を返した。** `diagnose.yml`で切り分けたところ、`/me`・`/content_publishing_limit`・`/media`（読み取り）は全て正常（レート制限も`quota_usage: 0/100`で問題なし）で、書き込み（`/media` POST）のみ失敗していた。数分後に同じ処理を再試行したところ成功したため、Meta側の一過性のエラーだったと考えられる。トークン・権限・Instagram testersの状態はいずれも正常だったことを確認済み

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
