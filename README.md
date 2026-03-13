# ZipRecruiterV3 — SeleniumBase UC Driver Job Scraper

Scrapes job listings from [ZipRecruiter](https://www.ziprecruiter.com) using **SeleniumBase Undetected Chrome (UC) Driver** to bypass bot detection.  
Clicks each job card to extract full descriptions. Resilient pagination — retries failed pages and stops only after multiple consecutive empty pages.

---

## Features

- 🤖 **Bot bypass** via SeleniumBase UC Driver (undetected Chrome)
- 🔄 **Resilient pagination** — retries failed pages, stops after 3 consecutive empty pages
- 🎯 **Target-based scraping** — runs until it hits your requested job count
- 🚫 **Title exclusion filter** (manager, senior, director, sales, etc.)
- 🌐 **Remote detection** from location text + job description (`#LI-Remote`, `Remote(...)`)
- 💾 **CSV output** saved in real-time (batch after each page)
- 🌐 **Flask API** wrapper for Fly.io deployment

---

## Local CLI Usage

```bash
pip install -r requirements.txt
python scraper.py
```

You'll be prompted for:
- Job title to search
- Max number of jobs (or unlimited)
- Easy/Quick Apply only?
- Remote only? (default: yes)
- Starting page number
- Headless mode?

---

## API Usage (Fly.io / Docker)

```bash
docker build -t ziprecruiterv3 .
docker run -e SCRAPER_API_KEY=your-key -p 8080:8080 ziprecruiterv3
```

**POST** `/scrape`

```json
{
  "api_key": "your-secret-key",
  "keyword": "cybersecurity analyst",
  "results": 30,
  "remote_only": true,
  "zip_apply_only": false,
  "start_page": 0
}
```

**GET** `/health` — health check  
**GET** `/` — service info

---

## Environment Variables

| Variable | Description |
|---|---|
| `SCRAPER_API_KEY` | **Required** — set via `fly secrets set SCRAPER_API_KEY=...` |
| `PORT` | HTTP port (default: `8080`) |

---

## Fly.io Deployment (ziprecruiterv3)

```bash
fly apps create ziprecruiterv3
fly secrets set SCRAPER_API_KEY=your-secret-key --app ziprecruiterv3
fly deploy --app ziprecruiterv3
```

### Why `performance-2x` + `4096 MB`?

| Component | RAM Usage |
|---|---|
| Chrome browser process (UC mode) | ~500–700 MB |
| Chrome renderer + V8 JS engine | ~300–500 MB |
| Per-card DOM interaction + waits | ~200 MB |
| Python + Flask overhead | ~150 MB |
| OS + headroom | ~250 MB |
| **Total recommended** | **4096 MB** |

**2 dedicated vCPUs** (`performance-2x`) because:
- UC Driver patches Chrome at startup — CPU-intensive burst
- Card clicking + waiting for DOM elements is CPU-bound
- Matches `glassdoorv3` profile (same SeleniumBase UC usage pattern)
