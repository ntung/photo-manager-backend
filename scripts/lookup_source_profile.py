#!/usr/bin/env python3
"""
Resolve source_profile for photos whose courtesy URL is a bare Facebook
photo permalink (https://www.facebook.com/photo/?fbid=<id>, no set= or
id= param) -- a form extract_facebook_profile() in app/app.py can't
decode, since a bare fbid doesn't encode the owning profile/page id
anywhere in the string.

Two resolution strategies, tried in order per record:
  1. Graph API  (GET /{fbid}?fields=from) -- fast and structured, but
     Facebook's photo endpoints are heavily permission-gated: this will
     generally only resolve photos your access token has visibility
     into (e.g. photos on a Page you administer), not arbitrary public
     photos.
  2. HTML scrape of the public photo page -- fetches
     https://www.facebook.com/photo/?fbid=<id> **logged out** and reads
     the profile slug out of the page's <link rel="canonical"> / og:url
     tag, which for a photo page looks like facebook.com/<profile>/photos/...
     This deliberately does NOT send a Facebook session cookie: tested
     against real data, an authenticated request gets Facebook's full
     "Comet" app shell (a ~1MB JSON blob for client-side rendering, no
     SEO meta tags at all), while a logged-out request reliably gets the
     lightweight SSR snapshot search engines see, which does carry the
     canonical tag. So logged-in scraping isn't just unnecessary here --
     it actively breaks this parsing strategy. Facebook's markup changes
     often regardless, so this stays best-effort -- spot-check the
     report. (An earlier version of this script also matched an
     `actorID` field in embedded JSON, but that key turned out to hold a
     constant placeholder on every page regardless of content, not the
     real owner -- it's intentionally not used.)

A record that consistently fails the scrape step (confirmed non-flaky by
retrying) is most likely a photo Facebook doesn't consider public enough
to hand out SEO metadata for to an anonymous/crawler-like request --
even if it renders fine in your own logged-in browser. There's no known
workaround for that case via plain HTTP; the Graph API step is the only
other option, and only helps for content your own token has permission
to see.

Credentials (optional; the Graph API step is skipped without a token):
  FB_ACCESS_TOKEN   Graph API access token (see Graph API Explorer)
  FB_GRAPH_VERSION  Graph API version, default v19.0

Every attempted record is written to a CSV report (see --report), so
results can be reviewed before trusting them -- regardless of whether
--dry-run was passed.

Usage:
    python scripts/lookup_source_profile.py --dry-run
    python scripts/lookup_source_profile.py --limit 25
    python scripts/lookup_source_profile.py --limit 0   # all matching records
"""
import argparse
import csv
import os
import re
import time
from datetime import datetime
from html import unescape as html_unescape
from urllib.parse import urlparse, parse_qs

import pymongo
import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v19.0"
DEFAULT_DELAY = 2.0
DEFAULT_LIMIT = 25
DEFAULT_REPORT_DIR = os.path.join(os.path.dirname(__file__), "reports")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_CANONICAL_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
_OG_URL_RE = re.compile(r'<meta property="og:url" content="([^"]+)"')
_PROFILE_PATH_TAGS = ('photos', 'videos', 'posts')


def get_db():
    db_host = os.environ.get('DB_HOST')
    db_port = os.environ.get('DB_PORT')
    if not db_host or not db_port:
        raise RuntimeError("DB_HOST and DB_PORT must be set (see .env)")
    db_name = os.environ.get('DB_NAME', 'photodb')
    client = pymongo.MongoClient(db_host, int(db_port), serverSelectionTimeoutMS=5000)
    return client[db_name]


def extract_fbid_if_bare(url):
    """Return the fbid if `url` is a bare .../photo/?fbid=<id> permalink with no
    set= or id= param (the shape extract_facebook_profile() can't resolve).
    Returns None for any other Facebook URL shape or a non-Facebook URL."""
    if not url or 'facebook.com' not in url:
        return None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    if 'id' in params or 'set' in params:
        return None
    return params.get('fbid', [None])[0]


