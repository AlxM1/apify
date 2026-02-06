# Apify Platform Research: Free Alternatives for Every Scraper

## Table of Contents

- [What is Apify?](#what-is-apify)
- [Apify Pricing](#apify-pricing)
- [Free Scraping Frameworks](#1-free-scraping-frameworks--libraries)
- [Social Media Scraper Replacements](#2-social-media-scraper-replacements)
- [E-Commerce Scraper Replacements](#3-e-commerce-scraper-replacements)
- [Search & Maps Scraper Replacements](#4-search--maps-scraper-replacements)
- [Travel & Real Estate Replacements](#5-travel--real-estate-scraper-replacements)
- [Job Board Replacements](#6-job-board-scraper-replacements)
- [AI/LLM Content Crawlers](#7-aillm-content-crawler-replacements)
- [Free Proxies & Anti-Bot Tools](#8-free-proxies--anti-bot-tools)
- [Self-Hosted Platform Stacks](#9-recommended-self-hosted-stacks)
- [Quick Reference Table](#10-quick-reference-table)

---

## What is Apify?

Apify is a full-stack cloud platform for web scraping, browser automation, and data extraction at scale. Key facts:

- **10,000+ pre-built scrapers** ("Actors") on its marketplace (the "Apify Store")
- Actors are **serverless Docker containers** that accept JSON input and produce JSON output
- Built on **Crawlee**, Apify's own open-source scraping library (JS/Python)
- Supports Puppeteer, Playwright, Cheerio, BeautifulSoup under the hood
- Built-in proxy rotation, anti-bot evasion, scheduling, and data storage
- Exports to JSON, CSV, Excel, XML, HTML
- 200+ integrations (Zapier, Google Sheets, Slack, Airtable, n8n, webhooks)
- SOC2, GDPR, CCPA compliant

## Apify Pricing

| Plan | Monthly Cost | Credits Included | Actor Memory | Data Retention | Concurrent Runs |
|------|-------------|-----------------|-------------|---------------|-----------------|
| **Free** | $0 | $5/month | 4 GB | 7 days | 3 |
| **Starter** | $39/month | $39/month | More | Longer | More |
| **Scale** | $199/month | $199/month | 128 GB | 21 days | 100 |
| **Business** | $999/month | $999/month | Higher | Longer | More |
| **Enterprise** | Custom | Unlimited | Unlimited | Unlimited | Unlimited |

The free tier gives $5 of compute credits per month (no credit card required). Most actors use pay-per-result pricing on top of platform credits.

---

## 1. Free Scraping Frameworks & Libraries

These are the core building blocks for replacing any Apify actor yourself.

### Tier 1: Production-Ready Frameworks

| Tool | Language | GitHub Stars | License | Best For |
|------|----------|-------------|---------|----------|
| **[Scrapy](https://github.com/scrapy/scrapy)** | Python | ~54,000 | BSD | Large-scale structured crawling, most mature ecosystem |
| **[Playwright](https://github.com/microsoft/playwright)** | JS/Python/C#/Java | ~81,000 | Apache 2.0 | JS-heavy sites, cross-browser automation |
| **[Puppeteer](https://github.com/puppeteer/puppeteer)** | Node.js | ~88,000 | Apache 2.0 | Chrome-based scraping, best stealth plugins |
| **[Crawlee](https://github.com/apify/crawlee)** | JS/Python | ~16,500 / ~6,000 | Apache 2.0 | Apify-quality scraping without the platform |
| **[Crawl4AI](https://github.com/unclecode/crawl4ai)** | Python | ~50,000+ | Apache 2.0 | AI/LLM pipelines, RAG, fully offline |
| **[Firecrawl](https://github.com/firecrawl/firecrawl)** | TypeScript | ~70,000+ | AGPL | Self-hosted API, Markdown output for LLMs |

### Tier 2: Specialized Tools

| Tool | Language | Stars | Best For |
|------|----------|-------|----------|
| **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** | Python | ~20,000+ | AI-driven extraction with natural language prompts, local LLMs via Ollama |
| **[Beautiful Soup](https://pypi.org/project/beautifulsoup4/)** | Python | N/A | Simple HTML parsing, beginners |
| **[Selenium](https://github.com/SeleniumHQ/selenium)** | Multi-lang | ~30,000 | Legacy browser automation, broad language support |
| **[Flyscrape](https://github.com/philippta/flyscrape)** | Go + JS | ~2,000+ | Fast, standalone, lightweight |
| **[MechanicalSoup](https://github.com/MechanicalSoup/MechanicalSoup)** | Python | ~4,700 | Simulates human browsing with Requests + BS4 |

### Key Notes

- **Crawlee** is Apify's own open-source library. It runs standalone without the Apify platform and includes anti-bot evasion, proxy rotation, and request queuing out of the box. This is the closest free equivalent to Apify's infrastructure.
- **Scrapy + scrapy-playwright** is the most battle-tested combination for large-scale scraping in Python.
- **Crawl4AI** is the best choice if your goal is feeding data into AI models (RAG, vector DBs, LLM fine-tuning).

---

## 2. Social Media Scraper Replacements

### Instagram

**Apify offers:** Instagram Scraper, Post Scraper, Profile Scraper, Comment Scraper, Reel Scraper (~$0.25-$2.70 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[drawrowfly/instagram-scraper](https://github.com/drawrowfly/instagram-scraper)** | Open-source | Posts, hashtags, locations, comments. No login/API keys required |
| **Custom Python + Backend API** | DIY | Intercept Instagram's backend JSON API (~200 req/hour/IP) |
| **Playwright/Puppeteer + stealth** | DIY | Full browser automation for any Instagram data |
| **Apify Free Tier** | Freemium | ~750 posts/day within $5 monthly credits |

**Challenges:** Instagram has aggressive anti-bot (IP quality detection, TLS fingerprinting, behavioral analysis). Updates internal API doc_ids every 2-4 weeks. Residential proxies recommended for scale.

---

### TikTok

**Apify offers:** TikTok Scraper, Profile Scraper, Hashtag Scraper, Comments Scraper (~$0.30-$10.00 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)** | Open-source Python | Unofficial API wrapper: trending, user info, video metadata |
| **[drawrowfly/tiktok-scraper](https://github.com/drawrowfly/tiktok-scraper)** | Open-source CLI | Download videos, collect metadata. Most popular OSS TikTok scraper |
| **[Q-Bukold/TikTok-Content-Scraper](https://github.com/Q-Bukold/TikTok-Content-Scraper)** | Open-source Python | 90+ metadata elements, downloads videos/slides |
| **Playwright + stealth** | DIY | Full browser automation for any TikTok data |

**Challenges:** JS-heavy interface makes browser automation the most reliable approach. Hidden API extraction is faster but APIs change frequently.

---

### Twitter / X

**Apify offers:** Tweet Scraper, User Scraper, Trends Scraper (~$0.25-$0.50 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **Nitter (self-hosted)** | Open-source | Privacy-focused Twitter frontend with RSS feeds. Requires guest account pool + proxies |
| **Playwright/Puppeteer scraping** | DIY | Scrape public tweets directly from x.com with browser automation |
| **Apify Free Tier** | Freemium | Scrape tweets/profiles within $5 monthly credits |
| **Serper Web Search** | Freemium | 2,500 free searches/month - use `site:x.com` queries for tweet discovery |

**Context:** Official Twitter API costs $100/month for Basic (15K tweets) or $5,000/month for Pro (1M tweets). Scraping public data visible without login is the practical free approach.

---

### YouTube

**Apify offers:** YouTube Scraper, Channel Scraper (~$0.50-$2.50 per 1,000 items)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** | Open-source CLI (~90K stars) | Gold standard. Metadata extraction with `--dump-json`. Hundreds of platforms supported |
| **[scrapetube](https://github.com/dermasmid/scrapetube)** | Open-source Python | Lightweight, zero-dependency. All videos from channels/playlists/search |
| **YouTube Data API v3** | Official API | Free: 10,000 units/day. Limited data points but legitimate |
| **Playwright + stealth** | DIY | Scrape any YouTube page including comments, transcripts |

**Best approach:** `yt-dlp --dump-json` for metadata (no video download needed) + YouTube Data API for structured queries within quota.

---

### Reddit

**Apify offers:** Reddit Scraper (~$9-$20/month third-party actors)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[PRAW](https://github.com/praw-dev/praw)** | Official API wrapper | 60 req/min rate limit. OAuth-based. Full Reddit access |
| **`.json` endpoint trick** | Built-in | Append `.json` to any Reddit URL for structured data. No auth needed |
| **`.rss` feeds** | Built-in | Append `.rss` to any Reddit URL. Structured XML, least likely to be blocked |
| **[YARS](https://github.com/datavorous/yars)** | Open-source Python | Uses `.json` endpoint, no API keys. Lightweight |
| **old.reddit.com scraping** | DIY | No JavaScript required. Perfect for traditional scraping with requests + BS4 |

**Reddit is the easiest major platform to scrape** due to built-in `.json` and `.rss` endpoints. PRAW is recommended for any serious use.

---

### LinkedIn

**Apify offers:** Profile Scraper, Company Scraper, Job Scraper, Post Scraper (~$0.10-$3.00 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[joeyism/linkedin_scraper](https://github.com/joeyism/linkedin_scraper)** | Open-source Python | Async Playwright-based. Profiles, companies, jobs. Apache 2.0 |
| **[linkedin-api (unofficial)](https://github.com/tomquirk/linkedin-api)** | Open-source Python | Programmatic LinkedIn access without official API |
| **Browser extensions** | No-code | Instant Data Scraper, Web Scraper, ParseHub free plan |
| **Playwright + stealth** | DIY | Full browser automation with login session |

**WARNING:** LinkedIn explicitly prohibits unauthorized scraping. Account suspension and legal action are real risks. GDPR compliance is essential for EU data.

---

### Facebook

**Apify offers:** Pages Scraper, Posts Scraper, Ads Scraper (~$0.75-$10.00 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[kevinzg/facebook-scraper](https://github.com/kevinzg/facebook-scraper)** | Open-source Python | Public pages to CSV. No API key. Some features need login cookies |
| **[facebook-page-info-scraper](https://github.com/AhmedMohamedAbdelworworoud/facebook-page-info-scraper)** | Open-source | Unlimited API calls, no restrictions. Public page data |
| **[harismuneer/Ultimate-Social-Scrapers](https://github.com/harismuneer/Ultimate-Social-Scrapers)** | Open-source | Multi-platform (FB, Instagram, Twitter) |
| **Meta Ad Library API** | Official | Free access to ad transparency data |

**WARNING:** Facebook has some of the most advanced anti-bot systems. Unauthorized scraping is explicitly forbidden in their ToS.

---

## 3. E-Commerce Scraper Replacements

### Amazon

**Apify offers:** Product Scraper, Reviews Scraper, Seller Scraper (~$0.04-$0.06 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **Scrapy + custom spiders** | Open-source | Most reliable DIY approach. Full control over extraction logic |
| **Crawlee** | Open-source | Build Amazon scrapers with Apify's OSS library |
| **[GitHub amazon-scraper projects](https://github.com/topics/amazon-scraper)** | Open-source | Multiple repos for titles, ratings, prices, images, ASINs |
| **Amazon Product Advertising API** | Official | Limited but legitimate access to product data |
| **ScraperAPI** | Freemium | 5,000 free credits. Handles proxies and CAPTCHA |
| **ScrapingBee** | Freemium | 1,000 free credits. No credit card required |

**Challenges:** Amazon frequently changes HTML structure. JS-heavy pages need Playwright/Selenium. Regular maintenance required.

### Shopify Stores

**Free approach:** Shopify stores expose `/products.json` endpoint by default. Simple HTTP requests can extract full product catalogs without any scraping library.

```
https://example-store.myshopify.com/products.json
https://example-store.myshopify.com/products.json?page=2
```

---

## 4. Search & Maps Scraper Replacements

### Google Maps

**Apify offers:** Google Maps Scraper (~$4.00 per 1,000 places + $0.50 per 1,000 reviews)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper)** | Open-source (MIT) | CLI, Web UI, REST API. Name, address, phone, website, rating, reviews, coords, email. Deployable to K8s/AWS Lambda |
| **[omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper)** | Open-source | 1,200 leads in 25 minutes, 30 data points per listing. 200 free searches/month via API |
| **[GoMaps](https://github.com/jakeee51/gomaps)** | Open-source Python | Lite Google Maps Places API. Geocode, reverse geocoding. No API key |
| **Outscraper** | Freemium | Free tier for business details, reviews, location data |

**Note:** Official Google Places API is pay-as-you-go and caps results at 60 per query. OSS scrapers bypass this.

### Google Search (SERP)

**Apify offers:** Google Search Scraper (~$0.25 per 1,000 results)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[Serper](https://serper.dev)** | Freemium | 2,500 free searches/month. Best free SERP API |
| **[DDGS (duckduckgo_search)](https://github.com/deedy5/duckduckgo_search)** | Open-source Python | Free, no rate limits published. Returns DuckDuckGo results (not Google) |
| **ScraperAPI** | Freemium | 5,000 free credits. General-purpose |
| **SearchAPI** | Freemium | 100 free credits on signup |
| **Playwright + stealth** | DIY | Google now requires JS rendering (since Jan 2025). Traditional HTTP scrapers are blocked |

**Important:** As of January 2025, Google requires JavaScript to render search results. Traditional non-JS scrapers no longer work. Browser automation or API services are required.

---

## 5. Travel & Real Estate Scraper Replacements

### Airbnb / Booking.com

**Apify offers:** Airbnb Scraper, Booking Scraper (~$0.50+ per 1,000 listings)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **Scrapy + Playwright** | DIY | Build custom spiders for any travel site |
| **Crawlee** | Open-source | Browser-based scraping with anti-bot evasion built in |
| **[GitHub airbnb-scraper projects](https://github.com/topics/airbnb-scraper)** | Open-source | Multiple community scrapers |

### Zillow / Real Estate

**Apify offers:** Zillow Scraper (~$2.00 per 1,000 results, 2,000 free)

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **Scrapy + custom spiders** | DIY | Extract listings with price, address, photos, zestimate |
| **[GitHub zillow-scraper projects](https://github.com/topics/zillow-scraper)** | Open-source | Community-maintained Zillow scrapers |
| **Zillow's own API** | Limited | Some property data available through partner programs |

---

## 6. Job Board Scraper Replacements

**Apify offers:** Indeed Scraper, Glassdoor Scraper, LinkedIn Jobs Scraper, All Jobs Scraper

**Free replacements:**

| Tool | Type | What It Does |
|------|------|-------------|
| **[JobSpy](https://github.com/Bunsly/JobSpy)** | Open-source Python | Scrapes Indeed, LinkedIn, Glassdoor, Google, ZipRecruiter simultaneously |
| **Scrapy + custom spiders** | DIY | Build per-site spiders |
| **Official job APIs** | Free/limited | Indeed Publisher API, LinkedIn Jobs API (partner), Google Jobs structured data |
| **RSS feeds** | Free | Many job boards offer RSS. Combine with feed parsers |

---

## 7. AI/LLM Content Crawler Replacements

**Apify offers:** Website Content Crawler (converts sites to clean Markdown for AI models, integrates with LangChain/LlamaIndex)

**Free replacements:**

| Tool | Stars | What It Does |
|------|-------|-------------|
| **[Crawl4AI](https://github.com/unclecode/crawl4ai)** | ~50,000+ | 6x faster than competitors. Clean Markdown output. Fully offline with local LLMs. Docker deployment. BFS/DFS/BestFirst crawl strategies |
| **[Firecrawl (self-hosted)](https://github.com/firecrawl/firecrawl)** | ~70,000+ | API service converting URLs to Markdown. LangChain/LlamaIndex native. Self-hosted version is free but lacks Fire-engine anti-bot |
| **[ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai)** | ~20,000+ | Describe what you want in natural language. Works with Ollama (local LLMs) for zero cost |
| **Crawlee + custom pipeline** | ~16,500 | Build custom crawlers that output Markdown/structured data for your AI pipeline |

**Best free approach:** Crawl4AI for general web-to-markdown conversion, ScrapeGraphAI for intelligent extraction with local LLMs.

---

## 8. Free Proxies & Anti-Bot Tools

### Free Proxy Services

| Provider | Free Tier | Notes |
|----------|-----------|-------|
| **[Webshare](https://www.webshare.io/)** | 10 rotating proxies, unmetered bandwidth | Most reliable free proxy provider |
| **[ProxyScrape](https://proxyscrape.com/)** | 100 free rotating IPs | Auto-rotating, good for lightweight scraping |
| **[ScraperAPI](https://www.scraperapi.com/)** | 5,000 free credits | 40M+ rotating proxies, 50+ countries, handles CAPTCHAs |

### Self-Hosted Proxy Tools

| Tool | What It Does |
|------|-------------|
| **[Scylla](https://github.com/imWildCat/scylla)** | All-in-one proxy crawler + checker + HTTP forward proxy |
| **[scrapy-rotating-proxies](https://github.com/TeamHG-Memex/scrapy-rotating-proxies)** | Scrapy middleware for proxy rotation |
| **Free proxy lists on GitHub** | Community-maintained, auto-updated daily (HTTP/HTTPS/SOCKS) |

### Anti-Bot Bypass (Open-Source)

| Tool | What It Does | Best For |
|------|-------------|----------|
| **[puppeteer-extra-plugin-stealth](https://github.com/berstend/puppeteer-extra)** | Evasion modules for Puppeteer | Most established stealth plugin |
| **[Patchright](https://github.com/AzizKama/Patchright)** | Stealthier fork of Playwright | Advanced anti-bot scenarios, can bypass Kasada |
| **[Camoufox](https://github.com/AzizKama/camoufox)** | Full browser automation with comprehensive stealth | Avoiding CAPTCHAs |
| **[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr)** | Proxy server bypassing Cloudflare/DDoS-GUARD challenges | Cloudflare-protected sites |
| **[Solvearr](https://github.com/revenz/solvearr)** | Drop-in FlareSolverr replacement using TLS fingerprint tampering | Lightweight Cloudflare bypass |
| **[undetected-chromedriver / Nodriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver)** | Modified ChromeDriver bypassing bot detection | Selenium-based scraping |
| **[Botasaurus](https://github.com/AzizKama/botasaurus)** | Python framework with anti-blocking features | Cloudflare-protected sites |

### Key Anti-Bot Strategy

Combine these layers for best results:
1. **TLS fingerprint spoofing** (Patchright or Camoufox)
2. **Browser stealth plugins** (puppeteer-stealth or playwright-stealth)
3. **Proxy rotation** (Webshare free + scrapy-rotating-proxies)
4. **Realistic headers** (rotating User-Agent, Accept-Language, etc.)
5. **Human-like behavior** (random delays, mouse movements, scroll patterns)

---

## 9. Recommended Self-Hosted Stacks

### Python Stack (Recommended)

```
Core:       Scrapy + scrapy-playwright (JS rendering)
AI/LLM:    Crawl4AI (web-to-markdown for RAG/vector DBs)
Proxies:    Webshare free tier (10 proxies) + Scylla (self-hosted)
Anti-bot:   FlareSolverr + Patchright
Scheduling: Airflow or system cron
Storage:    PostgreSQL / MongoDB / local JSON/CSV
```

**Cost: $0** (only your server/compute costs)

### JavaScript/TypeScript Stack

```
Core:       Crawlee (built-in anti-bot + proxy rotation + queuing)
Browser:    Playwright + puppeteer-extra-plugin-stealth
AI/LLM:    Firecrawl self-hosted (Markdown output)
Anti-bot:   FlareSolverr (Cloudflare bypass)
Scheduling: n8n (open-source workflow automation)
Storage:    PostgreSQL / MongoDB / local files
```

**Cost: $0** (only your server/compute costs)

### Minimal Quick-Start Stack

If you just need to scrape a few sites without heavy infrastructure:

```
1. Install Python + Playwright:  pip install playwright crawl4ai
2. Use Crawl4AI for simple sites
3. Use Playwright + stealth for JS-heavy sites
4. Store results as JSON/CSV locally
5. Schedule with cron
```

---

## 10. Quick Reference Table

| Apify Actor Category | Best Free Replacement | Difficulty | Notes |
|---------------------|----------------------|-----------|-------|
| **Instagram Scraper** | drawrowfly/instagram-scraper | Medium | Anti-bot is aggressive; needs proxies at scale |
| **TikTok Scraper** | davidteather/TikTok-Api | Medium | API changes frequently |
| **Twitter/X Scraper** | Playwright + stealth | Medium-Hard | No good free API; browser scraping is main option |
| **YouTube Scraper** | yt-dlp (`--dump-json`) | Easy | Gold standard, 90K+ GitHub stars |
| **Reddit Scraper** | PRAW + `.json` endpoints | Easy | Easiest platform to scrape |
| **LinkedIn Scraper** | joeyism/linkedin_scraper | Hard | Legal risks; account bans common |
| **Facebook Scraper** | kevinzg/facebook-scraper | Hard | Advanced anti-bot; ToS violations |
| **Amazon Scraper** | Scrapy + custom spiders | Medium | HTML changes frequently; needs maintenance |
| **Google Maps Scraper** | gosom/google-maps-scraper | Easy | MIT license, CLI + Web UI + REST API |
| **Google SERP Scraper** | Serper (2,500 free/month) | Easy | JS required since Jan 2025 |
| **Airbnb/Booking Scraper** | Crawlee + Playwright | Medium | Dynamic content, anti-bot |
| **Job Board Scraper** | JobSpy (multi-site) | Easy | Scrapes Indeed+LinkedIn+Glassdoor+more simultaneously |
| **Website Content Crawler** | Crawl4AI | Easy | Best free option for AI/LLM pipelines |
| **General Web Scraper** | Scrapy or Crawlee | Easy-Medium | Depends on target site complexity |

---

## Legal Disclaimer

Web scraping legality varies by jurisdiction and target website. Key considerations:

- **Always check robots.txt** and Terms of Service before scraping
- **Public data** (visible without login) is generally safer to scrape
- **GDPR/CCPA** compliance is required when collecting personal data
- **Rate limiting** your requests is both ethical and practical (avoids IP bans)
- **LinkedIn, Facebook, Instagram** have actively pursued legal action against scrapers
- The **hiQ Labs v. LinkedIn** (2022) case established that scraping publicly available data is not a CFAA violation in the US, but this is still evolving law

Use these tools responsibly and within applicable legal frameworks.
