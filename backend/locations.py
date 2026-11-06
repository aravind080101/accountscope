"""Every place a seller might filter on: worldwide, sales regions, all countries, states, major cities.

Regions are expanded to their countries for Apollo (which only knows countries, states and cities);
news search uses the region name as written, which search engines understand.
"""

COUNTRIES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", "Argentina", "Armenia",
    "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium",
    "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad",
    "Chile", "China", "Colombia", "Comoros", "Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt",
    "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France",
    "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea", "Guinea-Bissau",
    "Guyana", "Haiti", "Honduras", "Hong Kong", "Hungary", "Iceland", "India", "Indonesia", "Iran", "Iraq",
    "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati",
    "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein",
    "Lithuania", "Luxembourg", "Macau", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
    "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia",
    "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand",
    "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau",
    "Palestine", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal",
    "Puerto Rico", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
    "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", "Senegal",
    "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia",
    "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden",
    "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo", "Tonga",
    "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu", "Uganda", "Ukraine",
    "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan", "Vanuatu", "Vatican City",
    "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]

_GCC = ["United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Oman", "Bahrain"]
_DACH = ["Germany", "Austria", "Switzerland"]
_BENELUX = ["Belgium", "Netherlands", "Luxembourg"]
_NORDICS = ["Denmark", "Finland", "Iceland", "Norway", "Sweden"]
_UKI = ["United Kingdom", "Ireland"]
_WEST_EU = _UKI + _DACH + _BENELUX + ["France", "Monaco", "Liechtenstein"]
_SOUTH_EU = ["Italy", "Spain", "Portugal", "Greece", "Malta", "Cyprus", "San Marino", "Andorra", "Vatican City"]
_EAST_EU = ["Poland", "Czech Republic", "Slovakia", "Hungary", "Romania", "Bulgaria", "Croatia", "Slovenia",
            "Serbia", "Bosnia and Herzegovina", "Montenegro", "North Macedonia", "Albania", "Kosovo", "Estonia",
            "Latvia", "Lithuania", "Ukraine", "Moldova", "Belarus", "Russia"]
_EUROPE = _WEST_EU + _SOUTH_EU + _NORDICS + _EAST_EU
_SOUTH_ASIA = ["India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan", "Maldives", "Afghanistan"]
_SEA = ["Singapore", "Malaysia", "Indonesia", "Thailand", "Philippines", "Vietnam", "Cambodia", "Laos", "Myanmar",
        "Brunei", "Timor-Leste"]
_EAST_ASIA = ["China", "Japan", "South Korea", "Taiwan", "Hong Kong", "Macau", "Mongolia"]
_ANZ = ["Australia", "New Zealand"]
_OCEANIA = _ANZ + ["Fiji", "Papua New Guinea", "Samoa", "Tonga", "Vanuatu", "Solomon Islands", "Kiribati",
                   "Marshall Islands", "Micronesia", "Nauru", "Palau", "Tuvalu"]
_MIDDLE_EAST = _GCC + ["Israel", "Jordan", "Lebanon", "Iraq", "Iran", "Syria", "Yemen", "Palestine", "Turkey"]
_NORTH_AFRICA = ["Egypt", "Morocco", "Algeria", "Tunisia", "Libya", "Sudan"]
_AFRICA = [c for c in COUNTRIES if c in {
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi", "Cameroon", "Cape Verde",
    "Central African Republic", "Chad", "Comoros", "Congo", "Democratic Republic of the Congo", "Djibouti", "Egypt",
    "Equatorial Guinea", "Eritrea", "Eswatini", "Ethiopia", "Gabon", "Gambia", "Ghana", "Guinea", "Guinea-Bissau",
    "Ivory Coast", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar", "Malawi", "Mali", "Mauritania",
    "Mauritius", "Morocco", "Mozambique", "Namibia", "Niger", "Nigeria", "Rwanda", "Sao Tome and Principe",
    "Senegal", "Seychelles", "Sierra Leone", "Somalia", "South Africa", "South Sudan", "Sudan", "Tanzania", "Togo",
    "Tunisia", "Uganda", "Zambia", "Zimbabwe"}]
_NORTH_AMERICA = ["United States", "Canada"]
_LATAM = ["Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Ecuador", "Uruguay", "Paraguay",
          "Bolivia", "Venezuela", "Costa Rica", "Panama", "Guatemala", "Honduras", "El Salvador", "Nicaragua",
          "Dominican Republic", "Cuba", "Puerto Rico", "Jamaica", "Trinidad and Tobago", "Guyana", "Suriname",
          "Belize", "Haiti", "Bahamas", "Barbados"]
_CENTRAL_ASIA = ["Kazakhstan", "Uzbekistan", "Kyrgyzstan", "Tajikistan", "Turkmenistan"]
_APAC = _SOUTH_ASIA + _SEA + _EAST_ASIA + _OCEANIA

