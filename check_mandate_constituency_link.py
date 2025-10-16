#!/usr/bin/env python
"""
Check how mandates link to constituencies in the Abgeordnetenwatch API.
"""

import requests
import json

BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"


def main():
    # Get current Bundestag period
    print("=== Fetching Bundestag period ===")
    periods_response = requests.get(
        f"{BASE_URL}/parliament-periods",
        params={'parliament': 5},
        timeout=30
    )
    periods = periods_response.json().get('data', [])
    current_period_id = periods[0]['id']
    print(f"Current Bundestag period ID: {current_period_id}")

    # Get a few mandates to see the structure
    print("\n=== Fetching sample mandates ===")
    mandates_response = requests.get(
        f"{BASE_URL}/candidacies-mandates",
        params={
            'parliament_period': current_period_id,
            'type': 'mandate',
            'pager_limit': 5
        },
        timeout=30
    )
    mandates = mandates_response.json().get('data', [])

    print(f"\nFound {len(mandates)} sample mandates\n")

    for i, mandate in enumerate(mandates[:3]):
        print(f"{'='*70}")
        print(f"Mandate {i+1}: {mandate.get('politician', {}).get('label')}")
        print(f"{'='*70}")

        electoral_data = mandate.get('electoral_data', {})

        # Check for constituency link
        constituency = electoral_data.get('constituency')
        if constituency:
            print(f"✓ Constituency (direct mandate):")
            print(f"  ID: {constituency.get('id')}")
            print(f"  Label: {constituency.get('label')}")
            print(f"  Type: {constituency.get('entity_type')}")
        else:
            print(f"✗ No constituency (list mandate)")

        # Check for electoral list link
        electoral_list = electoral_data.get('electoral_list')
        if electoral_list:
            print(f"✓ Electoral list:")
            print(f"  ID: {electoral_list.get('id')}")
            print(f"  Label: {electoral_list.get('label')}")
            print(f"  Type: {electoral_list.get('entity_type')}")
        else:
            print(f"✗ No electoral list")

        print(f"\nFull electoral_data structure:")
        print(json.dumps(electoral_data, indent=2, ensure_ascii=False))
        print()

    # Check a state parliament too
    print(f"\n\n{'='*70}")
    print("=== Checking Bayern state parliament ===")
    print(f"{'='*70}")

    bayern_periods = requests.get(
        f"{BASE_URL}/parliament-periods",
        params={'parliament': 13},  # Bayern
        timeout=30
    ).json().get('data', [])

    if bayern_periods:
        bayern_period_id = bayern_periods[0]['id']
        print(f"Bayern period ID: {bayern_period_id}")

        bayern_mandates = requests.get(
            f"{BASE_URL}/candidacies-mandates",
            params={
                'parliament_period': bayern_period_id,
                'type': 'mandate',
                'pager_limit': 3
            },
            timeout=30
        ).json().get('data', [])

        for i, mandate in enumerate(bayern_mandates[:2]):
            print(f"\n--- Bayern Mandate {i+1}: {mandate.get('politician', {}).get('label')} ---")
            electoral_data = mandate.get('electoral_data', {})

            constituency = electoral_data.get('constituency')
            electoral_list = electoral_data.get('electoral_list')

            if constituency:
                print(f"  Constituency: {constituency.get('label')}")
            if electoral_list:
                print(f"  Electoral list: {electoral_list.get('label')}")


if __name__ == '__main__':
    main()
