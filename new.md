# Goa FPS Data Pipeline

Scrapes monthly Fair Price Shop (ration shop) transaction data for Goa off the government's IMPDS portal, and turns the mess of nested JSON it produces into one clean CSV you can actually open in Excel and work with.

If you've ever tried to scrape a government portal, you already know why this needed to exist. If you haven't — count yourself lucky, and read on anyway, because most of what's below is the story of things going wrong and how the script learned to deal with it.

## Why this isn't just a basic Selenium script

The first version of this was, in fact, a basic Selenium script. It worked fine for about forty shops and then started quietly writing the wrong data into the wrong files. Here's what forced the redesign:

**The page lies about being updated.** You click a Fair Price Shop link, the JS fires, and the DOM *looks* like it refreshed — but on a slow connection the AJAX call hasn't actually landed yet. If you scrape at that exact moment, you get shop #47's numbers saved under shop #48's filename, and there is no error, no warning, nothing. It just silently corrupts your dataset. The fix here is that after every click, the script pulls the FPS ID that's actually rendered on the page and compares it against the ID it meant to click. Any mismatch raises a `Stale DOM` exception on the spot, before a single byte gets written to disk.

**Headless Chrome degrades over long runs.** A few hundred shop clicks in a row and the browser starts leaking memory and getting sluggish, and the portal itself doesn't love long-lived sessions either. So there's a rolling 15-minute timer — every 900 seconds, the driver quits, a fresh one boots up, and it re-navigates back to wherever it was in the district. The scrape doesn't notice this happened; it just keeps going.

**Networks drop, and government servers time out for no reason.** There's a two-tier retry system for this. First tier: retry the same shop up to three times with `WebDriverWait` handling the slow loads. If that still fails, tier two kicks in — full teardown of the Chrome instance, a new session, re-navigate to the district, and pick back up where it left off.

**Nobody wants to re-scrape four thousand shops because the script crashed at shop 3,999.** Every file's path is worked out *before* anything gets clicked (`data/raw/2026-03/north_goa/158500100001_shopname.json`), and if that file already exists, the shop is skipped entirely. So the script is safe to just re-run after any crash, power cut, or "oops closed my laptop" moment — it picks up exactly where it stopped, no duplicate requests, no wasted time.

## Why two scripts instead of one

Early on I tried scraping straight into a CSV. Terrible idea. One crash mid-write and you've got a half-written row corrupting the whole file — and the actual data (summary cards, PHH vs AAY transaction tables, commodity-wise distributed quantities) is deeply nested, which does not want to live in flat rows anyway.

So the pipeline is split in two, deliberately:

1. **`get_raw_data.py`** — does the scraping. Headless Chrome + Selenium drives the navigation, BeautifulSoup parses the rendered page, and each shop's full record gets dumped as its own `.json` file. Nothing gets flattened here. It's raw.
2. **`consolidate_data.py`** — the ETL step. Reads every JSON file back in, flattens the nested tables into named columns (`txn_phh_regular`, `dty_rice_total`, and so on), and stitches everything into one `consolidated_fps_data.csv`.

Keeping these separate means a scraping crash never costs you already-scraped data, and you can re-run the ETL step as many times as you want — tweak a column name, fix a bug in the flattening logic — without touching the browser at all.

```
[ IMPDS Portal ]
       │
       ▼
[ get_raw_data.py ]        Headless Chrome + Selenium + BeautifulSoup
       │                   • 15-min session recycling
       │                   • stale DOM checks
       │                   • skips shops already saved
       ▼
[ Raw JSON files ]         data/raw/YYYY-MM/district/FPS_ID_name.json
       │
       ▼
[ consolidate_data.py ]    pandas — flattens and merges everything
       │
       ▼
[ consolidated_fps_data.csv ]
```

## What actually gets pulled for each shop

Every JSON file looks roughly like this before it gets flattened:

```json
{
  "year": "2026",
  "month": "03",
  "state": "GOA",
  "district": "NORTH GOA",
  "fps_id": "158500100001",
  "fps_name": "M/S SANNA SANJAY PADTE",
  "summary_cards": {
    "total_etransaction": "412",
    "aadhaar_authenticated": "398",
    "other_mode_authenticated": "9",
    "non_authenticated": "5"
  },
  "number_of_transactions": [ /* PHH / AAY rows */ ],
  "number_of_transacted_ration_cards": [ /* PHH / AAY rows */ ],
  "distributed_quantity_kg": [ /* rice, wheat, sugar... regular/intra/inter/total */ ]
}
```