def resolve_via_graph_api(fbid, token, version):
    """Return (profile_id, error) from the Graph API's `from` field."""
    url = f"{GRAPH_API_BASE}/{version}/{fbid}"
    try:
        resp = requests.get(url, params={'fields': 'from', 'access_token': token}, timeout=15)
    except requests.exceptions.RequestException as e:
        return None, f"request error: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    frm = data.get('from') or {}
    if not frm.get('id'):
        return None, f"no 'from' field in response: {data}"
    return frm['id'], None


def _profile_from_set_value(set_val):
    parts = set_val.split('.')
    return parts[1] if len(parts) >= 2 else set_val


def local_unescape_recover(courtesy):
    """A handful of stored courtesy URLs have their querystring ampersands
    HTML-entity-escaped -- sometimes doubly, e.g. '&amp;amp;set=...' -- which
    hides a real set=/id= param from a naive parse. These don't need a network
    call at all, just repeated unescaping. Returns a profile id/slug, or None
    if there's genuinely no set=/id= param to find."""
    text = courtesy
    for _ in range(3):
        params = parse_qs(urlparse(text).query)
        if 'id' in params:
            return params['id'][0]
        if 'set' in params:
            return _profile_from_set_value(params['set'][0])
        unescaped = html_unescape(text)
        if unescaped == text:
            return None
        text = unescaped
    return None


def _profile_from_facebook_url(url):
    """Extract a profile slug/id from a facebook.com URL shaped like
    /<profile>/photos/..., /<profile>/videos/..., /<profile>/posts/...,
    or one carrying a set= or id= param. Returns None if it's some other shape."""
    if not url:
        return None
    parsed = urlparse(html_unescape(url))
    params = parse_qs(parsed.query)
    if 'set' in params:
        return _profile_from_set_value(params['set'][0])
    if 'id' in params:
        return params['id'][0]
    path_parts = [p for p in parsed.path.split('/') if p]
    if len(path_parts) >= 2 and path_parts[1] in _PROFILE_PATH_TAGS:
        return path_parts[0]
    return None


