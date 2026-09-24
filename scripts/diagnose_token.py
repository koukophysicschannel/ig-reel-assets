#!/usr/bin/env python3
"""アクセストークン・アプリの状態を切り分けるための読み取り専用診断スクリプト。
投稿(POST /media, /media_publish)は一切行わない。

環境変数:
  IG_ACCESS_TOKEN  必須
  IG_USER_ID       必須
"""

import json
import os
import sys
import urllib.error
import urllib.request

GRAPH_BASE = "https://graph.instagram.com"


def call(label, url):
    print(f"--- {label} ---")
    print(f"URL: {url.split('access_token=')[0]}access_token=***")
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            headers = dict(resp.headers)
            body = json.loads(resp.read().decode("utf-8"))
            print(f"HTTPステータス: {resp.status}")
            for h in ("x-app-usage", "x-business-use-case-usage", "x-ad-account-usage"):
                if h in headers:
                    print(f"{h}: {headers[h]}")
            print(f"body: {json.dumps(body, ensure_ascii=False)}")
    except urllib.error.HTTPError as e:
        headers = dict(e.headers) if e.headers else {}
        try:
            body = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            body = {}
        print(f"HTTPエラー: {e.code}")
        for h in ("x-app-usage", "x-business-use-case-usage", "x-ad-account-usage"):
            if h in headers:
                print(f"{h}: {headers[h]}")
        print(f"body: {json.dumps(body, ensure_ascii=False)}")
    except Exception as e:
        print(f"その他のエラー: {e}")
    print()


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    if not token or not ig_user_id:
        print("IG_ACCESS_TOKEN / IG_USER_ID が未設定です", file=sys.stderr)
        sys.exit(1)

    call(
        "1. 基本プロフィール取得 (/me) — instagram_business_basicスコープの疎通確認",
        f"{GRAPH_BASE}/me?fields=id,username,account_type,media_count&access_token={token}",
    )

    call(
        "2. コンテンツ公開の残枠確認 (/content_publishing_limit) — instagram_business_content_publishスコープの疎通確認",
        f"{GRAPH_BASE}/{ig_user_id}/content_publishing_limit?fields=config,quota_usage&access_token={token}",
    )

    call(
        "3. 直近メディア一覧 (/media) — 読み取りアクセスの疎通確認",
        f"{GRAPH_BASE}/{ig_user_id}/media?fields=id,timestamp,media_product_type&limit=5&access_token={token}",
    )


if __name__ == "__main__":
    main()
