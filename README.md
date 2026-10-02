# ig-reel-assets

物理解説チャンネルの既存ショート動画（YouTube Shorts）を、Instagramリールとして毎日1本自動投稿するための動画アセット＋投稿キュー＋GitHub Actionsワークフロー。

## 構成

- `reels/001.mp4` 〜 `reels/018.mp4` — 投稿対象の動画本体（GitHub Pagesで公開し、`video_url`としてInstagram Graph APIに渡す）
- `reels/queue.json` — 投稿キュー。先頭から`posted: false`の最初の1件を毎日1本消化する
- `scripts/publish_reel.py` — コンテナ作成→ステータス確認→公開の3ステップを実行し、成功したら`queue.json`を更新するスクリプト
- `.github/workflows/post-reel.yml` — 投稿処理本体（`workflow_dispatch`のみ。日次起動はGAS側から行う。下記参照）
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
- [x] トークン自動リフレッシュのワークフロー・スクリプトを実装
- [x] `GH_PAT_SECRETS_ADMIN` シークレットの登録（2026-09-23完了）
- [x] `refresh-token.yml`の疎通確認（2026-09-23、実際にトークンがリフレッシュされ失効予定日が更新されたことを確認済み）
- [x] 読み取り専用の診断ワークフロー（`diagnose.yml`）を追加
- [x] GitHub Actions自体の`schedule`トリガーを廃止し、GAS（`ig-reel-trigger`）による外部起動に切り替え（2026-09-26）
- [x] GAS用PAT（`GITHUB_PAT`）の発行・Script Propertiesへの登録（清水さんが2026-09-27完了）
- [x] GAS側で`setupDailyTrigger`を1回手動実行（2026-09-27完了）
- [x] GAS→GitHubの`workflow_dispatch`呼び出しに`inputs.dry_run: "false"`を明示（2026-09-30。下記「既知の問題」参照）

### 既知の問題と対応履歴

- **2026-09-24, 09-26: GitHub Actions自体の`schedule`（cron）が複数回、未発火または大幅遅延した。** 9/24は終日未発火、9/25は約5.5時間遅延、9/26も終日未発火。ワークフローの`state`・YAML構文・デフォルトブランチはいずれも正常と確認済み。GitHub公式ドキュメントが「高負荷時はスケジュール実行がドロップされうる」と明記しているため、これはこちらの設定ミスではなくGitHub Actions自体の既知の制約と判断。**対応として、GitHub側のscheduleトリガーを廃止し、Google Apps Script（`ig-reel-trigger`）の時間主導トリガーから`workflow_dispatch`を毎日呼び出す方式に切り替えた**（下記「日次起動の仕組み」参照）。未発火だった日（`002`・`004`）は`workflow_dispatch`の手動実行で埋め合わせ済み
- **2026-09-24: 投稿APIが一時的に`OAuthException code=200 "API access blocked"`を返した。** `diagnose.yml`で切り分けたところ、`/me`・`/content_publishing_limit`・`/media`（読み取り）は全て正常（レート制限も`quota_usage: 0/100`で問題なし）で、書き込み（`/media` POST）のみ失敗していた。数分後に同じ処理を再試行したところ成功したため、Meta側の一過性のエラーだったと考えられる。トークン・権限・Instagram testersの状態はいずれも正常だったことを確認済み
- **2026-09-27〜09-30: GAS導入後、4日連続で「投稿が進んでいない」状態になっていた。** GitHub Actions側は毎日`workflow_dispatch`が正常に発火し「success」で完走していたため一見問題なく見えたが、実際には**4日間すべてドライランだった**。原因は、GASが`workflow_dispatch` APIを呼ぶ際に`inputs`を渡していなかったこと。GitHubはinputs省略時、ワークフローYAMLの`dry_run`入力に宣言された既定値（`"true"`。手動UI実行時の安全な既定値のつもりだった）を採用してしまい、投稿もqueue.jsonの更新も一切行われないまま「成功」を返し続けていた。**対応として、GASのAPI呼び出しに`inputs: { dry_run: "false" }`を明示するよう修正・push済み**（2026-09-30）。同日、修正後の呼び出しで`005`が実際に投稿されたことを確認済み。
  - **教訓**: GitHub Actionsの実行結果が「success」であることは、意図した処理（今回で言えば実投稿）が実際に行われたことを保証しない。ワークフロー単体のログだけでなく、`queue.json`の進捗や実際のInstagram側の状態と突き合わせて確認する必要がある
  - **再発防止策（2026-09-30追加）**: `post-reel.yml`に「ドライラン完走の検知」ステップを追加した。`workflow_dispatch`の`source`入力（GASは常に`"gas"`を渡す）と`event_name == 'schedule'`のいずれかに該当する実行で、`dry_run`が`"true"`のまま完走した場合は明示的に`exit 1`し、GitHub標準の失敗通知メールを発生させる。人が手動でUIから意図的にdry_run実行する場合（`source`を既定の`"manual"`のまま）は対象外。実際に「source=gasだがdry_run未指定」というバグ再現パターンで失敗することと、正常なGAS呼び出し（`dry_run:"false", source:"gas"`）では誤検知しないことの両方を検証済み