def resolve_via_scrape(fbid):
    """Best-effort HTML scrape of the public photo page, logged out on purpose --
    see the module docstring for why a session cookie is never sent here.
    Returns (profile_id, error)."""
    url = f"https://www.facebook.com/photo/?fbid={fbid}"
    headers = {'User-Agent': USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        return None, f"request error: {e}"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"
    html = resp.text

    # Facebook sometimes redirects the bare fbid URL straight to the canonical
    # /<profile>/photos/... URL; check that before parsing the page body.
    profile = _profile_from_facebook_url(resp.url)
    if profile:
        return profile, None

    for pattern in (_CANONICAL_RE, _OG_URL_RE):
        m = pattern.search(html)
        if m:
            profile = _profile_from_facebook_url(m.group(1))
            if profile:
                return profile, None

    if 'login' in resp.url or 'login_form' in html[:5000].lower():
        return None, "hit a login wall"
    return None, "no profile id found in page"


def resolve_record(fbid, token, graph_version, skip_graph_api):
    """Try the Graph API then the HTML-scrape fallback. Returns (profile, method, error)."""
    graph_error = None
    if not skip_graph_api:
        profile, graph_error = resolve_via_graph_api(fbid, token, graph_version)
        if profile:
            return profile, 'graph_api', None

    profile, scrape_error = resolve_via_scrape(fbid)
    if profile:
        return profile, 'scrape', None
    return None, None, graph_error or scrape_error


def find_candidates(db):
    """Split photos with a facebook.com/photo/? courtesy URL and no source_profile
    into ones recoverable locally (a hidden/escaped set=/id= param) and ones that
    need a network lookup (a genuinely bare fbid, no profile info encoded at all).
    Returns (local_fixes, network_records, total_candidate_count)."""
    query = {
        'source_profile': {'$exists': False},
        'courtesy': {'$regex': r'facebook\.com/photo/\?'},
    }
    docs = list(db.photos.find(query, {'_id': 1, 'courtesy': 1}))
    local_fixes = []
    network_records = []
    for photo in docs:
        courtesy = photo.get('courtesy', '')
        local_profile = local_unescape_recover(courtesy)
        if local_profile:
            local_fixes.append((photo['_id'], courtesy, local_profile))
            continue
        fbid = extract_fbid_if_bare(courtesy)
        if fbid:
            network_records.append((photo['_id'], fbid, courtesy))
    return local_fixes, network_records, len(docs)


def apply_local_fixes(db, local_fixes, dry_run, writer):
    """Write the locally-recovered records straight to the DB (no network call)."""
    for object_id, courtesy, profile in local_fixes:
        print(f"[local] {courtesy} -> {profile} (local_unescape)")
        if not dry_run:
            db.photos.update_one(
                {'_id': object_id},
                {'$set': {'source_profile': profile, 'source_profile_method': 'local_unescape'}}
            )
        writer.writerow([str(object_id), '', courtesy, profile, 'local_unescape', ''])
    return len(local_fixes)


def process_records(db, records, token, graph_version, args, writer, report_fh):
    counts = {'graph_api': 0, 'scrape': 0, 'failed': 0}
    for i, (object_id, fbid, courtesy) in enumerate(records, start=1):
        print(f"[{i}/{len(records)}] fbid={fbid}", end=' ')
        profile, method, error = resolve_record(fbid, token, graph_version, args.skip_graph_api)

        if profile:
            print(f"-> {profile} ({method})")
            counts[method] += 1
            if not args.dry_run:
                db.photos.update_one(
                    {'_id': object_id},
                    {'$set': {'source_profile': profile, 'source_profile_method': method}}
                )
        else:
            print(f"-> FAILED ({error})")
            counts['failed'] += 1

        writer.writerow([str(object_id), fbid, courtesy, profile or '', method or '', error or ''])
        report_fh.flush()

        if i < len(records):
            time.sleep(args.delay)
    return counts


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--limit', type=int, default=DEFAULT_LIMIT,
        help=f"Max records to process, 0 = no limit (default: {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        '--delay', type=float, default=DEFAULT_DELAY,
        help=f"Seconds to sleep between records (default: {DEFAULT_DELAY})"
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Resolve and report but don't write source_profile to the DB"
    )
    parser.add_argument(
        '--skip-graph-api', action='store_true',
        help="Go straight to HTML scraping, skip the Graph API step"
    )
    parser.add_argument(
        '--report', default=None,
        help="CSV report path (default: scripts/reports/source_profile_lookup_<timestamp>.csv)"
    )
    args = parser.parse_args()

    token = os.environ.get('FB_ACCESS_TOKEN')
    graph_version = os.environ.get('FB_GRAPH_VERSION', DEFAULT_GRAPH_VERSION)

    if not token and not args.skip_graph_api:
        print("No FB_ACCESS_TOKEN set - skipping Graph API step, scraping only.\n")
        args.skip_graph_api = True

    db = get_db()
    local_fixes, network_records, total_candidates = find_candidates(db)
    print(f"Found {total_candidates} facebook.com/photo/ courtesy URL(s) missing "
          f"source_profile: {len(local_fixes)} recoverable locally, "
          f"{len(network_records)} need a network lookup")

    if args.limit:
        network_records = network_records[:args.limit]
    limit_note = f" (--limit {args.limit})" if args.limit else ""
    print(f"Processing {len(local_fixes)} local fix(es) + {len(network_records)} "
          f"network lookup(s){limit_note}\n")

    if not local_fixes and not network_records:
        return

    report_path = args.report or os.path.join(
        DEFAULT_REPORT_DIR, f"source_profile_lookup_{datetime.now():%Y%m%d_%H%M%S}.csv"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)

    with open(report_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['object_id', 'fbid', 'courtesy', 'source_profile', 'method', 'error'])
        local_count = apply_local_fixes(db, local_fixes, args.dry_run, writer)
        f.flush()
        counts = process_records(db, network_records, token, graph_version, args, writer, f)

    print("\n" + "=" * 60)
    print(f"Resolved locally (hidden set=/id=): {local_count}")
    print(f"Resolved via Graph API:             {counts['graph_api']}")
    print(f"Resolved via scrape:                {counts['scrape']}")
    print(f"Failed:                             {counts['failed']}")
    print(f"Report written to {report_path}")
    if args.dry_run:
        print("(dry run - no DB writes made)")


if __name__ == '__main__':
    main()
