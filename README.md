# ig-reel-assets

物理解説チャンネルの既存ショート動画（YouTube Shorts）を、Instagramリールとして毎日1本自動投稿するための動画アセット＋投稿キュー＋GitHub Actionsワークフロー。

## 構成

- `reels/001.mp4` 〜 `reels/018.mp4` — 投稿対象の動画本体（GitHub Pagesで公開し、`video_url`としてInstagram Graph APIに渡す）
- `reels/queue.json` — 投稿キュー。先頭から`posted: false`の最初の1件を毎日1本消化する
- `scripts/publish_reel.py` — コンテナ作成→ステータス確認→公開の3ステップを実行し、成功したら`queue.json`を更新するスクリプト
- `.github/workflows/post-reel.yml` — 日次実行用のGitHub Actionsワークフロー（毎日 JST 18:00 に自動実行。手動実行も可能）

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
- [ ] アクセストークンの60日ごとのリフレッシュ運用を別途仕組み化する（未着手）

## 動画URLの形式

```
https://koukophysicschannel.github.io/ig-reel-assets/reels/001.mp4
```
