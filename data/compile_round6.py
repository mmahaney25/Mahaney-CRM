#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from data.compile_final import is_valid, same_domain

round6 = [
  {"name": "Barbara Ross","title": "Director of Bereavement Services","organization": "Arkansas Hospice","segment": "Hospice/Palliative","website": "https://www.arkansashospice.org","email": "bross@arkansashospice.org","email_source_url": "https://www.arkansashospice.org/patients-families-caregivers/grief-support","phone": "501-748-3390","city": "North Little Rock","state": "AR"},
  {"name": "Leslie Aldrich","title": "Bereavement Coordinator","organization": "St. Peter's Health","segment": "Hospice/Palliative","website": "https://www.sphealth.org","email": "laldrich@sphealth.org","email_source_url": "https://www.sphealth.org/hospice-bereavement-resources/bereavement-staff","phone": "(406) 438-1634","city": "Helena","state": "MT"},
  {"name": "Amber Pope","title": "Director","organization": "Community Grief Support","segment": "Nonprofit/Center","website": "https://www.communitygriefsupport.org","email": "info@communitygriefsupport.org","email_source_url": "https://www.communitygriefsupport.org/contact/","phone": "(205) 870-8667","city": "Birmingham","state": "AL"},
]

with open('data/leads_to_validate_final.json') as f:
    prev = json.load(f)

existing_emails = {l['email'].strip().lower() for l in prev}

new_valid = []
for lead in round6:
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

print(f"New valid entries from round 6: {len(new_valid)}")
combined = prev + new_valid
print(f"Total: {len(combined)}")
print(f"Gap to 250: {250 - len(combined)}")

with open('data/leads_to_validate_250.json', 'w') as f:
    json.dump(combined, f, indent=2)
print("Saved to leads_to_validate_250.json")
