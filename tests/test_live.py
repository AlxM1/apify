#!/usr/bin/env python3
"""Live integration tests for all scrapers."""

import asyncio
import json
import sys
import traceback
from datetime import datetime

# Add project root to path
sys.path.insert(0, "/home/user/apify")

from scrapers.base import ScraperConfig

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

config = ScraperConfig(max_results=5, delay_between_requests=0.5)

results_log = []


async def test_scraper(name, scraper_cls, tests):
    """Run a set of tests for a scraper."""
    print(f"\n{'='*60}")
    print(f"  Testing: {name}")
    print(f"{'='*60}")

    async with scraper_cls(config) as scraper:
        for test_name, test_fn in tests:
            try:
                result = await test_fn(scraper)
                count = len(result) if result else 0
                if count > 0:
                    print(f"  {PASS} {test_name} -> {count} results")
                    # Print first result data preview
                    first = result[0].to_dict()
                    data_keys = list(first.get("data", {}).keys())[:5]
                    print(f"       Keys: {data_keys}")
                    results_log.append({"scraper": name, "test": test_name, "status": "pass", "count": count})
                else:
                    print(f"  {FAIL} {test_name} -> 0 results (empty)")
                    results_log.append({"scraper": name, "test": test_name, "status": "fail", "error": "empty results"})
            except Exception as e:
                err = str(e)[:200]
                print(f"  {FAIL} {test_name} -> {type(e).__name__}: {err}")
                traceback.print_exc()
                results_log.append({"scraper": name, "test": test_name, "status": "fail", "error": err})


async def run_tier1():
    """Tier 1: Pure API scrapers (Reddit, Bluesky, HackerNews)"""
    print("\n" + "=" * 60)
    print("  TIER 1: Pure API Scrapers")
    print("=" * 60)

    # --- Reddit ---
    from scrapers.reddit import RedditScraper
    await test_scraper("Reddit", RedditScraper, [
        ("scrape_profile('spez')", lambda s: s.scrape_profile("spez")),
        ("scrape_posts('r/python', 5)", lambda s: s.scrape_posts("r/python", 5)),
        ("search('web scraping', 5)", lambda s: s.search("web scraping", 5)),
    ])

    # --- Bluesky ---
    from scrapers.bluesky import BlueskyScraper
    await test_scraper("Bluesky", BlueskyScraper, [
        ("scrape_profile('bsky.app')", lambda s: s.scrape_profile("bsky.app")),
        ("scrape_posts('bsky.app', 5)", lambda s: s.scrape_posts("bsky.app", 5)),
        ("search('python', 5)", lambda s: s.search("python", 5)),
    ])

    # --- HackerNews ---
    from scrapers.hackernews import HackerNewsScraper
    await test_scraper("HackerNews", HackerNewsScraper, [
        ("scrape_profile('pg')", lambda s: s.scrape_profile("pg")),
        ("scrape_posts('top', 5)", lambda s: s.scrape_posts("top", 5)),
        ("search('python', 5)", lambda s: s.search("python", 5)),
    ])


async def run_tier2():
    """Tier 2: Stable API scrapers (YouTube, Mastodon, Twitch, Kick)"""
    print("\n" + "=" * 60)
    print("  TIER 2: Stable API Scrapers")
    print("=" * 60)

    # --- YouTube ---
    from scrapers.youtube import YouTubeScraper
    await test_scraper("YouTube", YouTubeScraper, [
        ("scrape_posts('https://www.youtube.com/@veritasium', 3)", lambda s: s.scrape_posts("https://www.youtube.com/@veritasium", 3)),
        ("search('python tutorial', 3)", lambda s: s.search("python tutorial", 3)),
    ])

    # --- Mastodon ---
    from scrapers.mastodon import MastodonScraper
    await test_scraper("Mastodon", MastodonScraper, [
        ("scrape_profile('Gargron@mastodon.social')", lambda s: s.scrape_profile("Gargron@mastodon.social")),
        ("scrape_posts('Gargron@mastodon.social', 5)", lambda s: s.scrape_posts("Gargron@mastodon.social", 5)),
        ("scrape_timeline('public', 5)", lambda s: s.scrape_timeline("public", 5)),
    ])

    # --- Twitch ---
    from scrapers.twitch import TwitchScraper
    await test_scraper("Twitch", TwitchScraper, [
        ("scrape_profile('shroud')", lambda s: s.scrape_profile("shroud")),
        ("scrape_posts('shroud', 5)", lambda s: s.scrape_posts("shroud", 5)),
        ("search('valorant', 5)", lambda s: s.search("valorant", 5)),
    ])

    # --- Kick ---
    from scrapers.kick import KickScraper
    await test_scraper("Kick", KickScraper, [
        ("scrape_profile('xqc')", lambda s: s.scrape_profile("xqc")),
        ("search('gaming', 5)", lambda s: s.search("gaming", 5)),
    ])


