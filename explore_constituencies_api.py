#!/usr/bin/env python
"""
Explore Abgeordnetenwatch API to see what constituency data is available.
"""

import requests
import json

BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"


def fetch_paginated(endpoint, params=None):
    """Fetch all pages from a paginated endpoint."""
    params = params or {}
    params.setdefault('page', 0)
    params.setdefault('pager_limit', 100)

    results = []
    while True:
        url = f"{BASE_URL}/{endpoint}"
        print(f"Fetching {url} with params {params}")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        data = payload.get('data', [])
        if not data:
            break

        results.extend(data)

        meta = payload.get('meta', {}).get('result', {})
        total = meta.get('total', len(results))
        print(f"  Got {len(data)} items, total so far: {len(results)}/{total}")

        if len(results) >= total:
            break

        params['page'] += 1

    return results


def main():
    # First, get parliaments to find IDs
    print("\n=== Fetching Parliaments ===")
    parliaments = fetch_paginated('parliaments')

    print(f"\nFound {len(parliaments)} parliaments:")
    for p in parliaments:
        print(f"  ID {p['id']}: {p['label']}")

    # Try to fetch constituencies endpoint
    print("\n=== Trying to fetch constituencies ===")
    try:
        constituencies = fetch_paginated('constituencies')
        print(f"\nFound {len(constituencies)} constituencies total")

        # Group by parliament
        by_parliament = {}
        for c in constituencies:
            # Explore the structure
            if len(by_parliament) == 0:
                print("\n=== Example Constituency Structure ===")
                print(json.dumps(c, indent=2, ensure_ascii=False))

            # Try to figure out how they're linked to parliaments
            # Check for parliament_period or parliament fields
            period = c.get('parliament_period')
            if period:
                pid = period.get('id') if isinstance(period, dict) else period
                by_parliament.setdefault(pid, []).append(c)

        print(f"\n=== Constituencies by Parliament Period ===")
        for period_id, consts in sorted(by_parliament.items()):
            print(f"Period {period_id}: {len(consts)} constituencies")

    except requests.HTTPError as e:
        print(f"Error fetching constituencies: {e}")
        print("The 'constituencies' endpoint might not exist or require different params")

    # Let's also check what a parliament period looks like
    print("\n=== Checking Parliament Period Structure ===")
    bundestag = next((p for p in parliaments if p['label'] == 'Bundestag'), None)
    if bundestag:
        periods = fetch_paginated('parliament-periods', {'parliament': bundestag['id']})
        if periods:
            print("\n=== Example Parliament Period ===")
            print(json.dumps(periods[0], indent=2, ensure_ascii=False))

    # Check what fields candidacy-mandates have
    print("\n=== Checking Candidacy-Mandate Structure ===")
    if bundestag and periods:
        current_period = periods[0]
        mandates = fetch_paginated('candidacies-mandates', {
            'parliament_period': current_period['id'],
            'pager_limit': 1  # Just get one example
        })
        if mandates:
            print("\n=== Example Mandate ===")
            print(json.dumps(mandates[0], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
