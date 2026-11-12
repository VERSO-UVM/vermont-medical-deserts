"""Provider categories from NPPES taxonomy codes, shared by the Vermont map and the regional comparison."""

CATS = [  # (key, label, taxonomy prefixes) - first match wins
    ('mh', 'Mental & behavioral health', ['101Y', '103', '104', '106', '2084P', '2084A', '2084B',
                                          '363LP', '261QM', '3245', '320', '2083A']),
    ('pc', 'Primary care', ['207Q', '207R', '208D', '2080', '363LF', '363LA', '363LG', '363LP',
                            '363L0', '261QP0300', '261QF0400', '261QR1300', '261QC1500']),
    ('dent', 'Dental', ['122', '124', '1223', '126']),
    ('rx', 'Pharmacy', ['1835', '3336']),
    ('rehab', 'Rehab & therapy (PT/OT/speech)', ['2251', '225X', '235Z', '2255', '2257', '2278', '2279', '2256']),
    ('spec', 'Specialist physicians', ['20']),
    ('hosp', 'Hospitals & facilities', ['27', '28', '31', '261Q']),
    ('nurse', 'Nursing, NP/PA, midwifery', ['163W', '164', '363', '367']),
    ('comm', 'Home & community support', ['171M', '172V', '251', '253', '374', '372', '376']),
    ('sn', 'Safety-net clinics (FQHC & RHC sites)', []),     # from HRSA/CMS, not NPPES taxonomy
    ('other', 'Other / students', ['']),
]


def cat_of(code):
    for key, _, prefixes in CATS:
        if any(code.startswith(p) for p in prefixes):
            return key
    return 'other'
