# ig-reel-assets

物理解説チャンネルの既存ショート動画（YouTube Shorts）を、Instagramリールとして毎日1本自動投稿するための動画アセット＋投稿キュー＋GitHub Actionsワークフロー。

## 構成

- `reels/001.mp4` 〜 `reels/018.mp4` — 投稿対象の動画本体（GitHub Pagesで公開し、`video_url`としてInstagram Graph APIに渡す）
- `reels/queue.json` — 投稿キュー。先頭から`posted: false`の最初の1件を毎日1本消化する
- `scripts/publish_reel.py` — コンテナ作成→ステータス確認→公開の3ステップを実行し、成功したら`queue.json`を更新するスクリプト
- `.github/workflows/post-reel.yml` — 日次実行用のGitHub Actionsワークフロー（現在はスケジュール無効・手動実行のみ）

## 動作確認前に必ず確認してほしいこと

`reels/queue.json` の中に `_needs_review` フィールドが付いているエントリが3件あります。元のCSV（`shorts-mapping.csv`）とローカルファイル名からの推測でcaptionを割り当てたため、内容が実際の動画と一致しているか一度目視で確認してください。

- `006` / `017`: 「自由落下」と「鉛直投げ上げ」のどちらのCSV行がどちらの動画ファイルに対応するか、ファイル名とタイトル文言からの推測です
- `009`: 「7章_よくある」というファイル名と「2物体の衝突」というCSVタイトルの対応も推測です
- `018`: `単原子分子理想気体の定圧変化.MP4` はCSVの1〜17行目（YouTube URL付き・撮影済み）に対応する行が見つかりませんでした。caption未設定のため現状は投稿対象から自動的に除外されています。captionを設定すれば投稿対象に加わります

## セットアップ状況

- [x] GitHubリポジトリ作成・動画18本を`reels/`に配置
- [x] `queue.json`の初期データ作成
- [x] 投稿スクリプト・ワークフロー作成
- [x] GitHub Actions Secrets（`IG_ACCESS_TOKEN` / `IG_USER_ID`）設定
- [x] GitHub Pages公開設定
- [ ] `queue.json`のcaption内容を目視確認（上記の3件）
- [ ] `workflow_dispatch`（`dry_run: true`）での動作確認
- [ ] `workflow_dispatch`（`dry_run: false`）で実際に1本だけ手動投稿して確認
- [ ] 問題なければ`.github/workflows/post-reel.yml`の`schedule`のコメントを外して毎日自動実行を有効化
- [ ] アクセストークンの60日ごとのリフレッシュ運用を別途仕組み化する（未着手）

## 動画URLの形式

```
https://koukophysicschannel.github.io/ig-reel-assets/reels/001.mp4
```
