"""Bake one model's manual LINK into the cache that ships inside the container image.

    python tools/bake_manual_cache.py "Westinghouse ePX3030" \
        https://cdn.westinghouseoutdoorpower.com/owners_manuals/ePX3030_manual_web.pdf

App Runner's filesystem is ephemeral, and a search engine is a moving part, so the image
carries the answer to "where is this model's manual": the manufacturer's URL and the
pages that matter. It does NOT carry the manual's words — this repository is public and
the text is the manufacturer's. At runtime ``research.hydrate`` fetches the PDF from that
URL and reads the listed pages into a gitignored page cache. This tool downloads the PDF
once only to find those page numbers, then deletes it; nothing but the link and the
page list is written.

Run it from a checkout with the network up.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stepspotter import research  # noqa: E402


def bake(product: str, url: str, out_dir: Path) -> int:
    print(f"downloading {url}")
    scratch = out_dir / "_tmp"
    pdf = research.download(url, dest_dir=str(scratch))
    if pdf is None:
        print("  that URL did not come back as a PDF — nothing written", file=sys.stderr)
        return 1
    pages = research.read_pdf_pages(pdf)
    excerpt = research.extract_assembly(pages)
    if not excerpt.text.strip():
        print("  the PDF has no readable text layer — nothing written", file=sys.stderr)
        return 1

    res = research.Research(
        product=product,
        status="found",
        manual_url=url,
        manual_path=None,  # neither the PDF nor its text travels with the image
        manual_pages=excerpt.pages,
        excerpt="",  # never: the manual's words are the manufacturer's, fetched at runtime
        source="index",
        trail=[f"baked from {url} by tools/bake_manual_cache.py"],
        note=excerpt.note
        or "link and page numbers only; the page text is fetched from manual_url at runtime",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{research.slug(product)}.json"
    dest.write_text(res.model_dump_json(indent=2))
    # The PDF and its scratch dir must not survive: data/manuals is copied into the
    # image wholesale, and an empty _tmp/ riding along is noise at best.
    Path(pdf).unlink(missing_ok=True)
    if scratch.is_dir() and not any(scratch.iterdir()):
        scratch.rmdir()
    print(f"  {len(pages)} pages read; pages {excerpt.pages} listed (no text written)")
    print(f"  wrote {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("product", help='e.g. "Westinghouse ePX3030"')
    ap.add_argument("url", help="a direct link to the manufacturer's PDF")
    ap.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "manuals"),
        help="where to write (default: the repo's data/manuals, which the image copies)",
    )
    args = ap.parse_args(argv)
    return bake(args.product, args.url, Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
