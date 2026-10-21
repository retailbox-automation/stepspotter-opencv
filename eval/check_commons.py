"""Re-check every Wikimedia Commons file in the eval against Commons itself.

    python eval/check_commons.py              # licence + author from the API, sha256 of our copy
    python eval/check_commons.py --download   # also re-download each file (one at a time) and compare bytes

The licence is read from the Commons API (``prop=imageinfo&iiprop=extmetadata``,
``LicenseShortName`` / ``License``), never from the page title. Allowed: CC0, public
domain, CC BY, CC BY-SA. Our copies are the Commons 1280 px thumbnails, unmodified.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "eval" / "cases" / "public" / "sources.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = "StepSpotterEval/0.1 (https://github.com/retailbox-automation; eval licence check) python-urllib"
ALLOWED = re.compile(r"^(cc0|pd|cc-by-[0-9.]+|cc-by-sa-[0-9.]+)$")


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args(argv)
    src = {k: v for k, v in json.loads(SOURCES.read_text())["sources"].items() if v["source_type"] == "commons"}
    by_title = {v["commons"]["title"]: k for k, v in src.items()}
    titles = list(by_title)
    bad = 0
    for i in range(0, len(titles), 40):
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "|".join(titles[i:i + 40]),
                                    "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 1280})
        pages = json.loads(_get(f"{API}?{q}"))["query"]["pages"].values()
        for p in pages:
            sid = by_title[p["title"]]
            em = p["imageinfo"][0]["extmetadata"]
            lic = _strip(em.get("License", {}).get("value", ""))
            author = _strip(em.get("Artist", {}).get("value", ""))
            ours = src[sid]["commons"]
            ok = bool(ALLOWED.match(lic)) and lic == ours["licence_code"]
            local = hashlib.sha256((ROOT / src[sid]["file"]).read_bytes()).hexdigest() == src[sid]["sha256"]
            line = f"{sid} {lic:<14} allowed+unchanged={ok} local_sha256_ok={local} author={author[:40]!r}"
            if args.download:
                data = _get(p["imageinfo"][0]["thumburl"])
                same = hashlib.sha256(data).hexdigest() == src[sid]["sha256"]
                line += f" commons_bytes_equal={same}"
                ok = ok and same
                time.sleep(1.0)
            bad += not (ok and local)
            print(line)
        time.sleep(1.0)
    print(f"{len(titles)} files, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
