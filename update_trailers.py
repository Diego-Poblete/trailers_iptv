"""Build a public, credential-free trailer index for Poblete IPTV.

Run in GitHub Actions with IPTV_SERVER, IPTV_USERNAME and IPTV_PASSWORD secrets.
TMDB_BEARER is optional. Never publish the provider responses or this job's env.
"""

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "docs" / "trailers.json"
SCRIPT_OUTPUT = ROOT / "docs" / "trailers.js"
STATE = ROOT / "state" / "trailer-state.json"
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
RECHECK_FOUND_DAYS = 30
RECHECK_MISSING_DAYS = 14


def request_json(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {"Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 2:
                raise RuntimeError("Remote API returned HTTP %s" % error.code) from None
            time.sleep(2 ** attempt + 1)
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt == 2:
                raise RuntimeError("Remote API request or response failed") from None
            time.sleep(2 ** attempt + 1)


def youtube_id(value):
    value = str(value or "").strip()
    if YOUTUBE_ID.fullmatch(value):
        return value
    try:
        url = urllib.parse.urlparse(value)
        host = (url.hostname or "").lower()
        if host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
            candidate = urllib.parse.parse_qs(url.query).get("v", [""])[0]
            if not candidate and url.path.startswith("/shorts/"):
                candidate = url.path.split("/")[2]
        elif host in ("youtu.be", "www.youtu.be"):
            candidate = url.path.strip("/").split("/")[0]
        else:
            return ""
        return candidate if YOUTUBE_ID.fullmatch(candidate) else ""
    except (ValueError, IndexError):
        return ""


def provider_video(info):
    for key in ("youtube_trailer", "trailer", "trailer_url"):
        value = youtube_id(info.get(key))
        if value:
            return value
    return ""


def api_url(server, username, password, action, **params):
    query = {"username": username, "password": password, "action": action}
    query.update(params)
    return server.rstrip("/") + "/player_api.php?" + urllib.parse.urlencode(query)


def tmdb_request(path, bearer, **params):
    url = "https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(params)
    return request_json(url, {"Authorization": "Bearer " + bearer, "Accept": "application/json"})


def pick_tmdb_video(videos):
    options = [video for video in videos if video.get("site") == "YouTube"
               and video.get("type") == "Trailer" and youtube_id(video.get("key"))]
    options.sort(key=lambda video: (video.get("official") is True,
                                    video.get("iso_639_1") == "es",
                                    video.get("iso_639_1") == "en"), reverse=True)
    return options[0]["key"] if options else ""


def normalized_title(value):
    value = re.sub(r"\s*\(\d{4}\).*", "", str(value or ""))
    value = re.sub(r"^(?:\d+\s*[-.]\s*|(?:VOD|SERIES?)\s+)", "", value, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def tmdb_video(kind, item, info, bearer):
    if not bearer:
        return ""
    media = "movie" if kind == "movies" else "tv"
    tmdb_id = info.get("tmdb_id") or item.get("tmdb_id")
    if kind == "series" and not tmdb_id:
        title = str(item.get("name") or "")
        year = str(item.get("releaseDate") or item.get("year") or "")[:4]
        params = {"query": title}
        if year.isdigit():
            params["first_air_date_year"] = year
        results = tmdb_request("search/tv", bearer, **params).get("results") or []
        exact = [row for row in results if normalized_title(row.get("name")) == normalized_title(title)
                 and (not year.isdigit() or str(row.get("first_air_date") or "").startswith(year))]
        if len(exact) != 1:
            return ""
        tmdb_id = exact[0].get("id")
    if not str(tmdb_id or "").isdigit():
        return ""
    data = tmdb_request("%s/%s/videos" % (media, tmdb_id), bearer)
    return pick_tmdb_video(data.get("results") or [])


def load_previous():
    if not STATE.exists():
        return {"version": 1, "movies": {}, "series": {}}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("Unsupported index version")
        return data
    except (ValueError, OSError):
        raise RuntimeError("Existing trailer index is invalid; refusing to overwrite it") from None


def due(record, today):
    if not isinstance(record, dict):
        return True
    try:
        checked = dt.date.fromisoformat(record.get("checked", ""))
    except ValueError:
        return True
    interval = RECHECK_FOUND_DAYS if record.get("youtube") else RECHECK_MISSING_DAYS
    return (today - checked).days >= interval


def update(server, username, password, bearer="", batch_size=250):
    today = dt.date.today()
    data = load_previous()
    budget = batch_size
    discovered = 0
    for kind, action, id_field, detail_action, detail_field in (
        ("movies", "get_vod_streams", "stream_id", "get_vod_info", "vod_id"),
        ("series", "get_series", "series_id", "get_series_info", "series_id"),
    ):
        items = request_json(api_url(server, username, password, action))
        if not isinstance(items, list):
            raise RuntimeError("Provider catalog response has an unexpected shape")
        records = data.setdefault(kind, {})
        valid = {str(item[id_field]) for item in items if isinstance(item, dict) and item.get(id_field) is not None}
        for stale in list(records):
            if stale not in valid:
                del records[stale]
        items = [item for item in items if isinstance(item, dict)]
        items.sort(key=lambda item: int(item.get("added") or item.get("last_modified") or 0), reverse=True)
        for item in items:
            if budget <= 0:
                break
            item_id = str(item.get(id_field) or "")
            if not item_id or not due(records.get(item_id), today):
                continue
            detail = request_json(api_url(server, username, password, detail_action, **{detail_field: item_id}))
            info = detail.get("info") if isinstance(detail, dict) else None
            info = info if isinstance(info, dict) else {}
            video = provider_video(info)
            source = "provider" if video else ""
            if not video and bearer:
                try:
                    video = tmdb_video(kind, item, info, bearer)
                    source = "tmdb" if video else ""
                except RuntimeError:
                    pass
            records[item_id] = {"youtube": video, "source": source, "checked": today.isoformat()}
            budget -= 1
            discovered += bool(video)
    data["updated"] = today.isoformat()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    public = {"version": 1, "updated": data["updated"]}
    for kind in ("movies", "series"):
        public[kind] = {item_id: {"youtube": row["youtube"], "source": row["source"]}
                        for item_id, row in data[kind].items() if row.get("youtube")}
    payload = json.dumps(public, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    OUTPUT.write_text(payload + "\n", encoding="utf-8")
    SCRIPT_OUTPUT.write_text("window.POBLETE_TRAILER_FEED=" + payload + ";\n", encoding="utf-8")
    print("Checked %s titles; found %s trailers; remaining daily budget %s." % (batch_size - budget, discovered, budget))


if __name__ == "__main__":
    server = os.environ.get("IPTV_SERVER", "").strip()
    username = os.environ.get("IPTV_USERNAME", "").strip()
    password = os.environ.get("IPTV_PASSWORD", "").strip()
    bearer = os.environ.get("TMDB_BEARER", "").strip()
    if not server.startswith(("https://", "http://")) or not username or not password:
        sys.exit("Missing private IPTV_SERVER, IPTV_USERNAME or IPTV_PASSWORD secrets")
    size = max(1, min(500, int(os.environ.get("TRAILER_BATCH_SIZE", "250"))))
    try:
        update(server, username, password, bearer, size)
    except RuntimeError as error:
        sys.exit(str(error))
