#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from data.compile_final import is_valid, same_domain

round4 = [
  # From hospice/PP agent - NEW entries only
  {"name": "Sara Yates","title": "Bereavement Coordinator","organization": "HoriSun Hospice","segment": "Hospice/Palliative","website": "https://www.horisunhospice.com","email": "syates@horisunhospice.com","email_source_url": "https://www.horisunhospice.com/bereavement","phone": "402-484-6444","city": "Lincoln","state": "NE"},
  {"name": "Kristen Johnson","title": "Bereavement Coordinator","organization": "Dartmouth Health Palliative Care","segment": "Hospice/Palliative","website": "https://www.dartmouth-hitchcock.org","email": "kristen.r.johnson@hitchcock.org","email_source_url": "https://www.dartmouth-hitchcock.org/patients-visitors/bereavement-support-groups","phone": "603-308-2447","city": "Lebanon","state": "NH"},
  {"name": "Jessica Hall","title": "Executive Director","organization": "Hospice Council of West Virginia","segment": "Hospice/Palliative","website": "https://hospicewv.org","email": "jhall@hospicewv.org","email_source_url": "https://hospicewv.org/contact/","phone": "304-768-8523","city": "Charleston","state": "WV"},
  {"name": "Suzi Sena","title": "Grief Therapist / Practice Owner","organization": "CT Integrative Counseling","segment": "Private Practice","website": "https://ctintegrativecounseling.com","email": "suzi@ctintegrativecounseling.com","email_source_url": "https://ctintegrativecounseling.com/contact/","phone": "NOT_FOUND","city": "Simsbury","state": "CT"},
  {"name": "Not Listed","title": "Practice Owner","organization": "Held Center for Healing","segment": "Private Practice","website": "https://heldcenterforhealing.com","email": "admin@heldcenterforhealing.com","email_source_url": "https://heldcenterforhealing.com/contact-us/","phone": "860-516-5722","city": "West Hartford","state": "CT"},
  {"name": "Suzie","title": "LPC, Fellow in Thanatology / Practice Owner","organization": "Penny Lane Therapy","segment": "Private Practice","website": "https://pennylanetherapy.com","email": "suzie@pennylanetherapy.com","email_source_url": "https://pennylanetherapy.com/","phone": "405-985-9300","city": "Oklahoma City","state": "OK"},
  {"name": "Not Listed","title": "Practice Owner","organization": "CARE Counseling NH","segment": "Private Practice","website": "https://www.carenh.com","email": "Therapy@carenh.com","email_source_url": "https://www.carenh.com/contactus","phone": "NOT_FOUND","city": "Manchester","state": "NH"},
  {"name": "Kelli Lee","title": "Hospice Volunteer Coordinator","organization": "Livingston HealthCare Hospice","segment": "Hospice/Palliative","website": "https://www.livingstonhealthcare.org","email": "Kelli.Lee@LivingstonHealthCare.org","email_source_url": "https://www.livingstonhealthcare.org/services/hospice-care/","phone": "406-823-6251","city": "Livingston","state": "MT"},
  {"name": "Not Listed","title": "Bereavement Team","organization": "Athena Hospice of Rhode Island","segment": "Hospice/Palliative","website": "https://athenahospiceofri.com","email": "Info@AthenaHospiceofRI.com","email_source_url": "https://athenahospiceofri.com/about-us/the-hospice-team/","phone": "NOT_FOUND","city": "Providence","state": "RI"},
  {"name": "Not Listed","title": "Organization Contact","organization": "Endless Journey Hospice","segment": "Hospice/Palliative","website": "https://www.endlessjourneyhospice.com","email": "ourpath@endlessjourneyhospice.com","email_source_url": "https://www.endlessjourneyhospice.com/contact-us/","phone": "NOT_FOUND","city": "Omaha","state": "NE"},
  # From nonprofit agent - NEW entries only
  {"name": "Mary Bristol","title": "Director of Programs","organization": "Center for Grieving Children","segment": "Nonprofit/Center","website": "https://www.cgcmaine.org","email": "mary@cgcmaine.org","email_source_url": "https://www.cgcmaine.org/the-center/","phone": "207-775-5216","city": "Portland","state": "ME"},
  {"name": "Allison K. Stearns","title": "Chief Executive Officer","organization": "CaringMatters","segment": "Nonprofit/Center","website": "https://www.caringmatters.org","email": "allisons@caringmatters.org","email_source_url": "https://www.caringmatters.org/staff","phone": "301-869-4673 ext. 1010","city": "Gaithersburg","state": "MD"},
  {"name": "Gilly Cannon","title": "Senior Director of Children's Bereavement Services","organization": "CaringMatters","segment": "Nonprofit/Center","website": "https://www.caringmatters.org","email": "gillyc@caringmatters.org","email_source_url": "https://www.caringmatters.org/staff","phone": "301-869-4673 ext. 108","city": "Gaithersburg","state": "MD"},
  {"name": "Dr. C. Brandon Brewer","title": "Director of Adult Bereavement Services","organization": "CaringMatters","segment": "Nonprofit/Center","website": "https://www.caringmatters.org","email": "brandonb@caringmatters.org","email_source_url": "https://www.caringmatters.org/staff","phone": "301-869-4673 ext. 107","city": "Gaithersburg","state": "MD"},
  {"name": "Talya Block","title": "Clinical Director","organization": "OUR HOUSE Grief Support Center","segment": "Nonprofit/Center","website": "https://www.ourhouse-grief.org","email": "talya@ourhouse-grief.org","email_source_url": "https://www.ourhouse-grief.org/staff/","phone": "310-473-1511","city": "Los Angeles","state": "CA"},
  {"name": "Mike Seward","title": "President and Camp Erin Director","organization": "Because Kids Grieve","segment": "Nonprofit/Camp","website": "https://becausekidsgrieve.org","email": "presbecausekidsgrieve@gmail.com","email_source_url": "https://becausekidsgrieve.org/contact/","phone": "208-352-2994","city": "Twin Falls","state": "ID"},
  {"name": "Angela Hamblen Kelly","title": "Executive Director","organization": "Baptist Centers for Good Grief","segment": "Nonprofit/Center","website": "https://baptistgriefcenters.org","email": "angela.kelly@bmhcc.org","email_source_url": "https://baptistgriefcenters.org/staff/","phone": "901-861-5656","city": "Memphis","state": "TN"},
  {"name": "Allison Wysota","title": "Founder","organization": "Adam's House","segment": "Nonprofit/Center","website": "https://adamshousect.org","email": "allison@adamshousect.org","email_source_url": "https://adamshousect.org","phone": "(203) 513-2808","city": "Shelton","state": "CT"},
  {"name": "Alan Wolfelt","title": "Founder and Director","organization": "Center for Loss & Life Transition","segment": "Nonprofit/Center","website": "https://www.centerforloss.com","email": "DrWolfelt@CenterforLoss.com","email_source_url": "https://www.centerforloss.com/about-the-center-for-loss/contact/","phone": "(970) 226-6050","city": "Fort Collins","state": "CO"},
  {"name": "Kristen Santel","title": "Clinical Director","organization": "Camp Lionheart","segment": "Nonprofit/Camp","website": "https://www.camplionheart.org","email": "camplionheartcolumbus@gmail.com","email_source_url": "https://www.camplionheart.org/about-camp","phone": "614-506-7959","city": "Columbus","state": "OH"},
  {"name": "Not Listed","title": "Program Director","organization": "FRIENDS WAY","segment": "Nonprofit/Center","website": "https://www.friendsway.org","email": "Ryan@friendsway.org","email_source_url": "https://www.friendsway.org/our-staff","phone": "401-921-0980","city": "Warwick","state": "RI"},
]

