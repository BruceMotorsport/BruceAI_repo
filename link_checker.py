#!/usr/bin/env python3
"""
link_checker.py — fetch a URL, extract all links, check their status, report.
"""

import argparse
import concurrent.futures
import csv
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "LinkChecker/1.0 (+https://github.com/bruce/link-checker)"
REQUEST_TIMEOUT = 15
MAX_WORKERS = 20


@dataclass
class LinkResult:
    source_url: str
    target_url: str
    status: Optional[int]
    ok: bool
    error: str = ""
    response_time: float = 0.0
    link_type: str = ""
    is_internal: bool = False


@dataclass
class CheckReport:
    base_url: str
    started: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished: str = ""
    total_links: int = 0
    internal_count: int = 0
    external_count: int = 0
    ok_count: int = 0
    broken_count: int = 0
    error_count: int = 0
    results: list[LinkResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Link Check Report",
            f"=================",
            f"Base URL:      {self.base_url}",
            f"Started:       {self.started}",
            f"Finished:      {self.finished}",
            f"",
            f"Total links:   {self.total_links}",
            f"  Internal:    {self.internal_count}",
            f"  External:    {self.external_count}",
            f"  OK (2xx):    {self.ok_count}",
            f"  Broken (4xx/5xx): {self.broken_count}",
            f"  Errors:      {self.error_count}",
        ]
        return "\n".join(lines)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
    return url


def is_internal(base: str, target: str) -> bool:
    return urlparse(base).netloc == urlparse(target).netloc


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[tuple[str, str]] = []

    for tag in soup.find_all(["a", "link", "script", "img", "iframe", "source", "video", "audio", "embed", "object", "form"]):
        attr = None
        if tag.name in ("a", "link", "area"):
            attr = tag.get("href")
        elif tag.name in ("script", "img", "iframe", "source", "video", "audio", "embed", "object"):
            attr = tag.get("src")
        elif tag.name == "form":
            attr = tag.get("action")

        if not attr:
            continue
        if attr.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
            continue

        absolute = urljoin(base_url, attr)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue

        link_type = tag.name
        links.append((absolute, link_type))

    seen = set()
    unique = []
    for url, ltype in links:
        if url not in seen:
            seen.add(url)
            unique.append((url, ltype))
    return unique


def check_link(source_url: str, target_url: str, link_type: str, internal: bool) -> LinkResult:
    start = time.monotonic()
    try:
        resp = requests.head(
            target_url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        elapsed = time.monotonic() - start
        if resp.status_code >= 400:
            resp = requests.get(
                target_url,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            elapsed = time.monotonic() - start
        return LinkResult(
            source_url=source_url,
            target_url=target_url,
            status=resp.status_code,
            ok=200 <= resp.status_code < 400,
            response_time=round(elapsed, 3),
            link_type=link_type,
            is_internal=internal,
        )
    except requests.exceptions.SSLError as e:
        return LinkResult(source_url, target_url, None, False, f"SSL error: {e}", time.monotonic() - start, link_type, internal)
    except requests.exceptions.ConnectionError as e:
        return LinkResult(source_url, target_url, None, False, f"Connection error: {e}", time.monotonic() - start, link_type, internal)
    except requests.exceptions.Timeout:
        return LinkResult(source_url, target_url, None, False, "Timeout", time.monotonic() - start, link_type, internal)
    except requests.exceptions.TooManyRedirects:
        return LinkResult(source_url, target_url, None, False, "Too many redirects", time.monotonic() - start, link_type, internal)
    except requests.exceptions.RequestException as e:
        return LinkResult(source_url, target_url, None, False, str(e), time.monotonic() - start, link_type, internal)


def run_check(base_url: str, check_external: bool = True, max_links: int = 0) -> CheckReport:
    base_url = normalize_url(base_url)
    report = CheckReport(base_url=base_url)

    print(f"Fetching {base_url} ...")
    try:
        resp = requests.get(base_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: could not fetch {base_url}: {e}", file=sys.stderr)
        sys.exit(1)

    links = extract_links(resp.text, base_url)
    if max_links:
        links = links[:max_links]

    report.total_links = len(links)
    internal_links = [(u, t) for u, t in links if is_internal(base_url, u)]
    external_links = [(u, t) for u, t in links if not is_internal(base_url, u)]
    report.internal_count = len(internal_links)
    report.external_count = len(external_links)

    to_check = list(internal_links)
    if check_external:
        to_check.extend(external_links)

    print(f"Checking {len(to_check)} links ({len(internal_links)} internal, {len(external_links)} external) ...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(check_link, base_url, url, ltype, url in [u for u, _ in internal_links]): (url, ltype)
            for url, ltype in to_check
        }
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            report.results.append(result)
            if result.ok:
                report.ok_count += 1
            elif result.status and result.status >= 400:
                report.broken_count += 1
            else:
                report.error_count += 1
            if i % 25 == 0 or i == len(to_check):
                print(f"  {i}/{len(to_check)} checked ...")

    report.finished = datetime.now(timezone.utc).isoformat()
    return report


def print_report(report: CheckReport, verbose: bool = False):
    print()
    print(report.summary())
    print()

    broken = [r for r in report.results if not r.ok]
    if broken:
        print(f"Broken / error links ({len(broken)}):")
        print("-" * 60)
        for r in broken:
            status_str = str(r.status) if r.status else "ERR"
            print(f"  [{status_str}] {r.target_url}")
            print(f"         type={r.link_type}  internal={r.is_internal}  time={r.response_time}s")
            if r.error:
                print(f"         error: {r.error}")
        print()

    if verbose:
        print("All links:")
        print("-" * 60)
        for r in sorted(report.results, key=lambda x: (x.ok, x.target_url)):
            status_str = str(r.status) if r.status else "ERR"
            print(f"  [{status_str}] {r.target_url}  ({r.link_type}, {r.response_time}s)")
        print()


def save_report(report: CheckReport, output_prefix: str):
    json_path = f"{output_prefix}.json"
    csv_path = f"{output_prefix}.csv"

    data = {
        "base_url": report.base_url,
        "started": report.started,
        "finished": report.finished,
        "total_links": report.total_links,
        "internal_count": report.internal_count,
        "external_count": report.external_count,
        "ok_count": report.ok_count,
        "broken_count": report.broken_count,
        "error_count": report.error_count,
        "results": [
            {
                "source_url": r.source_url,
                "target_url": r.target_url,
                "status": r.status,
                "ok": r.ok,
                "error": r.error,
                "response_time": r.response_time,
                "link_type": r.link_type,
                "is_internal": r.is_internal,
            }
            for r in report.results
        ],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["target_url", "status", "ok", "error", "response_time", "link_type", "is_internal"])
        for r in report.results:
            writer.writerow([r.target_url, r.status, r.ok, r.error, r.response_time, r.link_type, r.is_internal])

    print(f"Saved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Check all links on a web page.")
    parser.add_argument("url", help="URL to check")
    parser.add_argument("--internal-only", action="store_true", help="Only check internal links")
    parser.add_argument("--max-links", type=int, default=0, help="Max links to check (0 = unlimited)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print all links, not just broken")
    parser.add_argument("--output", "-o", help="Output file prefix (without extension)")
    args = parser.parse_args()

    report = run_check(args.url, check_external=not args.internal_only, max_links=args.max_links)
    print_report(report, verbose=args.verbose)

    if args.output:
        save_report(report, args.output)

    if report.broken_count or report.error_count:
        sys.exit(2)


if __name__ == "__main__":
    main()
