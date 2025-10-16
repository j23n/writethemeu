#!/usr/bin/env python
"""
Quick sample of Abgeordnetenwatch constituency API structure.
"""

import requests
import json

BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"


def main():
    # Get just 5 constituencies to see the structure
    print("=== Fetching sample constituencies ===")
    url = f"{BASE_URL}/constituencies"
    response = requests.get(url, params={'page': 0, 'pager_limit': 5}, timeout=30)
    response.raise_for_status()
    data = response.json()

    meta = data.get('meta', {}).get('result', {})
    print(f"Total constituencies available: {meta.get('total')}")

    print("\n=== Sample Constituency Structure ===")
    for i, constituency in enumerate(data.get('data', [])[:2]):
        print(f"\n--- Constituency {i+1} ---")
        print(json.dumps(constituency, indent=2, ensure_ascii=False))

    # Try filtering by parliament_period to see if we can narrow it down
    print("\n\n=== Trying to filter by Bundestag current period ===")
    # Bundestag ID is 5, let's try to get current period
    parliament_response = requests.get(f"{BASE_URL}/parliament-periods", params={'parliament': 5}, timeout=30)
    parliament_response.raise_for_status()
    periods = parliament_response.json().get('data', [])

    if periods:
        current_period_id = periods[0]['id']  # Assuming first is current
        print(f"Current Bundestag period ID: {current_period_id}")

        # Try filtering constituencies by this period
        filtered_response = requests.get(
            f"{BASE_URL}/constituencies",
            params={'parliament_period': current_period_id, 'pager_limit': 5},
            timeout=30
        )
        filtered_response.raise_for_status()
        filtered_data = filtered_response.json()
        filtered_meta = filtered_data.get('meta', {}).get('result', {})

        print(f"\nConstituencies for current Bundestag period: {filtered_meta.get('total')}")

        if filtered_data.get('data'):
            print("\n=== Example filtered constituency ===")
            print(json.dumps(filtered_data['data'][0], indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