`consolidate_data.py` unpacks each of those nested blocks with a sensible column prefix — `txn_` for transactions, `rc_` for ration card counts, `dty_` for distributed quantities — so the final CSV ends up wide but flat, and every column name tells you exactly what it is without opening the raw JSON to check.

## Project layout

```
.
├── data/
│   ├── raw/                       # one JSON per shop, per month, per district
│   │   ├── 2026-03/
│   │   │   ├── north_goa/
│   │   │   └── south_goa/
│   │   └── 2026-04/
│   │       ├── north_goa/
│   │       └── south_goa/
│   └── processed/
│       └── consolidated_fps_data.csv
├── get_raw_data.py
├── consolidate_data.py
└── requirements.txt
```

## Running it

```bash
git clone https://github.com/your-username/goa-fps-scraper.git
cd goa-fps-scraper
pip install -r requirements.txt

python get_raw_data.py        # scrapes shop-by-shop, resumable if it dies
python consolidate_data.py    # flattens everything into one CSV
```

The months and zones being scraped are set right at the top of `get_raw_data.py`:

```python
years = [2026]
months = [3, 4]
goa_zones = ['NORTH GOA', 'SOUTH GOA']
```

Change those to pull different months or add more zones later.

## Before you run this: the honest flaws section

Every scraper has rough edges. Here are ours, laid out properly instead of buried in a comment somewhere.

### It will take a very, very long time — and that's fine

This isn't a five-minute script. It's fetching hundreds and hundreds of individual shop pages, one click at a time, with deliberate waits built in so it doesn't outrun a government server that wasn't built for speed. Depending on how many shops a district has, one month of one zone alone can take a good while. Multiply that across two zones and two months and you're looking at a genuinely long, multi-hour run.

So: start it, walk away, let it work. Don't panic if the terminal is quiet for a stretch — that's just `WebDriverWait` doing its job, not the script hanging. The one thing that actually matters on your end is a **stable internet connection** for the duration. The script tolerates *drops* gracefully (more on that below), but it can't do anything about a connection that's down for good.

### It genuinely doesn't mind if you interrupt it

This is the part I'm most confident about. If your Wi-Fi dies mid-run, if you hit `Ctrl+C` because you need your laptop back, if the power goes out — none of that is a disaster. Just run `python get_raw_data.py` again.

Here's why it's safe to do that: before touching the browser for any given shop, the script already knows exactly what the output filename *would* be, and it checks whether that file already exists. If it does, that shop is skipped, no questions asked. So a re-run doesn't re-scrape anything you already have — it just picks up at the first shop that's still missing and continues from there. No duplicate files, no duplicate network calls, no wasted hours re-downloading data you already paid the time cost for once.

### It's dynamic in one way, and stubbornly hardcoded in another

This trips people up, so it's worth being precise about it.

**What *is* dynamic:** the month and year. Right at the top of `get_raw_data.py` you'll find:

```python
years = [2026]
months = [3, 4]
```

Add a year, add a month, and the script builds the right URL and folder structure for it automatically — `data/raw/2026-05/...` just appears on its own. No other code needs to change for that.

**What is *not* dynamic:** the state and the districts. Right now the script is wired specifically to click on **GOA**, and only knows about two zones:

```python
goa_zones = ['NORTH GOA', 'SOUTH GOA']
```

If you want more districts within Goa, or a different state entirely, you can't just add a name to a list and expect it to work — you have to go find that name first. Open the IMPDS portal yourself, navigate to the state you want, and look at the actual page source for the district link's `title` or `aria-label` attribute. Whatever text sits there — copy it **exactly**, in the **same capitalisation** the site uses. The zone-matching logic looks for that string verbatim, so `"North Goa"` won't match where `"NORTH GOA"` would.

And a step further: switching states isn't just a list edit at all. The very first click in `navigate_to_district()` is hardcoded to look for an element whose title contains `'GOA'`:

```python
"//a[contains(@title, 'GOA')] | //img[contains(@aria-label, 'GOA')]"
```

To point this at a different state, that line itself needs editing, not just the zones list. So think of the script as "dynamic for time, hardcoded for geography" — changing *when* you scrape is a config change, changing *where* is a small code change.

