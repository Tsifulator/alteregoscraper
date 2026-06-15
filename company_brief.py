"""Condensed ALTER EGO brief + service map injected into the LLM so it can reason
about fit and write a tailored pitch. Distilled from the full analytical brief."""

ALTER_EGO_BRIEF = """
ALTER EGO Facilities Management S.A. — one of the largest Integrated Facility
Management (IFM) operators in Greece (Top-5, ~€17.3M turnover 2024, 850+ staff,
~1M m² under management, ~40 years, 8.2yr avg client tenure, 73% delivered in-house).
Member of Allianz Ευρωπαϊκή Πίστη (insurance group → financial stability + trust).

WHAT THEY SELL: outsourced, SLA-driven operation of a client's whole building/estate
under ONE accountable contract. Not "cheap cleaning" — they sell integration, single
accountability, cost optimization, continuity, compliance, and end-user EXPERIENCE
(health/wellbeing/productivity of everyone inside the building).

SERVICE PILLARS:
- Soft services: professional cleaning, pest control, disinfection, green spaces,
  waste management, consumables, hotel housekeeping, mailroom/reception/first-aid.
- Hard services: technical maintenance (preventive+corrective), renovations/fit-outs/
  construction, energy management & efficiency, end-to-end business relocation.
- Security: manned guarding, mobile patrols, CCTV/access/alarms, 24/7 alarm-monitoring.
- Catering: canteen/restaurant management, vending & water, corporate event catering.
- Integrated Facility Management: any/all of the above bundled under one managed contract.

SWEET SPOT: complex, high-hygiene, high-security, high-footfall sites — hospitals &
pharma, corporate HQs, retail chains, factories & logistics, public/cultural venues,
hotels. Existing reference clients include Bristol Myers Squibb, Ernst & Young, Estée
Lauder, Iatriko Athinon, Grecotel — the SNFCC won them a Gold FM award.

HOW TO PITCH: lead with integration + accountability + continuity + experience. Match
the vertical: hygiene/compliance for health & pharma; guest-readiness for hospitality;
uptime + energy cost for production & logistics; footfall + security for public venues;
single-contract simplicity + experience for big corporate HQs.
"""

# Companies ALTER EGO already serves (per the brief) — exclude from leads.
EXISTING_CLIENTS = {
    "bristol myers squibb", "bms", "ernst & young", "ey", "estée lauder",
    "estee lauder", "iatriko athinon", "ιατρικό αθηνών", "grecotel", "snfcc",
    "stavros niarchos foundation cultural center", "ίδρυμα σταύρος νιάρχος",
    "stavros niarchos", "σταύρος νιάρχος", "snf",
}