## 日次起動の仕組み（GAS + GitHub Actions）

GitHub Actions自体の`schedule`は信頼性の問題により廃止した。代わりに、独立したGoogle Apps Scriptプロジェクト **`ig-reel-trigger`**（`~/Library/CloudStorage/Dropbox/GAS/ig-reel-trigger/`、スクリプトID `19fWnkwZnHHLz368Lo4e-7PjO3fPSE9XG1Ghm8FNKcg6RKM30Q--R4jS6`）が、毎日JST 18:10前後に`triggerDailyPost()`を実行し、GitHubの`workflow_dispatch` APIを1回呼ぶだけの役割を担う。投稿ロジック自体（動画選択・Instagram Graph API呼び出し・queue.json更新）はこれまで通りこのリポジトリのPython側に残したまま。

GASの時間主導トリガーとGitHub Actionsのスケジューラは無関係の別システムなので、両方が同時に同じ理由で機能しなくなる可能性は低い。

GAS側は`workflow_dispatch`呼び出し時に`inputs: { dry_run: "false" }`を明示している（省略するとYAMLの既定値`"true"`が採用されドライランになる。2026-09-30に実際に発生した不具合、上記「既知の問題」参照）。

### セットアップ手順（要手動対応・1回のみ）

1. **GAS用のPATを発行する**（トークン自動リフレッシュ用PATと同じ流れ）
   - github.com → Settings → Developer settings → **Fine-grained tokens** → Generate new token
   - Resource owner: `koukophysicschannel`、Repository access: **Only select repositories → ig-reel-assets**
   - Permissions → Repository permissions → **Actions: Read and write** のみ付与
   - Expiration: 選べる最大期間
2. `clasp open`（または https://script.google.com/d/19fWnkwZnHHLz368Lo4e-7PjO3fPSE9XG1Ghm8FNKcg6RKM30Q--R4jS6/edit ）でGASエディタを開く
3. 左側の歯車アイコン（プロジェクトの設定）→「スクリプト プロパティ」→ プロパティを追加
   - プロパティ名: `GITHUB_PAT`
   - 値: 手順1で発行したPAT
4. エディタ上部の関数選択で `setupDailyTrigger` を選び、実行ボタン（▷）をクリック
   - 初回はGoogleの権限承認画面が出るので許可する
   - 実行ログに「毎日 JST 18:10 前後に...」と出れば成功
5. （任意）`manualTestRun` を実行すると、その場でGitHub側のワークフローが起動する（投稿対象があれば実際に投稿されるので注意）

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

## 特定の時刻まで投稿を保留する（`not_before`）

通常は「先頭から`posted:false`の最初の1件」を毎日1本消化するだけだが、
特定の1件だけを決まった時刻まで投稿させたいとき（2026-10-02、ショート
「重心」で初めて使用）は、そのエントリに`not_before`
（ISO8601・タイムゾーン付き。例 `"2026-10-02T18:40:00+09:00"`）を持たせて
キューの先頭に置く。

- `publish_reel.py`の`pick_next()`が、先頭の未投稿エントリの`not_before`が
  未来ならそのエントリを**保留**とみなし、`None`を返す（`exit 0`。異常では
  ない）。**後続のエントリにはフォールバックしない**ので、先頭が保留中の
  間はキュー全体が止まる（＝その日は何も投稿されない）
- `not_before`に達していれば通常のエントリと同じに扱われる。投稿後は
  `posted:true`になるだけで、`not_before`フィールド自体は残る（無害）
- 番号は既存の連番（001〜018）を崩さず、続き番号（019〜）を新しいエントリに
  割る。**配列の並び順＝投稿順**なので、先頭に割り込ませたい場合は番号の
  連続性とは無関係に配列の先頭へ挿入してよい（`file`名と`id`が一致してい
  れば、配列中の位置とは独立）
- この仕組みは「今日だけ特定の時刻に」という一時的な需要向け。日々の運用
  （毎日18:10ごろに先頭の1本を消化）は変更していない
