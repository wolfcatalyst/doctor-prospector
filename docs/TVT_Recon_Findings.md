## TVT Registry Recon Findings (February 4, 2026)

**Status:** ✅ FULLY SCRAPABLE - No bot blocking, no auth, no CAPTCHA

---

### Site Architecture

- **Platform:** Drupal CMS with Leaflet.js map
- **Data loading:** ALL hospital data is embedded in the initial HTML page load via `drupalSettings` JavaScript object
- **Filtering:** Client-side JavaScript only (no API calls when filtering by location)
- **URL structure:** Main list at `/tvt-registry`, detail pages at `/site/{siteId}`

### Scraping Strategy: Two-Step Approach

#### Step 1: Hospital List (Single HTTP Request)

**URL:** `https://tvtpublicreporting.sts.org/tvt-registry`

**How it works:**
- GET the page HTML
- Find the `<script>` tag containing `drupalSettings`
- Extract and parse the JSON
- Hospital data lives at: `drupalSettings.leaflet['leaflet-map-view-search-tvt-attachment-1'].features`
- Features are grouped - iterate groups, then iterate `features` within each group
- Each feature with `lat` and `lon` is a hospital

**Data available per hospital from the list page:**
```json
{
  "name": "Morristown Medical Center",
  "siteId": "923009",
  "location": "Morristown, NJ",
  "lat": 40.79723,
  "lon": -74.47752,
  "entityId": "342655"
}
```

**Parsing the popup HTML:**
```python
# Each feature has popup.value containing HTML like:
# <a href="/site/923009" hreflang="en">Morristown Medical Center</a>
# <div class="search--location"> Morristown, NJ </div>

import re
name = re.search(r'<a[^>]*>([^<]+)</a>', popup_html).group(1)
site_id = re.search(r'href="/site/(\d+)"', popup_html).group(1)
location = re.search(r'class="search--location">\s*([^<]+)\s*</div>', popup_html).group(1).strip()
city, state = location.rsplit(', ', 1)
```

**Total hospitals found: 293** (as of February 4, 2026)

**Note:** Some hospital names contain HTML entities (e.g., `&amp;` for `&`). Unescape these.

---

#### Step 2: Detail Pages (One Request Per Hospital)

**URL Pattern:** `https://tvtpublicreporting.sts.org/site/{siteId}`

**Data available per detail page:**

| Field | Example Value | Location in Page |
|-------|---------------|------------------|
| Hospital name | Morristown Medical Center | `<h1>` or article title |
| City, State | Morristown, NJ | Text below title |
| First TAVR date | Apr, 2012 | After "Date of first commercial TAVR procedure performed" |
| Cumulative volume | 4959 | After "Cumulative volume since program inception" |
| Average annual volume | 747 | After "Average annual volume for reporting period" |
| Reporting period | October 1, 2021 through September 30, 2024 | After "Reporting Period" |
| Eligible procedures | 2042 | After "Eligible procedures in reporting period" |
| Composite score | 0.00 (-0.01, 0.01) | After "TAVR 30 Day Composite Score" |
| Star rating | 2 | After "TAVR 30-Day Composite Rating" - look for "X stars" text |
| Rating label | As Expected | Above the stars |

**Rating values observed:**
- 3 stars = "Better Than Expected"
- 2 stars = "As Expected"  
- 1 star = "Worse Than Expected"

**Page text is straightforward to parse with BeautifulSoup.** The detail page is simple server-rendered HTML with no JavaScript data loading.

**Important edge case:** Some hospitals may show "Missing value (shown as 0)" if they don't meet eligibility criteria. Handle gracefully.

---

### Implementation Notes

**No Playwright/Selenium needed.** Plain httpx + BeautifulSoup handles everything.

**Rate limiting approach:**
- 293 detail page requests
- Add 0.5-1.0 second delay between requests
- Total runtime: ~3-5 minutes for full scrape
- No observed rate limiting, but be respectful

**Caching strategy:**
- Cache the list page for 168 hours (1 week)
- Cache detail pages for 168 hours (TVT updates quarterly)
- Store raw HTML in cache so we can re-parse if parsing logic changes

**Extracting drupalSettings from HTML:**
```python
import json
import re
from bs4 import BeautifulSoup

# Step 1: Find the script tag with drupalSettings
soup = BeautifulSoup(html, 'lxml')
for script in soup.find_all('script'):
    if script.string and 'drupalSettings' in script.string:
        # Extract JSON - look for the assignment
        match = re.search(r'JSON\.parse\("(.+?)"\)', script.string)
        if match:
            # Drupal often JSON-encodes then escapes
            raw = match.group(1).encode().decode('unicode_escape')
            settings = json.loads(raw)
        else:
            # Or it might be a direct assignment
            match = re.search(r'drupalSettings\s*=\s*({.+?});', script.string, re.DOTALL)
            if match:
                settings = json.loads(match.group(1))
```

**Alternative approach for extracting drupalSettings:**
The JavaScript on the page sets `drupalSettings` via Drupal's standard pattern. Look for a `<script type="application/json" data-drupal-selector="drupal-settings-json">` tag, which is the modern Drupal approach and contains the full settings as clean JSON.

---

### Sample Data Points for Testing

**Morristown Medical Center (Généreux's hospital):**
- Site ID: 923009
- First TAVR: Apr, 2012
- Cumulative volume: 4,959
- Average annual volume: 747
- Star rating: 2 (As Expected)

**AdventHealth Ocala:**
- Site ID: 772319
- First TAVR: Nov, 2012
- Cumulative volume: 744
- Average annual volume: 93
- Star rating: 2 (As Expected)

**NJ hospitals found (6 total):**
1. Deborah Heart & Lung Center (Browns Mills) - site 391559
2. Robert Wood Johnson University Hospital (New Brunswick) - site 929515
3. Jersey City Medical Center (Jersey City) - site 389561
4. Newark Beth Israel Medical Center (Newark) - site 490196
5. Cooperman Barnabas Medical Center (Livingston) - site 784357
6. Morristown Medical Center (Morristown) - site 923009

---

### Location Dropdown Values

The location filter is a `<select>` with options that are a mix of:
- State names (e.g., "Alabama", "Alaska", "Arizona", "New Jersey")
- City, State pairs (e.g., "Albany, New York", "Amarillo, Texas")

For the scraper, we don't need this - we get ALL hospitals from one page load and can filter in Python.

---

### Open Questions Answered

- ✅ Does TVT allow filtering via URL params? **No, client-side JS only**
- ✅ Is there a hidden JSON API? **No, but drupalSettings has all list data as embedded JSON**
- ✅ Total number of hospitals? **293**
- ✅ Is it bot-blocked? **No - no Cloudflare, no CAPTCHA, standard Drupal**
- ✅ Does it need JS rendering? **No - data is in initial HTML response**
