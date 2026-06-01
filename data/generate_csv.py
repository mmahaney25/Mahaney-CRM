#!/usr/bin/env python3
"""
Generate final deliverable spreadsheet from validated leads.
Columns: name, title, organization, segment, website, email,
         email_source_url, deliverability_status, phone, city, state
"""
import json
import csv
import sys
from pathlib import Path
from collections import Counter


def normalize_segment(seg):
    """Normalize segment names for the final output."""
    seg = seg.strip()
    if 'Private' in seg:
        return 'Private Practice'
    if 'Hospice' in seg or 'Palliative' in seg:
        return 'Hospice/Palliative'
    return 'Nonprofit/Center/Camp'


def clean(val):
    if not val or val in ('NOT_FOUND', 'Not Listed'):
        return ''
    return str(val).strip()


def generate(input_path, output_csv):
    with open(input_path) as f:
        leads = json.load(f)

    # Separate out rejected leads (REJECTED deliverability = mailbox doesn't exist)
    accepted = []
    rejected = []
    for lead in leads:
        status = lead.get('deliverability_status', '')
        if ('REJECTED (mailbox does not exist)' in status
                or 'INVALID_DOMAIN' in status
                or 'Name or service not known' in status):
            rejected.append(lead)
        else:
            accepted.append(lead)

    print(f"Total validated: {len(leads)}")
    print(f"Accepted (not rejected): {len(accepted)}")
    print(f"Rejected (mailbox confirmed non-existent): {len(rejected)}")

    if rejected:
        print("\nRejected emails:")
        for r in rejected:
            print(f"  {r['email']} - {r['organization']}")

    # Sort: Nonprofit first, then Hospice, then Private Practice; then by state
    seg_order = {'Nonprofit/Center/Camp': 0, 'Hospice/Palliative': 1, 'Private Practice': 2}
    accepted.sort(key=lambda x: (seg_order.get(normalize_segment(x.get('segment', '')), 3), x.get('state', ''), x.get('organization', '')))

    fieldnames = [
        'name', 'title', 'organization', 'segment', 'city', 'state',
        'website', 'email', 'email_source_url', 'deliverability_status',
        'phone'
    ]

    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for lead in accepted:
            row = {
                'name': clean(lead.get('name')),
                'title': clean(lead.get('title')),
                'organization': clean(lead.get('organization')),
                'segment': normalize_segment(lead.get('segment', '')),
                'city': clean(lead.get('city')),
                'state': clean(lead.get('state')),
                'website': clean(lead.get('website')),
                'email': clean(lead.get('email')),
                'email_source_url': clean(lead.get('email_source_url')),
                'deliverability_status': clean(lead.get('deliverability_status')),
                'phone': clean(lead.get('phone')),
            }
            writer.writerow(row)

    print(f"\nWrote {len(accepted)} rows to {output_csv}")

    # Summary stats
    segs = Counter(normalize_segment(l.get('segment', '')) for l in accepted)
    states = Counter(l.get('state', '') for l in accepted)
    statuses = Counter(l.get('deliverability_status', '') for l in accepted)

    print(f"\n=== FINAL DELIVERABLE SUMMARY ===")
    print(f"Total leads: {len(accepted)}")
    print(f"\nBy segment:")
    for s, c in segs.most_common():
        print(f"  {s}: {c}")
    print(f"\nStates covered: {len(states)}")
    print(f"\nDeliverability breakdown:")
    for s, c in statuses.most_common():
        print(f"  {s}: {c}")

    print(f"\nTop states by count:")
    for state, count in states.most_common(15):
        print(f"  {state}: {count}")


if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'data/validated_final.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'data/grief_leaders_outreach_list.csv'
    generate(input_file, output_file)
