#!/usr/bin/env python3
"""
Compile all research rounds, deduplicate, strictly filter to only emails
found verbatim on the org's own website, then validate and produce CSV.
"""
import json
import re
import csv
from pathlib import Path
from urllib.parse import urlparse

def same_domain(source_url, website):
    """True if source_url shares the root domain with the org's website."""
    if not source_url or source_url == 'NOT_FOUND':
        return False
    try:
        src_host = urlparse(source_url).netloc.lower().lstrip('www.')
        web_host = urlparse(website).netloc.lower().lstrip('www.') if website else ''
        # Accept if source domain matches, or is a subdomain
        return src_host == web_host or src_host.endswith('.' + web_host) or web_host.endswith('.' + src_host)
    except Exception:
        return False

# ── Round 3 new entries (final research push) ─────────────────────────────────
round3_raw = [
  {"name": "Suzie Blake","title": "Director of Development","organization": "The Grief Center of New Mexico","segment": "Nonprofit/Center","website": "https://griefnm.org","email": "suzie.blake@griefnm.org","email_source_url": "https://griefnm.org/contact-us/","phone": "505-323-0478","city": "Albuquerque","state": "NM"},
  {"name": "Shari L. Ostroff","title": "Licensed Professional Counselor / Practice Owner","organization": "Grief Tree Counseling","segment": "Private Practice","website": "https://www.grieftreecounseling.com","email": "shari@grieftreecounseling.com","email_source_url": "https://www.grieftreecounseling.com/","phone": "(405) 251-7343","city": "Yukon","state": "OK"},
  {"name": "Audrey McCraw","title": "Executive Director","organization": "The Tristesse Grief Center","segment": "Nonprofit/Center","website": "https://www.thegriefcenter.org","email": "hello@thegriefcenter.org","email_source_url": "https://www.thegriefcenter.org/contact/","phone": "918-587-1200","city": "Tulsa","state": "OK"},
  {"name": "John T. Gold","title": "Executive Director","organization": "The Sharing Place","segment": "Nonprofit/Center","website": "https://www.thesharingplace.org","email": "jgold@thesharingplace.org","email_source_url": "https://www.thesharingplace.org/about/staff","phone": "801-466-6730","city": "Salt Lake City","state": "UT"},
  {"name": "Dianne H. McMahan","title": "LPC / Practice Owner","organization": "Grief Care and Counseling of Greenville, LLC","segment": "Private Practice","website": "https://www.griefcare-counseling.com","email": "dianne@griefcare-counseling.com","email_source_url": "https://www.griefcare-counseling.com","phone": "(864) 569-3404","city": "Greenville","state": "SC"},
  {"name": "Nicole Zegiestowsky","title": "Psychotherapist / Practice Owner","organization": "Stellar Insight Counseling","segment": "Private Practice","website": "https://stellarinsightcounseling.com","email": "Nicole@StellarInsightCounseling.com","email_source_url": "https://stellarinsightcounseling.com/","phone": "907-744-7026","city": "Anchorage","state": "AK"},
  {"name": "Not Listed","title": "Director","organization": "Kids Hurt Too Hawaii","segment": "Nonprofit/Center","website": "https://kidshurttoo.org","email": "info@kidshurttoo.org","email_source_url": "https://kidshurttoo.org/","phone": "(808) 545-5683","city": "Honolulu","state": "HI"},
  {"name": "Ashley Ladi","title": "Bereavement Coordinator, LSW","organization": "Islands Hospice","segment": "Hospice/Palliative","website": "https://www.islandshospice.com","email": "aladi@islandshospice.com","email_source_url": "https://www.islandshospice.com/services/bereavement-services","phone": "(808) 550-2552","city": "Honolulu","state": "HI"},
  {"name": "Adrienne Patridge","title": "LPC / Practice Owner","organization": "Inner Vision Counseling Boise","segment": "Private Practice","website": "https://www.innervisioncounselingboise.com","email": "adrienne@innervisioncounselingboise.com","email_source_url": "https://www.innervisioncounselingboise.com/","phone": "(208) 919-9555","city": "Boise","state": "ID"},
  {"name": "Not Listed","title": "Bereavement Support Team","organization": "Hospice of North Idaho","segment": "Hospice/Palliative","website": "https://hospiceofnorthidaho.org","email": "griefsupport@honi.org","email_source_url": "https://hospiceofnorthidaho.org/grief-and-loss/","phone": "208-772-7994","city": "Coeur d'Alene","state": "ID"},
  {"name": "Not Listed","title": "Director","organization": "Forget Me Not Grief Center of Alaska","segment": "Nonprofit/Center","website": "https://griefcenterak.com","email": "forgetmenot.griefcenter@gmail.com","email_source_url": "https://griefcenterak.com/","phone": "NOT_FOUND","city": "Anchorage","state": "AK"},
  {"name": "Not Listed","title": "Organization Contact","organization": "Hospice of Anchorage","segment": "Hospice/Palliative","website": "https://www.hospiceofanchorage.org","email": "info@hospiceofanchorage.org","email_source_url": "https://www.hospiceofanchorage.org/contact/","phone": "907-561-5322","city": "Anchorage","state": "AK"},
  {"name": "Jane Cornman","title": "Bereavement Coordinator","organization": "Hospice of Hancock County","segment": "Hospice/Palliative","website": "https://www.hospiceofhancock.org","email": "Jcornman@hospiceofhancock.org","email_source_url": "https://www.hospiceofhancock.org/bereavement-support/","phone": "207-667-2531","city": "Ellsworth","state": "ME"},
  {"name": "Esther","title": "Grief Counselor / Practice Owner","organization": "Grief Counseling Services, LLC","segment": "Private Practice","website": "https://griefbatonrouge.com","email": "esther@griefbatonrouge.com","email_source_url": "https://griefbatonrouge.com/contact-us","phone": "(225) 324-5578","city": "Baton Rouge","state": "LA"},
  {"name": "Lauren DeSalvo","title": "LPC / Practice Owner","organization": "Westbrook Counseling Services","segment": "Private Practice","website": "https://westbrookcounseling.org","email": "lauren@westbrookcounseling.org","email_source_url": "https://westbrookcounseling.org/","phone": "(504) 264-2684","city": "New Orleans","state": "LA"},
  {"name": "Not Listed","title": "Program Director","organization": "Center for Grief and Trauma Therapy at Southern University New Orleans","segment": "Nonprofit/Center","website": "https://www.suno.edu/page/social-work-the-center-for-grief-trauma-therapy","email": "TGCenter@suno.edu","email_source_url": "https://www.suno.edu/page/social-work-the-center-for-grief-trauma-therapy","phone": "504-286-5076","city": "New Orleans","state": "LA"},
  {"name": "Not Listed","title": "Practice Contact","organization": "Acadian Counseling Center","segment": "Private Practice","website": "https://acadiancounselingcenter.com","email": "Admin@acadiancounselingcenter.com","email_source_url": "https://acadiancounselingcenter.com/grief-counseling","phone": "337.504.4974","city": "Lafayette","state": "LA"},
  {"name": "Not Listed","title": "Executive Director","organization": "Grief Recovery Center of Baton Rouge","segment": "Nonprofit/Center","website": "https://www.grcbr.org","email": "info@grcbr.org","email_source_url": "https://www.grcbr.org/contact","phone": "225-924-6621","city": "Baton Rouge","state": "LA"},
  {"name": "Dr. Leslie Freedman","title": "PhD / Practice Owner","organization": "Leslie Freedman PhD","segment": "Private Practice","website": "https://lesliefreedmanphd.com","email": "drleslie@lesliefreedmanphd.com","email_source_url": "https://lesliefreedmanphd.com/grief-bereavement-counseling","phone": "212-288-5777","city": "Stamford","state": "CT"},
  {"name": "Katrina Koehler","title": "Executive Director","organization": "Gerard's House","segment": "Nonprofit/Center","website": "https://gerardshouse.org","email": "info@gerardshouse.org","email_source_url": "https://gerardshouse.org/about-us/","phone": "(505) 424-1800","city": "Santa Fe","state": "NM"},
  {"name": "Not Listed","title": "Organization Contact","organization": "Nevada Palliative Care","segment": "Hospice/Palliative","website": "https://nevpc.org","email": "info@nevpc.org","email_source_url": "https://nevpc.org/contact-us","phone": "702-901-7953","city": "Las Vegas","state": "NV"},
  {"name": "Not Listed","title": "Bereavement Contact","organization": "Nevada Caring Hearts Hospice","segment": "Hospice/Palliative","website": "https://nevadacaringheartshospice.com","email": "services@nevadacaringheartshospice.com","email_source_url": "https://nevadacaringheartshospice.com/","phone": "702-268-8393","city": "Las Vegas","state": "NV"},
  {"name": "Not Listed","title": "Director","organization": "Healing Hearts Connection","segment": "Nonprofit/Center","website": "https://healingheartsconnection.com","email": "hope@healingheartsconnection.com","email_source_url": "https://healingheartsconnection.com/","phone": "NOT_FOUND","city": "Big Lake","state": "MN"},
  {"name": "Kathryn VanTighem","title": "Children's Bereavement Program Coordinator","organization": "Benefis Peace Hospice","segment": "Hospice/Palliative","website": "https://www.benefis.org","email": "KathrynVanTighem@Benefis.org","email_source_url": "https://www.benefis.org/benefis-foundation/support-a-cause/womens-childrens-services/childrens-bereavement-program/","phone": "(406) 455-3065","city": "Great Falls","state": "MT"},
  {"name": "Not Listed","title": "Organization Contact","organization": "Good Grief of Kansas","segment": "Nonprofit/Center","website": "https://goodgriefofkansas.org","email": "info@goodgriefofkansas.org","email_source_url": "https://goodgriefofkansas.org/","phone": "316.612.0700","city": "Wichita","state": "KS"},
  {"name": "Gabby Gouveia","title": "Director / Founder","organization": "Let Grace In","segment": "Nonprofit/Center","website": "https://www.letgracein.org","email": "gabby@letgracein.org","email_source_url": "https://www.letgracein.org/resource-list","phone": "NOT_FOUND","city": "Honolulu","state": "HI"},
  {"name": "Amy Larson Lazier","title": "Program Director, LMHC","organization": "FRIENDS WAY","segment": "Nonprofit/Center","website": "https://www.friendsway.org","email": "Amy@friendsway.org","email_source_url": "https://www.friendsway.org/our-staff","phone": "NOT_FOUND","city": "Warwick","state": "RI"},
  {"name": "Christine Phillips","title": "Co-Founder and Executive Director","organization": "Friends of Aine Center for Grieving Children","segment": "Nonprofit/Center","website": "https://friendsofaine.com","email": "christine@friendsofaine.com","email_source_url": "https://friendsofaine.com/","phone": "(603) 669-1120","city": "Manchester","state": "NH"},
  {"name": "Not Listed","title": "Bereavement Team","organization": "Crescent Hospice South Carolina","segment": "Hospice/Palliative","website": "https://hospicesc.com","email": "info@HospiceSC.com","email_source_url": "https://hospicesc.com/bereavement.php","phone": "(855) 784-0254","city": "Greenville","state": "SC"},
  {"name": "Julie Kaplow","title": "Executive Director, PhD","organization": "Trauma & Grief Center at Manning Family Children's Hospital","segment": "Nonprofit/Center","website": "https://www.manningchildrens.org","email": "julie.kaplow@lcmchealth.org","email_source_url": "https://www.manningchildrens.org/services/behavioral-health/trauma-and-grief-center/","phone": "NOT_FOUND","city": "New Orleans","state": "LA"},
  {"name": "Not Listed","title": "Organization Contact","organization": "Maine Hospice Council","segment": "Hospice/Palliative","website": "https://mainehospicecouncil.org","email": "info@mainehospicecouncil.org","email_source_url": "https://mainehospicecouncil.org/about-us/contact-us","phone": "207-626-0651","city": "Augusta","state": "ME"},
  {"name": "Tina Barrett","title": "Co-Founder & Executive Director","organization": "Tamarack Grief Resource Center (general contact)","segment": "Nonprofit/Center","website": "https://www.tamarackgrc.org","email": "info@TamarackGRC.org","email_source_url": "https://www.tamarackgrc.org/contact-us","phone": "(406) 541-8472","city": "Missoula","state": "MT"},
]