REGIONS: dict[str, list[str]] = {
    "APAC": _APAC,
    "Asia": _SOUTH_ASIA + _SEA + _EAST_ASIA + _CENTRAL_ASIA,
    "South Asia": _SOUTH_ASIA,
    "Southeast Asia": _SEA,
    "East Asia": _EAST_ASIA,
    "ANZ": _ANZ,
    "Oceania": _OCEANIA,
    "Middle East": _MIDDLE_EAST,
    "GCC": _GCC,
    "MENA": _MIDDLE_EAST + _NORTH_AFRICA,
    "EMEA": _EUROPE + _MIDDLE_EAST + _AFRICA,
    "Europe": _EUROPE,
    "Western Europe": _WEST_EU,
    "Southern Europe": _SOUTH_EU,
    "Eastern Europe": _EAST_EU,
    "Nordics": _NORDICS,
    "DACH": _DACH,
    "Benelux": _BENELUX,
    "UK & Ireland": _UKI,
    "Africa": _AFRICA,
    "North Africa": _NORTH_AFRICA,
    "Sub-Saharan Africa": [c for c in _AFRICA if c not in _NORTH_AFRICA],
    "North America": _NORTH_AMERICA,
    "Americas": _NORTH_AMERICA + _LATAM,
    "LATAM": _LATAM,
    "Central Asia": _CENTRAL_ASIA,
}

STATES_BY_COUNTRY = {
    "India": ["Andhra Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh", "Delhi NCR", "Goa", "Gujarat", "Haryana",
              "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
              "Maharashtra", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh",
              "Uttarakhand", "West Bengal"],
    "United States": ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
                      "Florida", "Georgia (US)", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
                      "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
                      "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
                      "New York State", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
                      "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
                      "Virginia", "Washington State", "West Virginia", "Wisconsin", "Wyoming"],
    "Canada": ["Ontario", "Quebec", "British Columbia", "Alberta"],
    "Australia": ["New South Wales", "Victoria", "Queensland", "Western Australia"],
}

CITIES_BY_COUNTRY = {
    "India": ["Bengaluru", "Mumbai", "Delhi", "Gurugram", "Noida", "Hyderabad", "Chennai", "Pune", "Kolkata", "Ahmedabad",
              "Kochi", "Coimbatore", "Thiruvananthapuram", "Jaipur", "Chandigarh", "Indore", "Mysuru", "Visakhapatnam",
              "Bhubaneswar", "Nagpur", "Vadodara", "Mangaluru", "Madurai", "Lucknow", "GIFT City"],
    "United Arab Emirates": ["Dubai", "Abu Dhabi", "Sharjah"],
    "Saudi Arabia": ["Riyadh", "Jeddah", "Dammam"],
    "Qatar": ["Doha"], "Kuwait": ["Kuwait City"], "Oman": ["Muscat"], "Bahrain": ["Manama"], "Israel": ["Tel Aviv"],
    "Jordan": ["Amman"], "Turkey": ["Istanbul"], "Egypt": ["Cairo"],
    "Singapore": ["Singapore"], "Malaysia": ["Kuala Lumpur"], "Indonesia": ["Jakarta"], "Thailand": ["Bangkok"],
    "Philippines": ["Manila"], "Vietnam": ["Ho Chi Minh City", "Hanoi"], "Hong Kong": ["Hong Kong"],
    "China": ["Shanghai", "Beijing", "Shenzhen"], "Taiwan": ["Taipei"], "Japan": ["Tokyo", "Osaka"],
    "South Korea": ["Seoul"], "Australia": ["Sydney", "Melbourne", "Brisbane", "Perth"], "New Zealand": ["Auckland"],
    "Sri Lanka": ["Colombo"], "Bangladesh": ["Dhaka"], "Pakistan": ["Karachi", "Lahore"], "Nepal": ["Kathmandu"],
    "United Kingdom": ["London", "Manchester", "Edinburgh"], "Ireland": ["Dublin"],
    "Netherlands": ["Amsterdam", "Rotterdam"], "Belgium": ["Brussels"], "France": ["Paris", "Lyon"],
    "Germany": ["Berlin", "Munich", "Frankfurt", "Hamburg"], "Switzerland": ["Zurich", "Geneva"], "Austria": ["Vienna"],
    "Sweden": ["Stockholm"], "Denmark": ["Copenhagen"], "Norway": ["Oslo"], "Finland": ["Helsinki"],
    "Spain": ["Madrid", "Barcelona"], "Portugal": ["Lisbon"], "Italy": ["Milan", "Rome"],
    "Poland": ["Warsaw", "Krakow"], "Czech Republic": ["Prague"], "Hungary": ["Budapest"], "Romania": ["Bucharest"],
    "Bulgaria": ["Sofia"], "Estonia": ["Tallinn"], "Lithuania": ["Vilnius"], "Latvia": ["Riga"], "Ukraine": ["Kyiv"],
    "Luxembourg": ["Luxembourg City"],
    "United States": ["New York", "San Francisco", "San Jose", "Seattle", "Austin", "Dallas", "Houston", "Boston",
                      "Chicago", "Atlanta", "Los Angeles", "San Diego", "Denver", "Miami", "Washington DC", "Raleigh",
                      "Charlotte", "Phoenix", "Philadelphia", "Minneapolis", "Detroit"],
    "Canada": ["Toronto", "Vancouver", "Montreal", "Ottawa", "Calgary"],
    "Mexico": ["Mexico City", "Guadalajara", "Monterrey"], "Brazil": ["Sao Paulo", "Rio de Janeiro"],
    "Argentina": ["Buenos Aires"], "Chile": ["Santiago"], "Colombia": ["Bogota", "Medellin"], "Peru": ["Lima"],
    "South Africa": ["Johannesburg", "Cape Town"], "Kenya": ["Nairobi"], "Nigeria": ["Lagos"],
    "Morocco": ["Casablanca"], "Rwanda": ["Kigali"],
}

