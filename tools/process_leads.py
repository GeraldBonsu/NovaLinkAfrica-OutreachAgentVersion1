"""
Tool: process_leads.py
Purpose: Score hotel leads and generate personalised outreach messages.
Input:  .tmp/hotels_raw.json
Output: .tmp/hotels_processed.json
"""

import json, os, re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP_DIR  = os.path.join(BASE_DIR, '.tmp')

LUXURY_CHAINS = ['kempinski', 'marriott', 'sheraton', 'hilton', 'movenpick',
                 'radisson', 'hyatt', 'intercontinental', 'novotel', 'ibis',
                 'best western', 'accor', 'ihg', 'four points']
BEACH_RESORT  = ['beach', 'resort', 'oasis', 'lagoon', 'coastal', 'palm', 'harbour']
AIRPORT       = ['airport', 'airside', 'aviation']
BOUTIQUE      = ['boutique', 'villa', 'chateau', 'residence', 'suites', 'serviced']
BUDGET        = ['lodge', 'guesthouse', 'guest house', 'inn', 'hostel', 'motel']

SKIP_EMAILS = ['mymail@mailservice.com', 'noreply', 'no-reply', 'contactus@savvycfo.com']

def hotel_type(name):
    n = name.lower()
    if any(c in n for c in LUXURY_CHAINS):  return 'luxury_chain'
    if any(c in n for c in AIRPORT):        return 'airport'
    if any(c in n for c in BEACH_RESORT):   return 'beach_resort'
    if any(c in n for c in BOUTIQUE):       return 'boutique'
    if any(c in n for c in BUDGET):         return 'budget'
    return 'standard'

def score(hotel):
    pts = 0
    reasons = []

    if hotel.get('email'):
        bad = any(s in hotel['email'].lower() for s in SKIP_EMAILS)
        if bad:
            return 0, 'Placeholder/invalid email — exclude'
        pts += 35; reasons.append('Has email (+35)')
    else:
        return 0, 'No email — cannot reach'

    if hotel.get('phone'):    pts += 10; reasons.append('Has phone (+10)')
    if hotel.get('website'):  pts += 10; reasons.append('Has website (+10)')

    rating = float(hotel.get('rating') or 0)
    if rating >= 4.5:   pts += 25; reasons.append(f'Rating {rating} — excellent (+25)')
    elif rating >= 4.0: pts += 20; reasons.append(f'Rating {rating} — good (+20)')
    elif rating >= 3.5: pts += 15; reasons.append(f'Rating {rating} — average (+15)')
    elif rating > 0:    pts += 8;  reasons.append(f'Rating {rating} — below avg (+8)')

    reviews = int(hotel.get('reviews') or 0)
    if reviews >= 5000:   pts += 20; reasons.append(f'{reviews} reviews — very established (+20)')
    elif reviews >= 1000: pts += 15; reasons.append(f'{reviews} reviews — established (+15)')
    elif reviews >= 500:  pts += 10; reasons.append(f'{reviews} reviews — active (+10)')
    elif reviews >= 100:  pts += 5;  reasons.append(f'{reviews} reviews — growing (+5)')
    else:                 pts += 2;  reasons.append(f'{reviews} reviews — new (+2)')

    htype = hotel_type(hotel.get('hotel_name', ''))
    if htype == 'luxury_chain':  pts += 5;  reasons.append('Luxury chain brand (+5)')
    elif htype == 'beach_resort': pts += 15; reasons.append('Beach/Resort — high connectivity need (+15)')
    elif htype == 'airport':     pts += 12; reasons.append('Airport hotel — business travellers (+12)')
    elif htype == 'boutique':    pts += 10; reasons.append('Boutique — premium segment (+10)')

    city = hotel.get('city', '')
    if city == 'Accra':    pts += 10; reasons.append('Accra — primary market (+10)')
    elif city in ('Kumasi','Takoradi','Tema'): pts += 6; reasons.append(f'{city} — key city (+6)')
    elif city:             pts += 3;  reasons.append(f'{city} (+3)')

    return pts, '; '.join(reasons)


