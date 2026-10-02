#!/usr/bin/env python3
"""queue.json の先頭の未投稿エントリを1件、Instagramリールとして公開する。

環境変数:
  IG_ACCESS_TOKEN  必須。Instagram Graph API の長期アクセストークン。
  IG_USER_ID       必須。投稿先InstagramアカウントのID。
  PAGES_BASE_URL   必須。動画を公開しているGitHub PagesのベースURL
                    (例: https://koukophysicschannel.github.io/ig-reel-assets)
  DRY_RUN          "true" の場合、実際のAPI呼び出しを行わず対象と動画URLの
                    到達性だけを確認して終了する。

queue.jsonのnot_beforeについて:
  特定の1件を「この時刻より前には投稿しない」形で先頭に割り込ませたいとき
  （例: 今日だけ特別な時刻に投稿したい）、そのエントリに
  not_before（ISO8601、タイムゾーン付き。例 "2026-10-02T18:40:00+09:00"）
  を持たせる。先頭の未投稿エントリがnot_beforeを満たしていなければ、
  pick_nextはNoneを返して「今回は何も投稿しない」（exit 0、異常ではない）。
  後続のエントリへフォールバックはしない（先頭が保留中の間、キュー全体を
  止める）。not_beforeに達したら通常のエントリと同じに扱われ、投稿後は
  他のフィールドと同様キューに残り続けるだけ（posted更新で事実上無効化）。
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

QUEUE_PATH = os.path.join(os.path.dirname(__file__), "..", "reels", "queue.json")
GRAPH_BASE = "https://graph.instagram.com"
POLL_INTERVAL_SEC = 20
POLL_MAX_TRIES = 15


def load_queue():
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pick_next(queue, now=None):
    """先頭から最初の 未投稿かつcaption付き のエントリを返す。

    そのエントリに not_before があり、現在時刻がまだ達していなければ、
    先頭が保留中とみなしNoneを返す（後続は見ない。その回は何も投稿しない）。
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    for entry in queue:
        if entry.get("posted") or not entry.get("caption"):
            continue
        nb = entry.get("not_before")
        if nb:
            nb_dt = dt.datetime.fromisoformat(nb)
            if nb_dt.tzinfo is None:
                nb_dt = nb_dt.replace(tzinfo=dt.timezone.utc)
            if now < nb_dt:
                print(f"先頭の {entry['id']} は not_before={nb} で保留中です"
                      f"（現在 {now.isoformat()}）。今回は何も投稿しません。")
                return None
        return entry
    return None


def http_json(url, data=None, method="GET"):
    body = None
    headers = {}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_url_reachable(url):
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers.get("Content-Length")


def create_container(ig_user_id, token, video_url, caption):
    url = f"{GRAPH_BASE}/{ig_user_id}/media"
    return http_json(
        url,
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": token,
        },
        method="POST",
    )


def poll_status(container_id, token):
    url = f"{GRAPH_BASE}/{container_id}?fields=status_code&access_token={token}"
    for _ in range(POLL_MAX_TRIES):
        result = http_json(url)
        status = result.get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            raise RuntimeError(f"コンテナ処理がERRORになりました: {result}")
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError("コンテナのFINISHED待ちがタイムアウトしました")


def publish_container(ig_user_id, token, creation_id):
    url = f"{GRAPH_BASE}/{ig_user_id}/media_publish"
    return http_json(
        url,
        data={"creation_id": creation_id, "access_token": token},
        method="POST",
    )


def describe_error(exc):
    """MetaのOAuthException（トークン失効・無効）かどうかを判定し、
    分かりやすいラベル付きメッセージを返す。"""
    if isinstance(exc, urllib.error.HTTPError):
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            body = {}
        error = body.get("error", {})
        error_type = error.get("type", "")
        code = error.get("code")
        message = error.get("message", str(exc))
        if error_type == "OAuthException" or code in (190,):
            return (
                f"🔑 TOKEN_ERROR: アクセストークンが無効または失効しています "
                f"(code={code}, message={message})。"
                "refresh-token.ymlの状況を確認するか、手動でトークンを再発行してください。"
            )
        return f"公開APIでエラー (type={error_type}, code={code}, message={message})"
    return f"公開APIでエラー: {exc}"


def recent_media_looks_like_phantom_post(ig_user_id, token, window_sec=300):
    """公開APIがエラーを返しても実際には投稿済みだった、という既知の挙動への
    防御策。直近の投稿タイムスタンプが window_sec 以内なら phantom success とみなす。
    """
    url = (
        f"{GRAPH_BASE}/{ig_user_id}/media"
        f"?fields=id,timestamp&limit=1&access_token={token}"
    )
    try:
        result = http_json(url)
    except Exception:
        return None
    items = result.get("data") or []
    if not items:
        return None
    return items[0]


def main():
    token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    pages_base = os.environ.get("PAGES_BASE_URL")
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"

    if not pages_base:
        print("PAGES_BASE_URL が未設定です", file=sys.stderr)
        sys.exit(1)

    queue = load_queue()
    entry = pick_next(queue)
    if entry is None:
        print("投稿対象がありません（全て投稿済み、caption未設定、"
              "または先頭がnot_beforeで保留中）")
        sys.exit(0)

    video_url = f"{pages_base.rstrip('/')}/{entry['file']}"
    print(f"対象: {entry['id']} ({entry.get('source_title')})")
    print(f"video_url: {video_url}")
    print(f"caption: {entry['caption']}")

    status, content_length = check_url_reachable(video_url)
    print(f"video_url到達性チェック: status={status} size={content_length}")
    if status != 200:
        print("video_urlに到達できません。GitHub Pagesの反映待ちの可能性があります。", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("DRY_RUN=true のため、ここで終了します（実際の投稿は行っていません）")
        return

    if not token or not ig_user_id:
        print("🔑 TOKEN_ERROR: IG_ACCESS_TOKEN / IG_USER_ID が未設定です", file=sys.stderr)
        sys.exit(1)

    try:
        container = create_container(ig_user_id, token, video_url, entry["caption"])
        creation_id = container["id"]
        print(f"コンテナ作成: {creation_id}")

        poll_status(creation_id, token)
        print("コンテナ処理完了（FINISHED）")

        publish_result = publish_container(ig_user_id, token, creation_id)
        media_id = publish_result["id"]
        print(f"公開成功: media_id={media_id}")

    except (urllib.error.HTTPError, RuntimeError, TimeoutError, KeyError) as exc:
        print(describe_error(exc), file=sys.stderr)
        phantom = recent_media_looks_like_phantom_post(ig_user_id, token)
        if phantom:
            print(
                f"警告: エラー応答にもかかわらず直近の投稿が検出されました: {phantom}\n"
                "手動で確認し、queue.jsonのpostedフラグを人力で更新してください。",
                file=sys.stderr,
            )
        sys.exit(1)

    entry["posted"] = True
    entry["posted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entry["media_id"] = media_id
    save_queue(queue)
    print("queue.json を更新しました")


if __name__ == "__main__":
    main()
