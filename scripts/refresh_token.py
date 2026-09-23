#!/usr/bin/env python3
"""Instagram長期アクセストークンをリフレッシュし、GitHub Secretsを更新する。

環境変数:
  IG_ACCESS_TOKEN       必須。現在の長期アクセストークン（24時間以上経過している必要あり）。
  GH_PAT_SECRETS_ADMIN  必須。対象リポジトリのSecrets書き込み権限を持つPAT
                        （`gh secret set` の認証に使う。GH_TOKENとして渡される想定）。
  GITHUB_REPOSITORY     GitHub Actions実行時に自動設定される "owner/repo"。
  WARN_THRESHOLD_DAYS   任意。残り日数がこれを下回ったら警告的に失敗する（既定14）。

このスクリプトは以下を行う:
  1. graph.instagram.com/refresh_access_token を呼び、新しい60日トークンを取得
  2. 成功したら `gh secret set IG_ACCESS_TOKEN` でSecretsを更新
  3. state/token_status.json に最終リフレッシュ日時・新しい失効予定日を記録
  4. リフレッシュの成否に関わらず、記録されている失効予定日までの残り日数が
     WARN_THRESHOLD_DAYS を下回っていたら、意図的に失敗して通知を出す
"""

import datetime
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "token_status.json")
GRAPH_BASE = "https://graph.instagram.com"


def load_state():
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def refresh_token(current_token):
    url = (
        f"{GRAPH_BASE}/refresh_access_token"
        f"?grant_type=ig_refresh_token&access_token={current_token}"
    )
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def update_github_secret(repo, new_token):
    result = subprocess.run(
        ["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", repo],
        input=new_token.encode("utf-8"),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"gh secret set が失敗しました: {result.stderr.decode('utf-8', 'replace')}"
        )


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    warn_threshold_days = int(os.environ.get("WARN_THRESHOLD_DAYS", "14"))

    if not token:
        print("🔑 TOKEN_ERROR: IG_ACCESS_TOKEN が未設定です", file=sys.stderr)
        sys.exit(1)

    refresh_failed = False
    try:
        print("トークンのリフレッシュを試行します...")
        result = refresh_token(token)
        new_token = result["access_token"]
        expires_in = result.get("expires_in", 60 * 24 * 3600)

        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(seconds=expires_in)

        if not os.environ.get("GH_PAT_SECRETS_ADMIN"):
            print(
                "🔑 TOKEN_ERROR: GH_PAT_SECRETS_ADMIN が未設定のため、"
                "新トークンをGitHub Secretsへ反映できません。"
                "README記載の手順でPATを発行・登録してください。",
                file=sys.stderr,
            )
            sys.exit(1)

        update_github_secret(repo, new_token)
        print("GitHub Secrets (IG_ACCESS_TOKEN) を更新しました")

        state = {
            "refreshed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "refresh-token.ymlによる自動更新",
        }
        save_state(state)
        print(f"リフレッシュ成功。新しい失効予定日: {state['expires_at']}")

    except (urllib.error.HTTPError, urllib.error.URLError, KeyError, RuntimeError) as exc:
        refresh_failed = True
        body = ""
        if isinstance(exc, urllib.error.HTTPError):
            try:
                body = exc.read().decode("utf-8", "replace")
            except Exception:
                body = ""
        print(f"🔑 TOKEN_ERROR: リフレッシュに失敗しました: {exc} {body}", file=sys.stderr)

    # リフレッシュの成否に関わらず、記録済みの失効予定日から残り日数を確認する。
    # 直近数週間リフレッシュが失敗し続けている場合の最後の安全網。
    try:
        state = load_state()
        expires_at = datetime.datetime.strptime(
            state["expires_at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=datetime.timezone.utc)
        remaining_days = (expires_at - datetime.datetime.now(datetime.timezone.utc)).days
        print(f"現在記録されている失効予定日までの残り日数: {remaining_days}日")

        if remaining_days < warn_threshold_days:
            print(
                f"⚠️ TOKEN_EXPIRY_WARNING: 残り{remaining_days}日しかありません"
                f"（閾値{warn_threshold_days}日）。"
                "直近のリフレッシュが継続的に失敗している可能性があります。"
                "手動でのトークン再発行を検討してください。",
                file=sys.stderr,
            )
            sys.exit(1)
    except FileNotFoundError:
        print(
            "⚠️ state/token_status.json が見つかりません。初回セットアップが未完了の可能性があります。",
            file=sys.stderr,
        )
        sys.exit(1)

    if refresh_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