### The consolidator doesn't know what it doesn't know

`consolidate_data.py` has its own version of the same problem, and it's a quieter one because it fails silently rather than with an error.

```python
loop_path = ["2026-03//north_goa", "2026-03//south_goa", "2026-04//north_goa", "2026-04//south_goa"]
```

This list is hand-typed and only covers exactly four month/zone combinations. If you scrape a new month with `get_raw_data.py` — say May — that data lands correctly on disk in `data/raw/2026-05/...`, but `consolidate_data.py` has no idea it exists. It won't error, it won't warn you, it will just build the CSV from the four folders it already knows about and quietly leave May out entirely. The fix is manual: add the new `"YYYY-MM//zone_name"` entry to `loop_path` yourself before re-running the ETL step.

### Smaller things worth knowing about

A few more things I noticed while going through both scripts, none dealbreakers, all worth being aware of:

- **The two scripts don't agree on path style.** `get_raw_data.py` builds paths with forward slashes (`data/raw/...`), which work everywhere. `consolidate_data.py` uses Windows-style backslashes (`data\\raw`, `data\\processed\\...`). On Windows this is invisible — it just works. On macOS or Linux, backslashes in a path string aren't treated as folder separators, so `consolidate_data.py` will fail to find the folder unless you're running it on Windows or adjust those paths yourself.
- **There's no log file.** Every status update — successes, retries, stale DOM catches, reboots — goes to the console via `print()` and nowhere else. For a run that might last hours unattended, that means if something worth knowing happened at hour three, you'll only see it if you happened to be watching the terminal at the time, or you redirect output to a file yourself (e.g. `python get_raw_data.py > run_log.txt`).
- **Shop ID and name extraction leans on regex against the sidebar link text.** It assumes the portal always formats entries as something like `"158500100001 : SHOP NAME - extra text"`. If the government ever changes that formatting even slightly, the ID or name extraction can silently produce garbage rather than erroring out, since regex failures here don't currently raise an exception.
- **No duplicate data ever makes it in twice** — that's a genuine strength worth calling out, not a flaw. Between the stale-DOM check on the scrape side and the file-exists skip on resume, you're structurally protected from the same shop's data landing in your dataset more than once.
- **ChromeDriver version isn't pinned or auto-managed.** The script assumes a Chrome browser and matching driver are already installed and on your PATH. If Chrome auto-updates itself and your driver falls behind, you'll get a version-mismatch error at `create_driver()` with no built-in recovery for that specific case — it's a manual driver update.
- Images are blocked in the headless Chrome session on purpose (`profile.managed_default_content_settings.images: 2`) — a real, deliberate speed win across hundreds of shop pages, since all the data we actually need is text and tables anyway.

## Requirements

- Python 3.9+
- Chrome + a matching ChromeDriver on your PATH
- `selenium`, `beautifulsoup4`, `pandas`
## Pipeline Architecture

```text
[ IMPDS Portal ] 
       │
       ▼
[ get_raw_data.py ] ──► (Headless Chrome + Selenium + BeautifulSoup)
       │                 ├── 15-Min Session Recycling
       │                 ├── Stale DOM Assertions
       │                 └── Skip Existing Files
       ▼
[ Raw JSON Vault ]  ──► (data/raw/YYYY-MM/district/FPS_ID.json)
       │
       ▼
[ consolidate_data.py ] (Pandas Schema Flattening)
       │
       ▼
[ Final CSV Dataset ] ──► (data/processed/consolidated_fps_data.csv)

---

.
├── data/
│   ├── raw/                       # Raw scraper JSON dumps
│   │   ├── 2026-03/
│   │   │   ├── north_goa/
│   │   │   └── south_goa/
│   │   └── 2026-04/
│   │       ├── north_goa/
│   │       └── south_goa/
│   └── processed/                 # Final tabular data outputs
│       └── consolidated_fps_data.csv
├── get_raw_data.py                # Main web scraper & browser controller
├── consolidate_data.py            # JSON-to-CSV ETL parser
└── requirements.txt               # Dependencies

git clone [https://github.com/your-username/goa-fps-scraper.git](https://github.com/your-username/goa-fps-scraper.git)
cd goa-fps-scraper

pip install -r requirements.txt

python get_raw_data.py

python consolidate_data.py