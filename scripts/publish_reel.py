#!/usr/bin/env python3
"""queue.json から1本選び、Instagramリールとして公開する（くり返し投稿）。

選び方（2026-10-23 に「先頭から posted:false の1件」から変更）:
  キューの動画を順に使い切ったら止まる作りだったため、2026-10-14〜10-22 は
  毎日「投稿対象がありません」で何も投稿されなかった。くり返し投稿に変え、
  各動画に last_posted_at（最後に投稿した日時、UTC）を持たせる。
  毎回、caption のある動画のうち
    1. 一度も投稿していないもの（last_posted_at が空）を先に
    2. 次に last_posted_at がいちばん古いもの
    3. 同じなら id（番号）の小さいもの
  を選ぶ。caption が空（018 など）の動画は飛ばし続ける。

1日1本の上限（重複投稿の防止）:
  同じ日（JST）にすでに1本投稿していたら、何もせず正常終了（exit 0）する。
  判定は2重にしている。
    a. queue.json の last_posted_at が今日（JST）のものがある
    b. Instagram 側の最新の投稿が今日（JST）のものである
       （投稿は成功したのに queue.json の記録・push に失敗した場合や、
       公開APIがエラーを返したのに実際は投稿されていた場合でも、
       再実行で2本目を出さないため。b を確かめられないときは投稿しない）
  b で今日の投稿が見つかり、キャプション等から queue.json のどの動画か
  分かれば、その動画の記録を補正してから終了する。

環境変数:
  IG_ACCESS_TOKEN  必須。Instagram Graph API の長期アクセストークン。
  IG_USER_ID       必須。投稿先InstagramアカウントのID。
  PAGES_BASE_URL   必須。動画を公開しているGitHub PagesのベースURL
                    (例: https://koukophysicschannel.github.io/ig-reel-assets)
  DRY_RUN          "true" の場合、実際のAPI呼び出しを行わず対象と動画URLの
                    到達性だけを確認して終了する。

queue.jsonのnot_beforeについて（仕組みは従来どおり）:
  特定の1件を「この時刻より前には投稿しない」ようにしたいとき、そのエントリに
  not_before（ISO8601、タイムゾーン付き。例 "2026-10-02T18:40:00+09:00"）
  を持たせる。上の順で選ばれた1本が not_before を満たしていなければ、
  pick_next は None を返して「今回は何も投稿しない」（exit 0、異常ではない）。
  次の候補へフォールバックはしない。新しい動画（未投稿）は最優先で選ばれる
  ので、未投稿の新しい動画に not_before を付ければ、その時刻まで全体が待つ。
  not_before が過去になった動画は通常どおり扱われる。

queue.json のフィールド:
  last_posted_at  最後に投稿した日時（UTC, "...Z"）。選び方はこれだけで決まる
  last_media_id   最後に投稿したときの media_id
  post_log        投稿の履歴 [{posted_at, media_id}, ...]（古い順）
  posted / posted_at / media_id
                  2026-10-23 以前の作りの名残（初回投稿の記録）。
                  選び方には使わない。初回投稿時だけ埋める
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
JST = dt.timezone(dt.timedelta(hours=9))


def parse_time(s):
    """'2026-10-13T09:08:19Z' / '...+0000' / '...+09:00' -> aware datetime。"""
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    elif len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":
        s = s[:-2] + ":" + s[-2:]          # +0000 -> +00:00（Graph APIの形式）
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t


def jst_date(t):
    return t.astimezone(JST).date()


def load_queue():
    with open(QUEUE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(queue):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
        f.write("\n")


def selection_key(entry):
    """選ぶ順の並べ替えキー: 未投稿が先 → last_posted_at が古い順 → id の小さい順。"""
    last = parse_time(entry.get("last_posted_at"))
    if last is None:
        return (0, dt.datetime.min.replace(tzinfo=dt.timezone.utc), entry["id"])
    return (1, last, entry["id"])


def pick_next(queue, now=None):
    """caption のある動画から、selection_key の順で最初の1本を返す。

    その1本に not_before があり、現在時刻がまだ達していなければ、保留とみなし
    None を返す（次の候補は見ない。その回は何も投稿しない）。
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    candidates = sorted((e for e in queue if e.get("caption")), key=selection_key)
    if not candidates:
        return None
    entry = candidates[0]
    nb = entry.get("not_before")
    if nb and now < parse_time(nb):
        print(f"選ばれた {entry['id']} は not_before={nb} で保留中です"
              f"（現在 {now.isoformat()}）。今回は何も投稿しません。")
        return None
    return entry


def posted_today_in_queue(queue, now):
    """queue.json の記録上、今日（JST）すでに投稿した動画があれば返す。"""
    today = jst_date(now)
    for e in queue:
        last = parse_time(e.get("last_posted_at"))
        if last and jst_date(last) == today:
            return e
    return None


