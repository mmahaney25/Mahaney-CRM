#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from data.compile_final import is_valid, same_domain

round5 = [
  {"name": "Kim Burrows","title": "Program Director","organization": "Good Grief","segment": "Nonprofit/Center","website": "https://good-grief.org","email": "kim@good-grief.org","email_source_url": "https://good-grief.org/about/","phone": "908-522-1999 x2004","city": "Morristown","state": "NJ"},
  {"name": "Abbey Loughman","title": "Executive Director","organization": "Wings of Hope Cancer Support Center","segment": "Nonprofit/Center","website": "https://wingsofhope.org","email": "abbey@wingsofhope.org","email_source_url": "https://wingsofhope.org/contact","phone": "712-325-8970","city": "Council Bluffs","state": "IA"},
  {"name": "Not Listed","title": "Bereavement Support","organization": "Pathways Home Health & Hospice","segment": "Hospice/Palliative","website": "https://www.pathwayshealth.org","email": "bereavement@pathwayshealth.org","email_source_url": "https://www.pathwayshealth.org/about-us/bereavement-support","phone": "408-773-4329","city": "Sunnyvale","state": "CA"},
  {"name": "Not Listed","title": "Grief Support Team","organization": "Harbor Hospice Michigan","segment": "Hospice/Palliative","website": "https://harborhospicemi.org","email": "info@HarborHospiceMI.org","email_source_url": "http://harborhospicemi.org/resources/grief-support/","phone": "800-497-9559","city": "Muskegon","state": "MI"},
  {"name": "Lauren Pollock","title": "Hospice Bereavement Coordinator","organization": "Asante Hospice","segment": "Hospice/Palliative","website": "https://www.asante.org","email": "Lauren.pollock@asante.org","email_source_url": "https://www.asante.org/services/hospice/resources/","phone": "541-789-4831","city": "Medford","state": "OR"},
  {"name": "Not Listed","title": "Grief & Loss Counseling Team","organization": "Midland Care Connection","segment": "Hospice/Palliative","website": "https://midlandcare.org","email": "mkent@midlandcc.org","email_source_url": "https://midlandcare.org/services/grief-and-loss-counseling/","phone": "785-232-2044","city": "Topeka","state": "KS"},
  {"name": "Not Listed","title": "Grief Support Team","organization": "Hospice of the Panhandle","segment": "Hospice/Palliative","website": "https://hospiceotp.org","email": "griefsupport@hospiceotp.org","email_source_url": "https://hospiceotp.org/family-support/grief-support/","phone": "304-264-0406","city": "Martinsburg","state": "WV"},
  {"name": "Not Listed","title": "Care Team","organization": "Care of the Piedmont","segment": "Hospice/Palliative","website": "https://www.careofthepiedmont.org","email": "info@careofthepiedmont.org","email_source_url": "https://www.careofthepiedmont.org/contact/","phone": "864-227-9393","city": "Greenwood","state": "SC"},
  {"name": "Not Listed","title": "Kids Grief Program","organization": "Hospice of the Piedmont","segment": "Hospice/Palliative","website": "https://hopva.org","email": "kidsgrief@hopva.org","email_source_url": "https://hopva.org/kids-grief-and-healing/","phone": "434-817-6915","city": "Charlottesville","state": "VA"},
  {"name": "Stephanie Shaw","title": "Camp Sunrise Contact","organization": "ChristianWorks for Children — Camp Sunrise","segment": "Nonprofit/Camp","website": "https://christian-works.org","email": "sshaw@christian-works.org","email_source_url": "https://christian-works.org/camp-sunrise/","phone": "972-960-9981 ext 118","city": "Dallas","state": "TX"},
  {"name": "Not Listed","title": "Grief Support Team","organization": "CareFirstNY","segment": "Hospice/Palliative","website": "https://carefirstny.org","email": "info@CareFirstNY.org","email_source_url": "https://carefirstny.org/grief-support","phone": "607-962-3100","city": "Corning","state": "NY"},
  {"name": "Not Listed","title": "Grief & Loss Team","organization": "EveryStep (Hospice of Central Iowa)","segment": "Hospice/Palliative","website": "https://everystep.org","email": "griefandloss@everystep.org","email_source_url": "https://everystep.org/grief-loss/beraverment","phone": "800-806-9934","city": "Des Moines","state": "IA"},
  {"name": "Not Listed","title": "Programs Team","organization": "Stepping Stones of Hope","segment": "Nonprofit/Center","website": "https://steppingstonesofhope.org","email": "info@steppingstonesofhope.org","email_source_url": "https://steppingstonesofhope.org/contact-us/","phone": "NOT_FOUND","city": "Phoenix","state": "AZ"},
  {"name": "Molly Ruggles","title": "Assistant Clinical Director","organization": "FamilyMeans Center for Grief and Loss","segment": "Nonprofit/Center","website": "https://www.griefloss.org","email": "mruggles@familymeans.org","email_source_url": "https://www.griefloss.org/clinical-consultation-group.html","phone": "651-641-0177","city": "Stillwater","state": "MN"},
  {"name": "Kathy Cromwell","title": "Director, Center for Grief and Healing","organization": "Hinds LifeCare","segment": "Hospice/Palliative","website": "https://hindslifecare.org","email": "centerforgriefandhealing@hindshospice.org","email_source_url": "https://hindslifecare.org/center-for-grief-healing/","phone": "559-248-8579","city": "Fresno","state": "CA"},
]

# Load round 4 leads
with open('data/leads_to_validate_r4.json') as f:
    prev = json.load(f)

existing_emails = {l['email'].strip().lower() for l in prev}

new_valid = []
for lead in round5:
    email = (lead.get('email') or '').strip()
    src = (lead.get('email_source_url') or '').strip()
    website = (lead.get('website') or '').strip()
    if not email or email.upper() == 'NOT_FOUND':
        continue
    if not src or src.upper() == 'NOT_FOUND':
        continue
    # For midlandcare.org / midlandcc.org — same org different domain, accept
    # For hindshospice.org / hindslifecare.org — same org, accept
    # For harborhospicemi.org — http source, same domain
    src_domain = src.replace('https://', '').replace('http://', '').split('/')[0].lstrip('www.')
    web_domain = website.replace('https://', '').replace('http://', '').split('/')[0].lstrip('www.')
    same = same_domain(src, website)
    # Special: same org different email/web domains
    known_pairs = [
        ('midlandcc.org', 'midlandcare.org'),
        ('hindshospice.org', 'hindslifecare.org'),
    ]
    if not same:
        for e_dom, w_dom in known_pairs:
            if (e_dom in email and w_dom in src) or (e_dom in src_domain and w_dom in web_domain):
                same = True
                break
    if not same:
        print(f"SKIP (domain mismatch): {email} | src_domain: {src_domain} | web: {web_domain}")
        continue
    if email.lower() in existing_emails:
        print(f"SKIP (duplicate): {email}")
        continue
    new_valid.append(lead)
    existing_emails.add(email.lower())

print(f"\nNew valid entries from round 5: {len(new_valid)}")
combined = prev + new_valid
print(f"Total: {len(combined)}")
print(f"Gap to 250: {250 - len(combined)}")

with open('data/leads_to_validate_final.json', 'w') as f:
    json.dump(combined, f, indent=2)
print(f"Saved to leads_to_validate_final.json")