async def run_tier3():
    """Tier 3: RSS/Web scraping (Medium, Tumblr, Substack, Telegram)"""
    print("\n" + "=" * 60)
    print("  TIER 3: RSS / Web Scraping")
    print("=" * 60)

    # --- Medium ---
    from scrapers.medium import MediumScraper
    await test_scraper("Medium", MediumScraper, [
        ("scrape_posts('@towards-data-science', 5)", lambda s: s.scrape_posts("towards-data-science", 5)),
        ("scrape_tag('python', 5)", lambda s: s.scrape_tag("python", 5)),
    ])

    # --- Tumblr ---
    from scrapers.tumblr import TumblrScraper
    await test_scraper("Tumblr", TumblrScraper, [
        ("scrape_profile('staff')", lambda s: s.scrape_profile("staff")),
        ("scrape_posts('staff', 5)", lambda s: s.scrape_posts("staff", 5)),
    ])

    # --- Substack ---
    from scrapers.substack import SubstackScraper
    await test_scraper("Substack", SubstackScraper, [
        ("scrape_posts('platformer', 5)", lambda s: s.scrape_posts("platformer", 5)),
    ])

    # --- Telegram ---
    from scrapers.telegram import TelegramScraper
    await test_scraper("Telegram", TelegramScraper, [
        ("scrape_profile('durov')", lambda s: s.scrape_profile("durov")),
        ("scrape_posts('durov', 5)", lambda s: s.scrape_posts("durov", 5)),
    ])


async def run_tier4():
    """Tier 4: Stealth web scraping (Pinterest, Quora, Discord, Rumble)"""
    print("\n" + "=" * 60)
    print("  TIER 4: Stealth Web Scraping")
    print("=" * 60)

    # --- Discord ---
    from scrapers.discord import DiscordScraper
    await test_scraper("Discord", DiscordScraper, [
        ("scrape_profile('minecraft')", lambda s: s.scrape_profile("minecraft")),
    ])

    # --- Pinterest ---
    from scrapers.pinterest import PinterestScraper
    await test_scraper("Pinterest", PinterestScraper, [
        ("search('home decor', 5)", lambda s: s.search("home decor", 5)),
    ])

    # --- Quora ---
    from scrapers.quora import QuoraScraper
    await test_scraper("Quora", QuoraScraper, [
        ("scrape_profile('Adam-DAngelo')", lambda s: s.scrape_profile("Adam-DAngelo")),
    ])

    # --- Rumble ---
    from scrapers.rumble import RumbleScraper
    await test_scraper("Rumble", RumbleScraper, [
        ("search('news', 5)", lambda s: s.search("news", 5)),
    ])


async def main():
    tier = sys.argv[1] if len(sys.argv) > 1 else "all"

    if tier in ("1", "tier1", "all"):
        await run_tier1()
    if tier in ("2", "tier2", "all"):
        await run_tier2()
    if tier in ("3", "tier3", "all"):
        await run_tier3()
    if tier in ("4", "tier4", "all"):
        await run_tier4()

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results_log if r["status"] == "pass")
    failed = sum(1 for r in results_log if r["status"] == "fail")
    total = len(results_log)
    print(f"  {PASS}: {passed}/{total}    {FAIL}: {failed}/{total}")

    if failed:
        print(f"\n  Failed tests:")
        for r in results_log:
            if r["status"] == "fail":
                print(f"    - {r['scraper']}: {r['test']} -> {r['error'][:100]}")

    # Save detailed log
    with open("/home/user/apify/output/test_results.json", "w") as f:
        json.dump(results_log, f, indent=2)
    print(f"\n  Detailed log: output/test_results.json")


if __name__ == "__main__":
    asyncio.run(main())