def record_post(entry, posted_at, media_id):
    """投稿1回ぶんを queue.json のエントリに記録する。"""
    entry["last_posted_at"] = posted_at
    entry["last_media_id"] = media_id
    entry.setdefault("post_log", []).append({"posted_at": posted_at, "media_id": media_id})
    if not entry.get("posted"):
        entry["posted"] = True
        entry["posted_at"] = posted_at
        entry["media_id"] = media_id


def find_entry_for_media(queue, media):
    """Instagram の投稿（id・caption）が queue.json のどの動画かを探す。"""
    mid = media.get("id")
    for e in queue:
        ids = {e.get("media_id"), e.get("last_media_id")} | {
            x.get("media_id") for x in e.get("post_log", [])}
        if mid and mid in ids:
            return e
    cap = (media.get("caption") or "").strip()
    if cap:
        hits = [e for e in queue if (e.get("caption") or "").strip() == cap]
        if len(hits) == 1:
            return hits[0]
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


def ig_recent_media(ig_user_id, token, limit=1):
    """Instagram 側の最新の投稿（新しい順）を返す。失敗したら例外をそのまま投げる。"""
    url = (
        f"{GRAPH_BASE}/{ig_user_id}/media"
        f"?fields=id,timestamp,caption&limit={limit}&access_token={token}"
    )
    return http_json(url).get("data") or []


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


def main(now=None):
    token = os.environ.get("IG_ACCESS_TOKEN")
    ig_user_id = os.environ.get("IG_USER_ID")
    pages_base = os.environ.get("PAGES_BASE_URL")
    dry_run = os.environ.get("DRY_RUN", "").lower() == "true"
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    if not pages_base:
        print("PAGES_BASE_URL が未設定です", file=sys.stderr)
        sys.exit(1)

    queue = load_queue()
    print(f"現在: {now.astimezone(JST).isoformat()}（JST）")

    # 1日1本の上限（a）: queue.json の記録
    done = posted_today_in_queue(queue, now)
    if done:
        print(f"今日（JST {jst_date(now)}）はすでに {done['id']} を投稿済みです"
              f"（last_posted_at={done['last_posted_at']}）。何もせず終了します。")
        sys.exit(0)

    entry = pick_next(queue, now)
    if entry is None:
        print("投稿対象がありません（caption付きの動画がない、"
              "または選ばれた動画がnot_beforeで保留中）")
        sys.exit(0)

    video_url = f"{pages_base.rstrip('/')}/{entry['file']}"
    print(f"対象: {entry['id']} ({entry.get('source_title')})"
          f"  last_posted_at={entry.get('last_posted_at')}")
    print(f"video_url: {video_url}")
    print(f"caption: {entry['caption']}")

    status, content_length = check_url_reachable(video_url)
    print(f"video_url到達性チェック: status={status} size={content_length}")
    if status != 200:
        print("video_urlに到達できません。GitHub Pagesの反映待ちの可能性があります。", file=sys.stderr)
        sys.exit(1)

    # 1日1本の上限（b）: Instagram 側の実際の最新投稿
    if token and ig_user_id:
        try:
            recent = ig_recent_media(ig_user_id, token, limit=1)
        except Exception as exc:
            print(f"Instagram側の最新投稿を確認できませんでした: {describe_error(exc)}",
                  file=sys.stderr)
            if dry_run:
                print("（DRY_RUNのため続行します）")
                recent = []
            else:
                print("重複投稿を避けるため、今回は投稿しません。", file=sys.stderr)
                sys.exit(1)
        if recent:
            latest = recent[0]
            lt = parse_time(latest.get("timestamp"))
            print(f"Instagram側の最新投稿: id={latest.get('id')} "
                  f"timestamp={lt.astimezone(JST).isoformat() if lt else None}")
            if lt and jst_date(lt) == jst_date(now):
                e = find_entry_for_media(queue, latest)
                print(f"Instagram上で今日（JST）すでに投稿されています"
                      f"（queue.json の動画: {e['id'] if e else '特定できず'}）。")
                if e and not dry_run:
                    ts = lt.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    if e.get("last_posted_at") != ts:
                        record_post(e, ts, latest.get("id"))
                        save_queue(queue)
                        print(f"queue.json の {e['id']} の記録を補正しました"
                              f"（last_posted_at={ts}）。")
                print("何もせず終了します。")
                sys.exit(0)
    elif not dry_run:
        print("🔑 TOKEN_ERROR: IG_ACCESS_TOKEN / IG_USER_ID が未設定です", file=sys.stderr)
        sys.exit(1)

    if dry_run:
        print("DRY_RUN=true のため、ここで終了します（実際の投稿は行っていません）")
        return

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
                "今日の分はこれで投稿済みの可能性があります。再実行しても、"
                "Instagram側の最新投稿が今日なら2本目は出さずに記録だけ補正します。",
                file=sys.stderr,
            )
        sys.exit(1)

    record_post(entry, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), media_id)
    save_queue(queue)
    print("queue.json を更新しました")


if __name__ == "__main__":
    main()
