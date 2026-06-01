#!/usr/bin/env python3
"""
Email deliverability validation:
1. MX record check - confirms domain has mail server
2. SMTP RCPT TO check - attempts to verify mailbox exists
Records: DELIVERABLE, CATCH-ALL, UNVERIFIABLE (SMTP blocked), INVALID_DOMAIN
"""
import dns.resolver
import smtplib
import socket
import json
import time
import sys
from pathlib import Path


def get_mx_records(domain):
    """Return sorted MX records for domain, or [] if none."""
    try:
        records = dns.resolver.resolve(domain, 'MX', lifetime=10)
        return sorted([(r.preference, str(r.exchange).rstrip('.')) for r in records])
    except Exception:
        return []


def smtp_verify(email, mx_host, timeout=10):
    """
    Attempt SMTP RCPT TO verification.
    Returns: 'DELIVERABLE', 'REJECTED', 'CATCH-ALL', 'BLOCKED', 'ERROR'
    """
    sender = 'verify@example-check.com'
    probe_bad = 'xyzzy_no_such_mailbox_12345@' + email.split('@')[1]
    try:
        with smtplib.SMTP(timeout=timeout) as smtp:
            smtp.connect(mx_host, 25)
            smtp.ehlo('verify.example-check.com')
            smtp.mail(sender)

            # First check our real address
            code, msg = smtp.rcpt(email)
            real_result = code

            # Then check a definitely-bad address to detect catch-all
            code2, msg2 = smtp.rcpt(probe_bad)
            catch_all = (code2 == 250)

            smtp.quit()

            if real_result == 250 and catch_all:
                return 'CATCH-ALL'
            elif real_result == 250:
                return 'DELIVERABLE'
            elif real_result in (550, 551, 553, 554):
                return 'REJECTED'
            else:
                return f'SMTP_{real_result}'
    except smtplib.SMTPConnectError:
        return 'BLOCKED'
    except smtplib.SMTPServerDisconnected:
        return 'BLOCKED'
    except ConnectionRefusedError:
        return 'BLOCKED'
    except socket.timeout:
        return 'TIMEOUT'
    except Exception as e:
        return f'ERROR: {str(e)[:60]}'


def validate_email(email):
    """Full validation: MX check then SMTP check."""
    domain = email.split('@')[1].lower()

    # Step 1: MX check
    mx_records = get_mx_records(domain)
    if not mx_records:
        return {'mx': 'NO_MX', 'smtp': 'SKIPPED', 'deliverability': 'INVALID_DOMAIN'}

    mx_host = mx_records[0][1]  # Use highest-priority MX

    # Step 2: SMTP check
    smtp_result = smtp_verify(email, mx_host)

    if smtp_result == 'DELIVERABLE':
        deliverability = 'DELIVERABLE'
    elif smtp_result == 'CATCH-ALL':
        deliverability = 'CATCH-ALL (domain accepts all mail)'
    elif smtp_result == 'REJECTED':
        deliverability = 'REJECTED (mailbox does not exist)'
    elif smtp_result in ('BLOCKED', 'TIMEOUT'):
        deliverability = f'UNVERIFIABLE ({smtp_result} - SMTP port 25 blocked)'
    else:
        deliverability = f'UNVERIFIABLE ({smtp_result})'

    return {
        'mx': f"MX: {mx_host}",
        'smtp': smtp_result,
        'deliverability': deliverability
    }


def validate_all(leads, output_path):
    """Validate all leads with emails and write results."""
    results = []
    total = len(leads)

    for i, lead in enumerate(leads, 1):
        email = lead.get('email', '')
        if not email or email == 'NOT_FOUND':
            lead['deliverability_status'] = 'NO_EMAIL'
            results.append(lead)
            continue

        print(f"[{i}/{total}] Validating {email}...", end=' ', flush=True)
        v = validate_email(email)
        lead['deliverability_status'] = v['deliverability']
        lead['mx_check'] = v['mx']
        lead['smtp_check'] = v['smtp']
        print(v['deliverability'])
        results.append(lead)
        time.sleep(0.3)  # Be polite

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    # Summary
    statuses = [r.get('deliverability_status', '') for r in results if r.get('email') and r['email'] != 'NOT_FOUND']
    print(f"\n=== Validation Summary ===")
    from collections import Counter
    for status, count in Counter(statuses).most_common():
        print(f"  {status}: {count}")

    return results


if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'data/all_raw_leads.json'
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'data/validated_leads.json'

    with open(input_file) as f:
        leads = json.load(f)

    # Only validate those with emails
    with_emails = [l for l in leads if l.get('email') and l['email'] != 'NOT_FOUND']
    print(f"Validating {len(with_emails)} emails...")
    validate_all(with_emails, output_file)
