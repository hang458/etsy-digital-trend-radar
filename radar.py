"""Small, quota-aware Etsy digital listing collector and static dashboard renderer."""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
API_ROOT = "https://api.etsy.com/v3/application"
CONFIG = ROOT / "config" / "research.json"
STATE = ROOT / "state" / "radar_state.json"
SITE = ROOT / "site"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as f:
        json.dump(value, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
        temp = Path(f.name)
    temp.replace(path)


def is_digital(row: dict) -> bool:
    kind = str(row.get("type") or row.get("listing_type") or "").strip().lower()
    if row.get("is_digital") is True:
        return True
    if kind:
        return kind in {"download", "digital", "both"}
    text = f"{row.get('title', '')} {row.get('description', '')}".lower()
    return any(word in text for word in ("digital download", "printable", "template", "svg", "png"))


class Collector:
    def __init__(self, key: str, secret: str, cap: int, spacing: float):
        self.key, self.secret, self.cap, self.spacing = key, secret, cap, spacing
        self.requests = 0
        self.last_request = 0.0
        self.quota = {"daily_limit": None, "remaining_today": None, "retry_at": None}

    def get(self, path: str, **params) -> dict:
        if self.requests >= self.cap:
            raise RuntimeError("本轮 API 请求上限已到，保留已完成的采集结果")
        limit, remaining = self.quota.get("daily_limit"), self.quota.get("remaining_today")
        reserve = max(25, math.ceil(limit * 0.1)) if limit is not None else 25
        if remaining is not None and remaining <= reserve:
            self.quota["paused"] = True
            raise RuntimeError("已到 Etsy 每日额度保留线，本轮停止请求")
        wait = self.spacing - (time.monotonic() - self.last_request)
        if self.last_request and wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        request = Request(f"{API_ROOT}{path}?{urlencode(params, doseq=True)}", headers={
            "x-api-key": f"{self.key}:{self.secret}",
            "Accept": "application/json", "User-Agent": "EtsyDigitalTrendRadar/1.0",
        })
        self.requests += 1
        try:
            with urlopen(request, timeout=30) as response:
                self._headers(response.headers)
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self._headers(exc.headers or {})
            if exc.code == 429:
                delay = max(60, int((exc.headers or {}).get("Retry-After", "3600")))
                self.quota["retry_at"] = (utcnow() + timedelta(seconds=delay)).isoformat()
                raise RuntimeError("Etsy 要求暂停请求；本轮停止，等待下次运行") from exc
            if exc.code in (401, 403):
                raise RuntimeError("Etsy 拒绝了 API 凭证，请检查 GitHub Secrets 或本地环境变量") from exc
            raise RuntimeError(f"Etsy API 返回 HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("Etsy API 网络响应失败") from exc

    def _headers(self, headers) -> None:
        h = {str(k).lower(): v for k, v in headers.items()}
        for name, target in (("x-limit-per-day", "daily_limit"), ("x-remaining-today", "remaining_today")):
            try:
                self.quota[target] = int(h[name])
            except (KeyError, TypeError, ValueError):
                pass


def normalize(raw: dict, keyword: str, rank: int) -> dict | None:
    if not raw.get("listing_id") or not is_digital(raw):
        return None
    price = raw.get("price") or {}
    amount = price.get("amount") if isinstance(price, dict) else price
    divisor = (price.get("divisor") or 100) if isinstance(price, dict) else 1
    try:
        price_value = round(float(amount) / float(divisor), 2) if amount is not None else None
    except (TypeError, ValueError, ZeroDivisionError):
        price_value = None
    images = raw.get("images") or raw.get("Images") or []
    image = images[0].get("url_570xN") if images and isinstance(images[0], dict) else None
    shop = raw.get("shop") or raw.get("Shop") or {}
    listing_id = int(raw["listing_id"])
    return {
        "listing_id": listing_id,
        "title": html.unescape(str(raw.get("title") or f"Listing {listing_id}")).strip(),
        "url": raw.get("url") or f"https://www.etsy.com/listing/{listing_id}",
        "image_url": image,
        "price": price_value,
        "currency": (price.get("currency_code") if isinstance(price, dict) else None) or "USD",
        "favorites": raw.get("num_favorers", raw.get("favorites")),
        "views": raw.get("views"),
        "shop_name": shop.get("shop_name") or raw.get("shop_name") or "",
        "source_query": keyword,
        "search_rank": rank,
        "listing_type": "download",
    }


def merge(old: dict, incoming: dict, captured: str, max_samples: int) -> dict:
    prev = old.get("items", {})
    hits: dict[str, dict] = {}
    for row in incoming:
        key = str(row["listing_id"])
        if key not in hits:
            hits[key] = {**prev.get(key, {}), **row, "queries": []}
        hits[key]["queries"] = sorted(set(hits[key].get("queries", [])) | {row["source_query"]})
        hits[key]["search_rank"] = min(hits[key].get("search_rank", row["search_rank"]), row["search_rank"])
    items = {**prev}
    for key, row in hits.items():
        samples = list(items.get(key, {}).get("samples", []))
        sample = {"captured_at": captured, "favorites": row.get("favorites"), "views": row.get("views"), "rank": row["search_rank"]}
        if samples and samples[-1].get("captured_at") == captured:
            samples[-1] = sample
        else:
            samples.append(sample)
        cutoff = utcnow() - timedelta(days=35)
        samples = [s for s in samples if (iso(s.get("captured_at")) or cutoff - timedelta(seconds=1)) >= cutoff][-max_samples:]
        first = items.get(key, {}).get("first_seen_at", captured)
        row.update({"samples": samples, "first_seen_at": first, "last_seen_at": captured})
        row.update(metrics(row))
        items[key] = row
    cutoff = utcnow() - timedelta(days=35)
    items = {k: v for k, v in items.items() if (iso(v.get("last_seen_at")) or cutoff - timedelta(seconds=1)) >= cutoff}
    return items


def metrics(row: dict) -> dict:
    samples = row.get("samples", [])
    before = None
    current = samples[-1] if samples else {}
    current_time = iso(current.get("captured_at"))
    if current_time:
        options = []
        for sample in samples[:-1]:
            then = iso(sample.get("captured_at"))
            if then:
                hours = (current_time - then).total_seconds() / 3600
                if 2 <= hours <= 30:
                    options.append((abs(hours - 24), hours, sample))
        if options:
            _, hours, before = min(options, key=lambda x: x[0])
        else:
            hours = None
    else:
        hours = None
    growth = None
    if before and current.get("favorites") is not None and before.get("favorites") is not None:
        delta = max(0, float(current["favorites"]) - float(before["favorites"]))
        growth = round(delta * 24 / hours, 2) if hours else None
    fav = max(0, float(row.get("favorites") or 0))
    rank = max(1, int(row.get("search_rank") or 100))
    repeat = len(row.get("queries", []))
    score = 12 * math.log1p(fav) + max(0, 101 - min(rank, 100)) * 0.7 + repeat * 3 + (growth or 0) * 4
    return {"favorites_24h": growth, "comparison_hours": round(hours, 1) if hours else None, "trend_score": round(score, 1)}


def collect(config: dict, state: dict, collector: Collector) -> tuple[dict, list[str]]:
    terms = config["keywords"]
    start = int(state.get("next_keyword", 0)) % len(terms)
    count = min(int(config["searches_per_run"]), len(terms), collector.cap)
    selected = [terms[(start + i) % len(terms)] for i in range(count)]
    rows: list[dict] = []
    errors: list[str] = []
    completed = 0
    for keyword in selected:
        try:
            data = collector.get("/listings/active", keywords=keyword, limit=int(config["results_per_search"]),
                                 offset=0, sort_on="score", sort_order="desc", includes="Images,Shop")
            completed += 1
            for rank, raw in enumerate(data.get("results", []), start=1):
                row = normalize(raw, keyword, rank)
                if row:
                    rows.append(row)
        except RuntimeError as exc:
            errors.append(str(exc))
            if collector.quota.get("retry_at") or collector.quota.get("paused"):
                break
    # The active-listings search endpoint does not return image associations.
    # Hydrate the highest-ranked results with Etsy's batch listing endpoint,
    # which supports includes=Images. Keep within the configured per-run quota.
    unique_rows = {}
    for row in rows:
        unique_rows.setdefault(str(row["listing_id"]), row)
    image_budget = max(0, collector.cap - collector.requests) * 100
    image_ids = [
        listing_id for listing_id, _ in sorted(
            unique_rows.items(),
            key=lambda pair: (pair[1].get("search_rank", 9999), -float(pair[1].get("favorites") or 0)),
        )[:image_budget]
    ]
    for offset in range(0, len(image_ids), 100):
        batch_ids = image_ids[offset:offset + 100]
        try:
            batch = collector.get("/listings/batch", listing_ids=",".join(batch_ids), includes="Images")
            for item in batch.get("results", []):
                images = item.get("images") or item.get("Images") or []
                image = images[0].get("url_570xN") if images and isinstance(images[0], dict) else None
                if image:
                    row = unique_rows.get(str(item.get("listing_id")))
                    if row:
                        row["image_url"] = image
        except RuntimeError as exc:
            errors.append(f"图片信息补充失败：{exc}")
            if collector.quota.get("retry_at") or collector.quota.get("paused"):
                break
    state["next_keyword"] = (start + completed) % len(terms)
    return merge(state, rows, utcnow().isoformat(), int(config["history_samples"])), errors


def export(items: dict, generated: str, status: dict) -> None:
    rows = sorted(items.values(), key=lambda x: (-x.get("trend_score", 0), x.get("search_rank", 9999)))
    public = [{k: v for k, v in row.items() if k != "samples"} for row in rows]
    atomic_json(SITE / "data" / "radar.json", {"generated_at": generated, "items": public})
    atomic_json(SITE / "data" / "status.json", status)
    with (SITE / "data" / "radar.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["trend_score", "title", "price", "currency", "favorites", "favorites_24h", "search_rank", "shop_name", "source_query", "url"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-only", action="store_true", help="只导出已有状态")
    args = parser.parse_args()
    config = load_json(CONFIG, {})
    state = load_json(STATE, {"version": 1, "items": {}, "next_keyword": 0})
    generated = state.get("last_success_at") or utcnow().isoformat()
    errors: list[str] = []
    collector = Collector("", "", int(config["max_requests_per_run"]), float(config["request_interval_seconds"]))
    if not args.render_only:
        key, secret = os.getenv("ETSY_KEYSTRING"), os.getenv("ETSY_SHARED_SECRET")
        if not key or not secret:
            raise SystemExit("缺少 ETSY_KEYSTRING 或 ETSY_SHARED_SECRET 环境变量；只渲染请使用 --render-only")
        collector = Collector(key, secret, int(config["max_requests_per_run"]), float(config["request_interval_seconds"]))
        prior_retry = iso((state.get("api_usage") or {}).get("retry_at"))
        if prior_retry and prior_retry > utcnow():
            errors.append(f"额度暂停中，预计 {prior_retry.isoformat()} 后恢复")
            collector.quota["retry_at"] = prior_retry.isoformat()
        else:
            try:
                state["items"], errors = collect(config, state, collector)
            except Exception as exc:
                errors.append(str(exc))
        state["api_usage"] = collector.quota
        if not errors:
            state["last_success_at"] = utcnow().isoformat()
            generated = state["last_success_at"]
        elif state.get("items") and collector.requests:
            # Keep successful search results when one lane encounters a transient error.
            state["last_success_at"] = utcnow().isoformat()
            generated = state["last_success_at"]
        STATE.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(STATE, state)
    status = {
        "generated_at": generated,
        "last_success_at": state.get("last_success_at"),
        "collection_status": "ok" if not errors else "partial",
        "candidate_count": len(state.get("items", {})),
        "keywords_total": len(config.get("keywords", [])),
        "next_keyword": state.get("next_keyword", 0),
        "requests": collector.requests,
        "api_usage": collector.quota,
        "errors": errors[:3],
    }
    export(state.get("items", {}), generated, status)
    print(f"完成：候选 {status['candidate_count']} 个，API 请求 {collector.requests} 次，状态 {status['collection_status']}")


if __name__ == "__main__":
    main()