STATES = [x for v in STATES_BY_COUNTRY.values() for x in v]
CITIES = list(dict.fromkeys(x for v in CITIES_BY_COUNTRY.values() for x in v))

WORLDWIDE = {"", "any", "global", "worldwide", "all", "anywhere"}


def catalog() -> list[dict]:
    """Grouped options for the location picker."""
    return [
        {"group": "Worldwide", "items": ["Worldwide"]},
        {"group": "Regions", "items": list(REGIONS)},
        {"group": "Countries", "items": COUNTRIES},
        {"group": "States & provinces", "items": STATES},
        {"group": "Cities", "items": CITIES},
    ]


def clean(values) -> list[str]:
    """Accept a string or list (comma separated allowed); drop blanks, worldwide markers and duplicates."""
    if values is None:
        return []
    if isinstance(values, str):
        values = values.split(",") if "," in values else [values]
    out, seen = [], set()
    for v in values:
        v = str(v).strip()
        if v and v.lower() not in WORLDWIDE and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


_REGION_KEYS = {k.lower(): k for k in REGIONS}
_STATE_FIX = {"Georgia (US)": "Georgia, US", "New York State": "New York, US", "Washington State": "Washington, US",
              "Delhi NCR": "Delhi"}


def for_apollo(values) -> list[str]:
    """Expand regions to countries; Apollo matches countries, states and cities by name."""
    out: list[str] = []
    for v in clean(values):
        key = _REGION_KEYS.get(v.lower())
        for item in (REGIONS[key] if key else [_STATE_FIX.get(v, v)]):
            if item not in out:
                out.append(item)
    return out


def for_search(values) -> str:
    """Text to add to a news/web search, e.g. 'India OR GCC OR Singapore'."""
    vals = clean(values)
    return " OR ".join(f'"{v}"' if " " in v else v for v in vals[:6])


# ------------------------------------------------------------------ keeping results inside the chosen places

_COUNTRY_KEYS = {c.lower(): c for c in COUNTRIES}
_ALIASES = {"uae": "United Arab Emirates", "u.a.e.": "United Arab Emirates", "emirates": "United Arab Emirates",
            "usa": "United States", "us": "United States", "u.s.": "United States", "united states of america": "United States",
            "america": "United States", "uk": "United Kingdom", "u.k.": "United Kingdom", "england": "United Kingdom",
            "scotland": "United Kingdom", "wales": "United Kingdom", "great britain": "United Kingdom", "britain": "United Kingdom",
            "ksa": "Saudi Arabia", "korea": "South Korea", "republic of korea": "South Korea", "czechia": "Czech Republic",
            "holland": "Netherlands", "the netherlands": "Netherlands", "turkiye": "Turkey", "türkiye": "Turkey",
            "bharat": "India", "russian federation": "Russia", "viet nam": "Vietnam"}
_PLACE_COUNTRY = {**{x.lower(): c for c, xs in STATES_BY_COUNTRY.items() for x in xs},
                  **{x.lower(): c for c, xs in CITIES_BY_COUNTRY.items() for x in xs}}


def country_name(text: str | None) -> str | None:
    """'UAE', 'Dubai', 'united states' → the country's name in COUNTRIES; None if unknown."""
    t = (text or "").strip().lower().rstrip(".")
    if not t:
        return None
    if t in _COUNTRY_KEYS:
        return _COUNTRY_KEYS[t]
    if t in _ALIASES:
        return _ALIASES[t]
    return _PLACE_COUNTRY.get(t)


def allowed_countries(values) -> set[str] | None:
    """Every country the chosen places cover, or None when one of them isn't a place we know (be lenient)."""
    out: set[str] = set()
    for v in clean(values):
        key = _REGION_KEYS.get(v.lower())
        if key:
            out.update(REGIONS[key])
            continue
        c = country_name(v)
        if not c:
            return None
        out.add(c)
    return out or None


def describe(values) -> str:
    """'India; GCC (United Arab Emirates, Saudi Arabia, …)' for the prompt."""
    parts = []
    for v in clean(values):
        key = _REGION_KEYS.get(v.lower())
        if key:
            parts.append(f"{key} ({', '.join(REGIONS[key])})")
        elif country_name(v) and country_name(v) != v and v.lower() not in _ALIASES:
            parts.append(f"{v}, {country_name(v)}")
        else:
            parts.append(v)
    return "; ".join(parts)


def tavily_country(value: str) -> str | None:
    """Single-country places get Tavily's country boost (lowercase English name)."""
    if _REGION_KEYS.get(value.lower()):
        return None
    c = country_name(value)
    return c.lower() if c else None
