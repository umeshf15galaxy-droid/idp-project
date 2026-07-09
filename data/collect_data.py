"""
collect_data.py — Automated data collection for IDP project.

Step 1: Fetch lat/lon/state for all 15 cities from OpenStreetMap Nominatim
Step 2: Fetch India urban population data from World Bank API
Step 3: Generate a data quality report showing what we have vs what we need

Run: python collect_data.py
"""

import requests
import json
import time
import csv
import os

CITIES = [
    "Delhi", "Mumbai", "Bangalore", "Kolkata", "Chennai",
    "Hyderabad", "Ahmedabad", "Pune", "Surat", "Jaipur",
    "Lucknow", "Kanpur", "Nagpur", "Indore", "Visakhapatnam"
]

# Known state mapping (ground truth)
CITY_STATE = {
    "Delhi": "Delhi",
    "Mumbai": "Maharashtra",
    "Bangalore": "Karnataka",
    "Kolkata": "West Bengal",
    "Chennai": "Tamil Nadu",
    "Hyderabad": "Telangana",
    "Ahmedabad": "Gujarat",
    "Pune": "Maharashtra",
    "Surat": "Gujarat",
    "Jaipur": "Rajasthan",
    "Lucknow": "Uttar Pradesh",
    "Kanpur": "Uttar Pradesh",
    "Nagpur": "Maharashtra",
    "Indore": "Madhya Pradesh",
    "Visakhapatnam": "Andhra Pradesh",
}

# ── Step 1: OpenStreetMap Nominatim ──────────────────────────────

def fetch_coordinates(city):
    """Fetch lat/lon from OpenStreetMap Nominatim API."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{city}, India",
        "format": "json",
        "limit": 1,
        "countrycodes": "in",
    }
    headers = {"User-Agent": "IDP-Project/1.0 (college project)"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        if data:
            return {
                "city": city,
                "latitude": float(data[0]["lat"]),
                "longitude": float(data[0]["lon"]),
                "display_name": data[0].get("display_name", ""),
                "state": CITY_STATE.get(city, ""),
            }
    except Exception as e:
        print(f"  ERROR for {city}: {e}")
    return None

# ── Step 2: World Bank API ────────────────────────────────────────

def fetch_worldbank_urban_india():
    """
    Fetch India's total urban population from World Bank.
    Indicator SP.URB.TOTL = Urban population total
    """
    url = "https://api.worldbank.org/v2/country/IND/indicator/SP.URB.TOTL"
    params = {"format": "json", "per_page": 100, "mrv": 50}
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if len(data) >= 2 and data[1]:
            records = {}
            for item in data[1]:
                if item.get("value") is not None:
                    records[int(item["date"])] = int(item["value"])
            return dict(sorted(records.items()))
    except Exception as e:
        print(f"  World Bank ERROR: {e}")
    return {}

# ── Step 3: Load current CSV ──────────────────────────────────────

def load_current_population():
    """Load our existing population CSV."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "population.csv")
    data = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city = row["city"]
            if city not in data:
                data[city] = {}
            data[city][int(row["year"])] = int(float(row["population"]))
    return data

# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("IDP DATA COLLECTION SCRIPT")
    print("=" * 60)

    # Step 1: Coordinates
    print("\n📍 STEP 1: Fetching coordinates from OpenStreetMap...")
    coordinates = {}
    for city in CITIES:
        print(f"  Fetching {city}...", end=" ")
        result = fetch_coordinates(city)
        if result:
            coordinates[city] = result
            print(f"✅ lat={result['latitude']:.4f}, lon={result['longitude']:.4f}")
        else:
            print("❌ Failed")
        time.sleep(1.1)  # Nominatim rate limit: max 1 request/sec

    # Step 2: World Bank
    print("\n🌍 STEP 2: Fetching India urban population from World Bank API...")
    wb_data = fetch_worldbank_urban_india()
    if wb_data:
        print(f"  ✅ Got {len(wb_data)} years of data")
        # Show recent years
        for year in [2000, 2005, 2010, 2015, 2020]:
            if year in wb_data:
                print(f"     India urban total {year}: {wb_data[year]:,}")
    else:
        print("  ❌ World Bank API unavailable")

    # Step 3: Cross-check our data
    print("\n📊 STEP 3: Cross-checking our population data...")
    our_data = load_current_population()

    # Calculate each city's share of India's total urban population
    shares = {}
    if wb_data and 2020 in wb_data:
        india_2020 = wb_data[2020]
        for city in CITIES:
            if city in our_data and 2020 in our_data[city]:
                share = our_data[city][2020] / india_2020 * 100
                shares[city] = share
                print(f"  {city:20s}: {our_data[city][2020]:>12,} pop | {share:.2f}% of India urban")

    # Step 4: Print data quality report
    print("\n" + "=" * 60)
    print("DATA QUALITY REPORT")
    print("=" * 60)
    print(f"\n✅ Population data:    {len(our_data)} cities × 10 years each")
    print(f"✅ Coordinates:       {len(coordinates)}/{len(CITIES)} cities fetched from OpenStreetMap")
    print(f"✅ World Bank check:  {len(wb_data)} years of India urban total")
    print(f"\n❌ Schools:           NEEDS MANUAL DOWNLOAD — UDISE+ (udiseplus.gov.in)")
    print(f"❌ Hospitals:         NEEDS MANUAL DOWNLOAD — NHRR / data.gov.in")
    print(f"❌ Buses:             NEEDS MANUAL COLLECTION — city transport websites")
    print(f"❌ Road length:       NEEDS MANUAL DOWNLOAD — data.gov.in")

    # Save coordinates to JSON
    out_path = os.path.join(os.path.dirname(__file__), "collected_coordinates.json")
    with open(out_path, "w") as f:
        json.dump(coordinates, f, indent=2)
    print(f"\n💾 Coordinates saved to: {out_path}")

    print("\n" + "=" * 60)
    print("NEXT STEPS (Manual Downloads Required):")
    print("=" * 60)
    print("""
1. SCHOOLS (UDISE+)
   URL: https://udiseplus.gov.in
   → Reports & Publications → School Report Cards
   → Download city/district-wise summary
   → Filter for our 15 cities

2. HOSPITALS (data.gov.in)
   URL: https://data.gov.in
   → Search: "hospitals india city"
   → Download the health facilities dataset

3. BUSES
   Collect from each city's transport website:
   - Delhi: DTC → dtc.delhi.gov.in
   - Mumbai: BEST → bestundertaking.com
   - Bangalore: BMTC → mybmtc.com
   - Chennai: MTC → mtcbus.tn.gov.in
   - Hyderabad: TSRTC → tsrtconline.in
   - Others: search "[city] city bus fleet size"

4. ROADS (data.gov.in)
   URL: https://data.gov.in
   → Search: "road length urban cities india"
""")

if __name__ == "__main__":
    main()
