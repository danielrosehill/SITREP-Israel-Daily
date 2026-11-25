"""Parallel RSS fetching with a timeout (feedparser alone can hang forever)."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import feedparser
import httpx

log = logging.getLogger(__name__)
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")


def _one(url: str):
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as ex:
        log.warning("feed failed: %s: %s", url, str(ex).splitlines()[0])
        return feedparser.parse(b"")


def fetch_all(urls: list[str]) -> dict:
    with ThreadPoolExecutor(12) as pool:
        return dict(zip(urls, pool.map(_one, urls)))
