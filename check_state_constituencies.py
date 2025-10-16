#!/usr/bin/env python
"""
Check if Abgeordnetenwatch API has constituencies for all state parliaments.
"""

import requests

BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"


def main():
    # Get all parliaments
    print("=== Fetching all parliaments ===")
    response = requests.get(f"{BASE_URL}/parliaments", params={'pager_limit': 100}, timeout=30)
    response.raise_for_status()
    parliaments = response.json().get('data', [])

    state_parliaments = [p for p in parliaments if p['label'] not in ('Bundestag', 'EU-Parlament')]

    print(f"\nFound {len(state_parliaments)} state parliaments:\n")

    for parliament in sorted(state_parliaments, key=lambda x: x['label']):
        print(f"\n{'='*60}")
        print(f"Parliament: {parliament['label']} (ID: {parliament['id']})")
        print(f"{'='*60}")

        # Get parliament periods
        periods_response = requests.get(
            f"{BASE_URL}/parliament-periods",
            params={'parliament': parliament['id']},
            timeout=30
        )
        periods_response.raise_for_status()
        periods = periods_response.json().get('data', [])

        if not periods:
            print("  ⚠️  No periods found")
            continue

        # Check most recent period
        current_period = periods[0]
        print(f"  Current period: {current_period['label']} (ID: {current_period['id']})")

        # Check for constituencies
        const_response = requests.get(
            f"{BASE_URL}/constituencies",
            params={'parliament_period': current_period['id'], 'pager_limit': 1},
            timeout=30
        )
        const_response.raise_for_status()
        const_data = const_response.json()
        const_count = const_data.get('meta', {}).get('result', {}).get('total', 0)

        if const_count > 0:
            print(f"  ✓ Constituencies: {const_count}")
            # Show first example
            if const_data.get('data'):
                example = const_data['data'][0]
                print(f"    Example: {example['label']}")
        else:
            print(f"  ✗ NO CONSTITUENCIES FOUND")

        # Check for electoral lists
        list_response = requests.get(
            f"{BASE_URL}/electoral-lists",
            params={'parliament_period': current_period['id'], 'pager_limit': 1},
            timeout=30
        )
        list_response.raise_for_status()
        list_data = list_response.json()
        list_count = list_data.get('meta', {}).get('result', {}).get('total', 0)

        if list_count > 0:
            print(f"  ✓ Electoral lists: {list_count}")
            # Show first example
            if list_data.get('data'):
                example = list_data['data'][0]
                print(f"    Example: {example['label']}")
        else:
            print(f"  ✗ NO ELECTORAL LISTS FOUND")

    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    # Count which states have data
    has_constituencies = 0
    has_lists = 0

    for parliament in state_parliaments:
        periods_response = requests.get(
            f"{BASE_URL}/parliament-periods",
            params={'parliament': parliament['id']},
            timeout=30
        )
        periods = periods_response.json().get('data', [])

        if periods:
            current_period = periods[0]

            # Check constituencies
            const_response = requests.get(
                f"{BASE_URL}/constituencies",
                params={'parliament_period': current_period['id'], 'pager_limit': 1},
                timeout=30
            )
            const_count = const_response.json().get('meta', {}).get('result', {}).get('total', 0)
            if const_count > 0:
                has_constituencies += 1

            # Check lists
            list_response = requests.get(
                f"{BASE_URL}/electoral-lists",
                params={'parliament_period': current_period['id'], 'pager_limit': 1},
                timeout=30
            )
            list_count = list_response.json().get('meta', {}).get('result', {}).get('total', 0)
            if list_count > 0:
                has_lists += 1

    print(f"States with district constituencies: {has_constituencies}/{len(state_parliaments)}")
    print(f"States with electoral lists: {has_lists}/{len(state_parliaments)}")


if __name__ == '__main__':
    main()
