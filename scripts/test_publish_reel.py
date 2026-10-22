#!/usr/bin/env python3
"""publish_reel.py の選び方と1日1本の上限を、擬似データで確かめる（API・ネットには出ない）。

    python3 scripts/test_publish_reel.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish_reel as P  # noqa: E402

UTC = dt.timezone.utc
JST = dt.timezone(dt.timedelta(hours=9))


def entry(id_, last=None, caption="cap " + "x", **kw):
    e = {"id": id_, "file": f"reels/{id_}.mp4", "caption": caption,
         "last_posted_at": last, "last_media_id": None, "post_log": []}
    if last:
        e["post_log"] = [{"posted_at": last, "media_id": "m" + id_}]
        e["last_media_id"] = "m" + id_
        e.update(posted=True, posted_at=last, media_id="m" + id_)
    e.update(kw)
    return e


def at_jst(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=JST).astimezone(UTC)


class PickNext(unittest.TestCase):
    def test_all_posted_picks_oldest(self):
        q = [entry("003", "2026-09-25T14:35:44Z"), entry("001", "2026-09-23T10:04:24Z"),
             entry("002", "2026-09-24T11:31:55Z")]
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18, 10))["id"], "001")

    def test_never_posted_comes_first(self):
        q = [entry("001", "2026-09-23T10:04:24Z"), entry("021")]
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18))["id"], "021")

    def test_tie_goes_to_smaller_id(self):
        t = "2026-10-01T09:00:00Z"
        q = [entry("007", t), entry("003", t), entry("005", t)]
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18))["id"], "003")
        q = [entry("022"), entry("021")]            # 未投稿どうしも番号順
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18))["id"], "021")

    def test_018_without_caption_is_skipped(self):
        q = [entry("018", None, caption=None), entry("001", "2026-09-23T10:04:24Z")]
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18))["id"], "001")
        q = [entry("018", None, caption="")]          # 候補が018だけなら何も選ばない
        self.assertIsNone(P.pick_next(q, at_jst(2026, 10, 23, 18)))

    def test_not_before_holds_without_fallback(self):
        q = [entry("021", not_before="2026-10-23T18:40:00+09:00"),
             entry("001", "2026-09-23T10:04:24Z")]
        self.assertIsNone(P.pick_next(q, at_jst(2026, 10, 23, 18, 10)))
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18, 41))["id"], "021")

    def test_past_not_before_is_ignored(self):
        q = [entry("019", "2026-10-02T09:42:49Z", not_before="2026-10-02T18:40:00+09:00"),
             entry("001", "2026-09-23T10:04:24Z")]
        self.assertEqual(P.pick_next(q, at_jst(2026, 10, 23, 18))["id"], "001")


class Rotation(unittest.TestCase):
    def test_rotates_through_all_then_wraps(self):
        q = [entry(f"{i:03d}", f"2026-09-{10 + i:02d}T09:00:00Z") for i in range(1, 4)]
        q.append(entry("018", None, caption=None))
        picked = []
        for day in range(23, 30):
            now = at_jst(2026, 10, day, 18, 10)
            e = P.pick_next(q, now)
            picked.append(e["id"])
            P.record_post(e, now.strftime("%Y-%m-%dT%H:%M:%SZ"), "new" + str(day))
        self.assertEqual(picked, ["001", "002", "003", "001", "002", "003", "001"])
        self.assertEqual(len(q[0]["post_log"]), 4)


class DailyGuard(unittest.TestCase):
    """main() を通しで動かし、2回目の実行で投稿APIが呼ばれないことを確かめる。"""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump([entry("001", "2026-09-23T10:04:24Z"), entry("002", "2026-09-24T11:31:55Z"),
                   entry("018", None, caption=None)], self.tmp)
        self.tmp.close()
        self.patches = [
            mock.patch.object(P, "QUEUE_PATH", self.tmp.name),
            mock.patch.object(P, "check_url_reachable", return_value=(200, "1")),
            mock.patch.dict(os.environ, {"IG_ACCESS_TOKEN": "t", "IG_USER_ID": "u",
                                         "PAGES_BASE_URL": "https://example.invalid",
                                         "DRY_RUN": "false"}),
        ]
        for p in self.patches:
            p.start()
        self.ig = []                                  # Instagram側の投稿（新しい順）
        self.create = mock.patch.object(P, "create_container",
                                        return_value={"id": "c1"}).start()
        mock.patch.object(P, "poll_status", return_value=True).start()
        self.publish = mock.patch.object(P, "publish_container",
                                         side_effect=self._publish).start()
        mock.patch.object(P, "ig_recent_media",
                          side_effect=lambda *a, **k: self.ig[:1]).start()

    def _publish(self, *a):
        mid = f"media{len(self.ig) + 1}"
        self.ig.insert(0, {"id": mid, "timestamp": self.now.strftime("%Y-%m-%dT%H:%M:%S+0000"),
                           "caption": "cap x"})
        return {"id": mid}

    def tearDown(self):
        mock.patch.stopall()
        os.unlink(self.tmp.name)

    def run_main(self, now):
        self.now = now
        with mock.patch.object(P.time, "gmtime", return_value=now.timetuple()):
            try:
                P.main(now)
            except SystemExit as e:
                return e.code
        return 0

    def queue(self):
        with open(self.tmp.name, encoding="utf-8") as f:
            return json.load(f)

    def save(self, q):
        with open(self.tmp.name, "w", encoding="utf-8") as f:
            json.dump(q, f)

    def test_second_run_same_day_does_nothing(self):
        self.assertEqual(self.run_main(at_jst(2026, 10, 23, 18, 6)), 0)
        self.assertEqual(self.publish.call_count, 1)
        first = {e["id"]: e for e in self.queue()}
        self.assertEqual(first["001"]["last_posted_at"], "2026-10-23T09:06:00Z")
        self.assertEqual(self.run_main(at_jst(2026, 10, 23, 21, 0)), 0)   # 同じ日の再実行
        self.assertEqual(self.publish.call_count, 1)                      # 2本目は出ない
        self.assertEqual(self.run_main(at_jst(2026, 10, 24, 18, 6)), 0)   # 翌日は002
        self.assertEqual(self.publish.call_count, 2)
        self.assertEqual({e["id"]: e for e in self.queue()}["002"]["last_media_id"], "media2")

    def test_ig_side_guard_when_queue_record_was_lost(self):
        # 投稿は成功したが queue.json の記録が残らなかった（pushの失敗など）、という状況
        self.ig = [{"id": "lost1", "timestamp": "2026-10-23T09:07:00+0000", "caption": "cap x"}]
        q = self.queue()
        q[0]["caption"] = "cap x"                     # 001 のキャプションと一致させる
        q[1]["caption"] = "cap y"
        self.save(q)
        self.assertEqual(self.run_main(at_jst(2026, 10, 23, 21, 0)), 0)
        self.assertEqual(self.publish.call_count, 0)
        fixed = {e["id"]: e for e in self.queue()}["001"]
        self.assertEqual(fixed["last_posted_at"], "2026-10-23T09:07:00Z")  # 記録を補正
        self.assertEqual(fixed["last_media_id"], "lost1")

    def test_jst_day_boundary(self):
        # 前日23:30 JST に投稿済みでも、0:10 JST は別の日として投稿できる
        q = self.queue()
        q[0]["last_posted_at"] = at_jst(2026, 10, 22, 23, 30).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.save(q)
        self.assertEqual(self.run_main(at_jst(2026, 10, 23, 0, 10)), 0)
        self.assertEqual(self.publish.call_count, 1)

    def test_cannot_check_instagram_means_no_post(self):
        mock.patch.object(P, "ig_recent_media", side_effect=RuntimeError("down")).start()
        self.assertEqual(self.run_main(at_jst(2026, 10, 23, 18, 6)), 1)
        self.assertEqual(self.publish.call_count, 0)

    def test_dry_run_never_posts(self):
        with mock.patch.dict(os.environ, {"DRY_RUN": "true"}):
            self.assertEqual(self.run_main(at_jst(2026, 10, 23, 18, 6)), 0)
        self.assertEqual(self.create.call_count, 0)
        self.assertIsNone({e["id"]: e for e in self.queue()}["001"].get("post_log")[1:] or None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
