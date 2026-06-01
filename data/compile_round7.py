#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from data.compile_final import is_valid, same_domain

round7 = [
  {"name": "Jason Christensen","title": "Grief Services Director","organization": "Mourning Hope Grief Center","segment": "Nonprofit/Center","website": "https://www.mourninghope.org","email": "jchristensen@mourninghope.org","email_source_url": "https://www.mourninghope.org/aboutus/staff.html","phone": "(402) 488-8989","city": "Lincoln","state": "NE"},
  {"name": "Not Listed","title": "Grief Coordinator","organization": "Central Wyoming Hospice & Transitions","segment": "Hospice/Palliative","website": "https://centralwyominghospice.org","email": "centralwyominghospice@centralwyominghospice.org","email_source_url": "https://centralwyominghospice.org/services/","phone": "(307) 577-4832","city": "Casper","state": "WY"},
]

with open('data/leads_to_validate_250.json') as f:
    prev = json.load(f)

existing_emails = {l['email'].strip().lower() for l in prev}

new_valid = []
for lead in round7:
    email = (lead.get('email') or '').strip()
    src = (lead.get('email_source_url') or '').strip()
    website = (lead.get('website') or '').strip()
    if not email or email.upper() == 'NOT_FOUND':
        continue
    if not src or src.upper() == 'NOT_FOUND':
        continue
    if not same_domain(src, website):
        print(f"SKIP (domain mismatch): {email}")
        continue
    if email.lower() in existing_emails:
        print(f"SKIP (duplicate): {email}")
        continue
    new_valid.append(lead)
    existing_emails.add(email.lower())

print(f"New valid entries from round 7: {len(new_valid)}")
combined = prev + new_valid
print(f"Total: {len(combined)}")
print(f"Gap to 250: {250 - len(combined)}")

with open('data/leads_to_validate_r250.json', 'w') as f:
    json.dump(combined, f, indent=2)
print("Saved to leads_to_validate_r250.json")