# Load existing validated list
with open('data/leads_to_validate.json') as f:
    existing = json.load(f)

existing_emails = {l['email'].strip().lower() for l in existing}

# Filter new entries: strict source domain check + not duplicate
new_valid = []
for lead in round4:
    email = (lead.get('email') or '').strip()
    src = (lead.get('email_source_url') or '').strip()
    website = (lead.get('website') or '').strip()
    if not email or email.upper() == 'NOT_FOUND':
        continue
    if not src or src.upper() == 'NOT_FOUND':
        continue
    if not same_domain(src, website):
        print(f"SKIP (third-party source): {email} | src: {src} | site: {website}")
        continue
    if email.lower() in existing_emails:
        print(f"SKIP (duplicate): {email}")
        continue
    new_valid.append(lead)
    existing_emails.add(email.lower())

print(f"\nNew valid entries: {len(new_valid)}")
print(f"Previous count: {len(existing)}")
print(f"New total: {len(existing) + len(new_valid)}")
print(f"Gap to 250: {250 - (len(existing) + len(new_valid))}")

# Save combined
combined = existing + new_valid
with open('data/leads_to_validate_r4.json', 'w') as f:
    json.dump(combined, f, indent=2)
print(f"\nSaved {len(combined)} leads to leads_to_validate_r4.json")