def message(hotel, score_val):
    name     = hotel['hotel_name']
    city     = hotel.get('city') or 'Ghana'
    rating   = hotel.get('rating') or ''
    reviews  = hotel.get('reviews') or ''
    htype    = hotel_type(name)
    website  = hotel.get('website', '')

    # Build reputation line
    rep = ''
    if rating and reviews:
        rep = f"a {rating}-star rating across {int(reviews):,} guest reviews"
    elif rating:
        rep = f"a {rating}-star rating on Google"

    # Context-specific opening lines
    if htype == 'luxury_chain':
        context = (
            f"Properties like {name} set the standard for hospitality in {city} — "
            f"and today's guests hold premium hotels to an equally high bar when it comes to connectivity."
        )
        pain = (
            "Our clients in the luxury segment often find that their existing ISP cannot scale cost-effectively "
            "as guest WiFi demand doubles year-on-year. NovaLink steps in as a managed connectivity partner — "
            "delivering enterprise-grade speeds across all guest areas (rooms, lobby, pool, conference) while "
            "reducing total connectivity spend by an average of 30–40%."
        )
    elif htype == 'airport':
        context = (
            f"{name} serves one of the most demanding guest segments in hospitality — "
            f"business travellers who treat fast, reliable WiFi as a non-negotiable, not an amenity."
        )
        pain = (
            "A single dropped video call or sluggish upload can define a guest's entire stay. "
            "NovaLink provides dedicated, managed internet infrastructure built specifically for "
            "high-traffic airport and transit properties — guaranteed uptime, scalable bandwidth, "
            "and a fully managed experience so your team never has to troubleshoot a router again."
        )
    elif htype == 'beach_resort':
        context = (
            f"{name} offers guests an experience they can't get anywhere else. "
            f"But in 2025, even the most beautiful beachfront property loses stars in reviews when the WiFi doesn't reach the pool."
        )
        pain = (
            "Coastal and resort properties face unique connectivity challenges — distance from city ISP infrastructure, "
            "interference from building materials, and the need for wide outdoor coverage. "
            "NovaLink specialises in exactly this. We've built reliable, wide-area networks for resorts and beach properties "
            "across Africa, so your guests post about the sunset, not the dead zones."
        )
    elif htype == 'boutique':
        context = (
            f"Boutique properties like {name} compete on experience, detail, and the personal touch — "
            f"and WiFi has quietly become the most-reviewed amenity on TripAdvisor and Booking.com."
        )
        pain = (
            "We help boutique hotels punch above their weight on connectivity. Rather than dealing with a generic ISP, "
            "you get a tailored network solution designed around your property layout and guest profile — "
            "delivered and managed by NovaLink, with no technical burden on your team."
        )
    else:
        context = (
            f"{name} has built{(' ' + rep) if rep else ' a strong reputation'} in {city}. "
            f"As guest expectations keep rising, reliable internet has moved from a perk to a baseline requirement."
        )
        pain = (
            "Many hotels across Ghana are still running on legacy internet infrastructure that can't keep up with "
            "today's guest demand. NovaLink replaces that entirely — providing high-speed managed connectivity "
            "at costs well below what most properties currently pay their ISP, with full coverage design, "
            "installation, and ongoing management included."
        )

    rep_line = f"With {rep}, you're clearly delivering strong hospitality. " if rep else ""

    body = f"""Dear {name} Team,

My name is Gerald Bonsu, Founder of NovaLink Africa. We provide affordable, high-speed internet infrastructure for hotels, resorts, and commercial properties across Africa.

{context}

{rep_line}{pain}

I'd love to have a quick 15-minute conversation to understand your current connectivity setup and share how we've helped similar properties in Ghana improve guest satisfaction while cutting internet costs.

Would you be open to a brief call this week or next?

Warm regards,
Gerald Bonsu
Founder, NovaLink Africa
appaubonsu@gmail.com
https://nova-link-africa-website.vercel.app/"""

    return body.strip()


def subject_line(hotel, htype):
    name  = hotel['hotel_name']
    city  = hotel.get('city') or 'Ghana'
    short = name.split('–')[0].split('&')[0].strip()
    if len(short) > 30:
        short = short[:27].strip() + '...'

    templates = {
        'luxury_chain':  f"Managed WiFi Infrastructure for {short}",
        'airport':       f"Enterprise WiFi for Business Guests at {short}",
        'beach_resort':  f"Resort-Wide Connectivity for {short}",
        'boutique':      f"Boutique-Grade WiFi for {short}",
        'standard':      f"High-Speed Internet for {short} — NovaLink Africa",
        'budget':        f"Affordable High-Speed Internet for {short}",
    }
    return templates.get(htype, f"Internet Solution for {short} — NovaLink Africa")


def main():
    raw_path = os.path.join(TMP_DIR, 'hotels_raw.json')
    with open(raw_path, encoding='utf-8') as f:
        hotels = json.load(f)

    processed = []

    for hotel in hotels:
        score_val, reason = score(hotel)
        htype = hotel_type(hotel.get('hotel_name', ''))

        entry = {**hotel,
                 'lead_quality_score': score_val,
                 'reason_for_score': reason,
                 'personalised_message': message(hotel, score_val) if score_val > 0 else '',
                 'email_subject_line':   subject_line(hotel, htype) if score_val > 0 else '',
                 'outreach_status': 'Ready to Review' if score_val > 0 else 'No Email — Skip',
        }
        processed.append(entry)

    processed.sort(key=lambda x: x['lead_quality_score'], reverse=True)

    out_path = os.path.join(TMP_DIR, 'hotels_processed.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(processed, f, indent=2, ensure_ascii=False)

    sendable = [h for h in processed if h['lead_quality_score'] > 0]
    print(f"Total hotels:    {len(processed)}")
    print(f"Reachable leads: {len(sendable)}")
    print(f"\nTop 10 leads:")
    for h in sendable[:10]:
        name = h['hotel_name'].encode('ascii','replace').decode()[:42]
        print(f"  [{h['lead_quality_score']:>3}] {name:<42} | {h['city']:<10} | {h['email']}")

if __name__ == "__main__":
    main()
