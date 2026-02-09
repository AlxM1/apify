"""Global settings and platform registry."""

PLATFORMS = {
    # Phase 1 - Easy, high value
    "youtube": {
        "module": "scrapers.youtube",
        "class": "YouTubeScraper",
        "rate_limit": 2.0,  # requests per second
    },
    "reddit": {
        "module": "scrapers.reddit",
        "class": "RedditScraper",
        "rate_limit": 1.0,
    },
    "bluesky": {
        "module": "scrapers.bluesky",
        "class": "BlueskyScraper",
        "rate_limit": 5.0,
    },
    "hackernews": {
        "module": "scrapers.hackernews",
        "class": "HackerNewsScraper",
        "rate_limit": 5.0,
    },
    "medium": {
        "module": "scrapers.medium",
        "class": "MediumScraper",
        "rate_limit": 1.0,
    },
    "tumblr": {
        "module": "scrapers.tumblr",
        "class": "TumblrScraper",
        "rate_limit": 1.0,
    },
    # Phase 2 - Medium difficulty
    "twitter": {
        "module": "scrapers.twitter",
        "class": "TwitterScraper",
        "rate_limit": 0.5,
    },
    "instagram": {
        "module": "scrapers.instagram",
        "class": "InstagramScraper",
        "rate_limit": 0.3,
    },
    "tiktok": {
        "module": "scrapers.tiktok",
        "class": "TikTokScraper",
        "rate_limit": 0.5,
    },
    "pinterest": {
        "module": "scrapers.pinterest",
        "class": "PinterestScraper",
        "rate_limit": 1.0,
    },
    "threads": {
        "module": "scrapers.threads",
        "class": "ThreadsScraper",
        "rate_limit": 0.5,
    },
    "mastodon": {
        "module": "scrapers.mastodon",
        "class": "MastodonScraper",
        "rate_limit": 5.0,
    },
    # Phase 3 - Medium value
    "telegram": {
        "module": "scrapers.telegram",
        "class": "TelegramScraper",
        "rate_limit": 1.0,
    },
    "twitch": {
        "module": "scrapers.twitch",
        "class": "TwitchScraper",
        "rate_limit": 2.0,
    },
    "discord": {
        "module": "scrapers.discord",
        "class": "DiscordScraper",
        "rate_limit": 1.0,
    },
    "quora": {
        "module": "scrapers.quora",
        "class": "QuoraScraper",
        "rate_limit": 0.5,
    },
    "snapchat": {
        "module": "scrapers.snapchat",
        "class": "SnapchatScraper",
        "rate_limit": 0.5,
    },
    "kick": {
        "module": "scrapers.kick",
        "class": "KickScraper",
        "rate_limit": 1.0,
    },
    # Phase 4 - Specialized
    "substack": {
        "module": "scrapers.substack",
        "class": "SubstackScraper",
        "rate_limit": 1.0,
    },
    "rumble": {
        "module": "scrapers.rumble",
        "class": "RumbleScraper",
        "rate_limit": 1.0,
    },
    "vk": {
        "module": "scrapers.vk",
        "class": "VKScraper",
        "rate_limit": 3.0,
    },
    "weibo": {
        "module": "scrapers.weibo",
        "class": "WeiboScraper",
        "rate_limit": 0.5,
    },
    "truthsocial": {
        "module": "scrapers.truthsocial",
        "class": "TruthSocialScraper",
        "rate_limit": 2.0,
    },
    "producthunt": {
        "module": "scrapers.producthunt",
        "class": "ProductHuntScraper",
        "rate_limit": 1.0,
    },
    "dribbble": {
        "module": "scrapers.dribbble",
        "class": "DribbbleScraper",
        "rate_limit": 1.0,
    },
    "deviantart": {
        "module": "scrapers.deviantart",
        "class": "DeviantArtScraper",
        "rate_limit": 1.0,
    },
    "flickr": {
        "module": "scrapers.flickr",
        "class": "FlickrScraper",
        "rate_limit": 2.0,
    },
    "soundcloud": {
        "module": "scrapers.soundcloud",
        "class": "SoundCloudScraper",
        "rate_limit": 1.0,
    },
    "lemon8": {
        "module": "scrapers.lemon8",
        "class": "Lemon8Scraper",
        "rate_limit": 0.5,
    },
    "nextdoor": {
        "module": "scrapers.nextdoor",
        "class": "NextdoorScraper",
        "rate_limit": 0.3,
    },
}


def get_scraper_class(platform: str):
    """Dynamically import and return a scraper class."""
    import importlib

    if platform not in PLATFORMS:
        raise ValueError(
            f"Unknown platform '{platform}'. "
            f"Available: {', '.join(sorted(PLATFORMS.keys()))}"
        )
    info = PLATFORMS[platform]
    module = importlib.import_module(info["module"])
    return getattr(module, info["class"])