# Load compiled data from rounds 1+2
with open('data/all_leads_deduped.json') as f:
    prev_leads = json.load(f)

# Add round 3, filter strictly, then deduplicate
all_candidates = prev_leads + round3_raw

# Strict filter: must have email AND email_source_url on org's own domain
def is_valid(lead):
    email = (lead.get('email') or '').strip()
    src = (lead.get('email_source_url') or '').strip()
    website = (lead.get('website') or '').strip()
    if not email or email.upper() == 'NOT_FOUND':
        return False
    if not src or src.upper() == 'NOT_FOUND':
        return False
    # Source URL must be on the org's own domain (not a third-party)
    if not same_domain(src, website):
        # Special case: gmail.com emails published on their own site are fine
        # but the source must be on their site
        return False
    return True

# Apply strict filter
valid = [l for l in all_candidates if is_valid(l)]

# Deduplicate by normalized email
seen = set()
deduped = []
for lead in valid:
    key = lead['email'].strip().lower()
    if key not in seen:
        seen.add(key)
        deduped.append(lead)

print(f"Total candidates: {len(all_candidates)}")
print(f"Pass strict filter: {len(valid)}")
print(f"After dedup: {len(deduped)}")

from collections import Counter
segs = Counter(l['segment'] for l in deduped)
print("\nBy segment:")
for s, c in segs.most_common():
    print(f"  {s}: {c}")

states = Counter(l['state'] for l in deduped)
print(f"\nUnique states: {len(states)}")

# Save for validation
with open('data/leads_to_validate.json', 'w') as f:
    json.dump(deduped, f, indent=2)
print(f"\nSaved {len(deduped)} leads for validation")
