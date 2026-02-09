"""Flickr scraper using the public API, RSS feeds, and web scraping fallback.

No API key required for many endpoints. Flickr exposes public photo feeds
via RSS and has API endpoints that work without authentication for public data.
Supports: user profiles, photos, photosets, search.
"""

import json
import logging
import re
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, ScraperConfig, ScraperResult, ContentType

logger = logging.getLogger(__name__)

FLICKR_BASE = "https://www.flickr.com"
FLICKR_API = "https://api.flickr.com/services/rest"
FLICKR_FEEDS = "https://api.flickr.com/services/feeds"


class FlickrScraper(BaseScraper):
    """Flickr scraper using public API endpoints, RSS feeds, and HTML fallback.

    No API key required for public feeds. Some REST API methods work without
    a key, and RSS feeds provide structured access to public photos.

    Usage:
        scraper = FlickrScraper()
        results = await scraper.scrape_profile("nasahqphoto")
        results = await scraper.scrape_posts("nasahqphoto", max_results=50)
        results = await scraper.search("sunset landscape", max_results=20)
    """

    def __init__(self, config: ScraperConfig | None = None, api_key: str | None = None):
        super().__init__(config)
        self._api_key = api_key

    @property
    def platform_name(self) -> str:
        return "flickr"

    async def scrape_profile(self, identifier: str) -> list[ScraperResult]:
        """Scrape a Flickr user profile.

        Args:
            identifier: Username, user NSID, or profile URL.
        """
        username = self._normalize_username(identifier)
        profile_url = f"{FLICKR_BASE}/people/{username}/"

        # Try the API first if we have a key
        if self._api_key:
            profile = await self._fetch_profile_api(username)
            if profile:
                return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

        # Fall back to web scraping
        resp = await self.fetch(profile_url)
        soup = BeautifulSoup(resp.text, "lxml")

        profile = self._extract_profile_from_html(soup, username, profile_url)
        return [self.make_result(ContentType.PROFILE, profile, url=profile_url)]

    async def scrape_posts(
        self, source: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape photos from a Flickr user's photostream.

        Uses RSS feed for reliable access, with API and HTML fallbacks.

        Args:
            source: Username, NSID, or profile/photostream URL.
            max_results: Maximum photos to fetch.
        """
        limit = max_results or self.config.max_results
        username = self._normalize_username(source)

        # Strategy 1: Try the public photos RSS feed
        results = await self._fetch_photos_rss(username, limit)
        if results:
            return results[:limit]

        # Strategy 2: Try the API if key is available
        if self._api_key:
            results = await self._fetch_photos_api(username, limit)
            if results:
                return results[:limit]

        # Strategy 3: Fall back to web scraping the photostream
        return await self._fetch_photos_html(username, limit)

    async def scrape_photoset(
        self, photoset_url: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Scrape photos from a Flickr album/photoset.

        Args:
            photoset_url: Full URL to the album page.
            max_results: Maximum photos to fetch.
        """
        limit = max_results or self.config.max_results

        resp = await self.fetch(photoset_url)
        soup = BeautifulSoup(resp.text, "lxml")

        results = []
        # Extract album metadata
        album_title = self._meta(soup, "og:title") or ""

        # Parse the model data from the page
        model_data = self._extract_model_data(soup)
        if model_data:
            photos = self._extract_photos_from_model(model_data, limit)
            for photo in photos:
                photo["album_title"] = album_title
                results.append(
                    self.make_result(ContentType.IMAGE, photo, url=photo.get("url", ""))
                )
            return results

        # Fallback: find photo links in HTML
        for thumb in soup.find_all("div", class_=re.compile(r"photo-list-photo")):
            if len(results) >= limit:
                break
            photo_data = self._parse_photo_thumb(thumb)
            if photo_data:
                photo_data["album_title"] = album_title
                results.append(
                    self.make_result(ContentType.IMAGE, photo_data, url=photo_data.get("url", ""))
                )

        return results

    async def search(
        self, query: str, max_results: int | None = None
    ) -> list[ScraperResult]:
        """Search Flickr photos.

        Uses the public feed search endpoint, with API and HTML fallbacks.

        Args:
            query: Search query string.
            max_results: Maximum results.
        """
        limit = max_results or self.config.max_results

        # Strategy 1: Use the public photos feed with tags search
        results = await self._search_feed(query, limit)
        if results:
            return results[:limit]

        # Strategy 2: Use the API if key is available
        if self._api_key:
            results = await self._search_api(query, limit)
            if results:
                return results[:limit]

        # Strategy 3: Fall back to scraping the search results page
        return await self._search_html(query, limit)

    # --- API methods (require api_key) ---

    async def _fetch_profile_api(self, username: str) -> dict | None:
        """Fetch profile via Flickr REST API."""
        try:
            # First resolve username to NSID
            nsid = await self._resolve_nsid(username)
            if not nsid:
                return None

            params = {
                "method": "flickr.people.getInfo",
                "api_key": self._api_key,
                "user_id": nsid,
                "format": "json",
                "nojsoncallback": "1",
            }
            data = await self.fetch_json(FLICKR_API, params=params)
            person = data.get("person", {})

            return {
                "nsid": person.get("nsid", nsid),
                "username": person.get("username", {}).get("_content", username),
                "realname": person.get("realname", {}).get("_content", ""),
                "description": person.get("description", {}).get("_content", ""),
                "location": person.get("location", {}).get("_content", ""),
                "photo_count": person.get("photos", {}).get("count", {}).get("_content", 0),
                "profile_url": person.get("profileurl", {}).get("_content", ""),
                "photos_url": person.get("photosurl", {}).get("_content", ""),
                "icon_server": person.get("iconserver", ""),
                "icon_farm": person.get("iconfarm", ""),
                "is_pro": person.get("ispro", 0) == 1,
                "date_joined": person.get("photos", {}).get("firstdatetaken", {}).get("_content", ""),
            }
        except Exception as e:
            logger.warning(f"Flickr API profile fetch failed: {e}")
            return None

    async def _resolve_nsid(self, username: str) -> str | None:
        """Resolve a username to an NSID via the API."""
        try:
            params = {
                "method": "flickr.people.findByUsername",
                "api_key": self._api_key,
                "username": username,
                "format": "json",
                "nojsoncallback": "1",
            }
            data = await self.fetch_json(FLICKR_API, params=params)
            return data.get("user", {}).get("nsid")
        except Exception:
            # Try as URL-based lookup
            try:
                params = {
                    "method": "flickr.urls.lookupUser",
                    "api_key": self._api_key,
                    "url": f"{FLICKR_BASE}/photos/{username}/",
                    "format": "json",
                    "nojsoncallback": "1",
                }
                data = await self.fetch_json(FLICKR_API, params=params)
                return data.get("user", {}).get("id")
            except Exception:
                return None

    async def _fetch_photos_api(self, username: str, limit: int) -> list[ScraperResult]:
        """Fetch photos via the Flickr REST API."""
        nsid = await self._resolve_nsid(username)
        if not nsid:
            return []

        results = []
        page = 1
        per_page = min(limit, 100)

        while len(results) < limit:
            params = {
                "method": "flickr.people.getPublicPhotos",
                "api_key": self._api_key,
                "user_id": nsid,
                "per_page": per_page,
                "page": page,
                "extras": "description,date_upload,date_taken,owner_name,tags,"
                          "views,url_sq,url_m,url_l,url_o",
                "format": "json",
                "nojsoncallback": "1",
            }
            data = await self.fetch_json(FLICKR_API, params=params)
            photos = data.get("photos", {}).get("photo", [])

            if not photos:
                break

            for photo in photos:
                if len(results) >= limit:
                    break
                photo_data = self._normalize_api_photo(photo)
                results.append(
                    self.make_result(ContentType.IMAGE, photo_data, url=photo_data.get("url", ""))
                )

            total_pages = data.get("photos", {}).get("pages", 1)
            if page >= total_pages:
                break
            page += 1

        return results

    async def _search_api(self, query: str, limit: int) -> list[ScraperResult]:
        """Search photos via the Flickr REST API."""
        results = []
        page = 1
        per_page = min(limit, 100)

        while len(results) < limit:
            params = {
                "method": "flickr.photos.search",
                "api_key": self._api_key,
                "text": query,
                "per_page": per_page,
                "page": page,
                "extras": "description,date_upload,date_taken,owner_name,tags,"
                          "views,url_sq,url_m,url_l",
                "sort": "relevance",
                "format": "json",
                "nojsoncallback": "1",
            }
            data = await self.fetch_json(FLICKR_API, params=params)
            photos = data.get("photos", {}).get("photo", [])

            if not photos:
                break

            for photo in photos:
                if len(results) >= limit:
                    break
                photo_data = self._normalize_api_photo(photo)
                results.append(
                    self.make_result(ContentType.SEARCH, photo_data, url=photo_data.get("url", ""))
                )

            total_pages = data.get("photos", {}).get("pages", 1)
            if page >= total_pages:
                break
            page += 1

        return results

    # --- RSS feed methods ---

    async def _fetch_photos_rss(self, username: str, limit: int) -> list[ScraperResult]:
        """Fetch photos via the public RSS feed."""
        feed_url = f"{FLICKR_FEEDS}/photos_public.gne?id={username}&format=rss_200"

        try:
            resp = await self.fetch(feed_url)
            return self._parse_photo_rss(resp.text, limit, ContentType.IMAGE)
        except Exception:
            # Try with the username as a tag-based feed
            try:
                feed_url = (
                    f"{FLICKR_FEEDS}/photos_public.gne?"
                    f"tags={quote(username)}&format=rss_200"
                )
                resp = await self.fetch(feed_url)
                return self._parse_photo_rss(resp.text, limit, ContentType.IMAGE)
            except Exception as e:
                logger.debug(f"RSS feed fetch failed for {username}: {e}")
                return []

    async def _search_feed(self, query: str, limit: int) -> list[ScraperResult]:
        """Search photos via the public photos feed."""
        tags = query.replace(" ", ",")
        feed_url = f"{FLICKR_FEEDS}/photos_public.gne?tags={quote(tags)}&format=rss_200"

        try:
            resp = await self.fetch(feed_url)
            return self._parse_photo_rss(resp.text, limit, ContentType.SEARCH)
        except Exception as e:
            logger.debug(f"Feed search failed: {e}")
            return []

    def _parse_photo_rss(
        self, xml_text: str, limit: int, content_type: ContentType
    ) -> list[ScraperResult]:
        """Parse Flickr RSS feed XML into results."""
        results = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Failed to parse Flickr RSS feed")
            return results

        channel = root.find("channel")
        if channel is None:
            return results

        # Namespaces used by Flickr feeds
        ns = {
            "media": "http://search.yahoo.com/mrss/",
            "dc": "http://purl.org/dc/elements/1.1/",
            "flickr": "urn:flickr:user",
        }

        for item in channel.findall("item"):
            if len(results) >= limit:
                break

            title = self._xml_text(item, "title")
            link = self._xml_text(item, "link")
            description_raw = self._xml_text(item, "description")
            pub_date = self._xml_text(item, "pubDate")
            author = self._xml_text(item, f"{{{ns['dc']}}}creator")

            # Extract image URL from media:content or description
            image_url = ""
            media_content = item.find(f"{{{ns['media']}}}content")
            if media_content is not None:
                image_url = media_content.get("url", "")

            media_thumb = item.find(f"{{{ns['media']}}}thumbnail")
            thumbnail = media_thumb.get("url", "") if media_thumb is not None else ""

            # Parse tags from media:category
            tags = []
            for cat in item.findall(f"{{{ns['media']}}}category"):
                if cat.text:
                    tags.extend(t.strip() for t in cat.text.split(",") if t.strip())

            # Clean description HTML
            description = ""
            if description_raw:
                desc_soup = BeautifulSoup(description_raw, "lxml")
                description = desc_soup.get_text(strip=True)[:500]

            photo = {
                "title": title,
                "url": link,
                "image_url": image_url or thumbnail,
                "thumbnail": thumbnail,
                "author": author,
                "description": description,
                "published_date": pub_date,
                "tags": tags,
            }
            results.append(self.make_result(content_type, photo, url=link))

        return results

    # --- HTML scraping methods ---

    def _extract_profile_from_html(
        self, soup: BeautifulSoup, username: str, url: str
    ) -> dict:
        """Extract profile data from a Flickr profile page."""
        # Try to find model data embedded in the page
        model_data = self._extract_model_data(soup)

        if model_data:
            person = (
                model_data.get("person", {})
                or model_data.get("owner", {})
                or {}
            )
            if person:
                return {
                    "username": person.get("pathAlias", "") or person.get("username", username),
                    "realname": person.get("realname", ""),
                    "nsid": person.get("nsid", ""),
                    "description": person.get("description", ""),
                    "location": person.get("location", ""),
                    "photo_count": person.get("photoCount", 0),
                    "follower_count": person.get("followerCount", 0),
                    "following_count": person.get("followingCount", 0),
                    "is_pro": person.get("isPro", False),
                    "profile_url": url,
                    "avatar": person.get("buddyicon", {}).get("large", ""),
                }

        # Fallback to meta tags
        return {
            "username": username,
            "realname": self._meta(soup, "og:title") or username,
            "description": self._meta(soup, "og:description") or "",
            "avatar": self._meta(soup, "og:image") or "",
            "profile_url": url,
        }

    async def _fetch_photos_html(self, username: str, limit: int) -> list[ScraperResult]:
        """Scrape photos from a user's photostream HTML page."""
        results = []
        page_num = 1

        while len(results) < limit:
            url = f"{FLICKR_BASE}/photos/{username}/page{page_num}"
            try:
                resp = await self.fetch(url)
            except Exception as e:
                logger.warning(f"Failed to fetch photostream page {page_num}: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Try embedded model data first
            model_data = self._extract_model_data(soup)
            if model_data:
                photos = self._extract_photos_from_model(model_data, limit - len(results))
                for photo in photos:
                    results.append(
                        self.make_result(ContentType.IMAGE, photo, url=photo.get("url", ""))
                    )
                if photos:
                    page_num += 1
                    continue

            # Fallback: parse photo thumbnails from HTML
            photo_divs = soup.find_all("div", class_=re.compile(r"photo-list-photo"))
            if not photo_divs:
                break

            for div in photo_divs:
                if len(results) >= limit:
                    break
                photo_data = self._parse_photo_thumb(div)
                if photo_data:
                    results.append(
                        self.make_result(
                            ContentType.IMAGE, photo_data, url=photo_data.get("url", "")
                        )
                    )

            # Check for next page
            next_link = soup.find("a", class_=re.compile(r"next"))
            if not next_link or not photo_divs:
                break

            page_num += 1

        return results

    async def _search_html(self, query: str, limit: int) -> list[ScraperResult]:
        """Search Flickr by scraping the search results page."""
        results = []
        page_num = 1

        while len(results) < limit:
            params = urlencode({"text": query, "page": page_num})
            url = f"{FLICKR_BASE}/search/?{params}"

            try:
                resp = await self.fetch(url)
            except Exception as e:
                logger.warning(f"Search page fetch failed: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            # Try model data
            model_data = self._extract_model_data(soup)
            if model_data:
                photos = self._extract_photos_from_model(model_data, limit - len(results))
                for photo in photos:
                    results.append(
                        self.make_result(ContentType.SEARCH, photo, url=photo.get("url", ""))
                    )
                if photos:
                    page_num += 1
                    continue

            # Fallback: parse search result thumbnails
            photo_divs = soup.find_all("div", class_=re.compile(r"photo-list-photo"))
            if not photo_divs:
                break

            for div in photo_divs:
                if len(results) >= limit:
                    break
                photo_data = self._parse_photo_thumb(div)
                if photo_data:
                    results.append(
                        self.make_result(
                            ContentType.SEARCH, photo_data, url=photo_data.get("url", "")
                        )
                    )

            if not photo_divs:
                break

            page_num += 1

        return results

    # --- Data extraction helpers ---

    def _extract_model_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract the modelExport JSON data embedded in Flickr pages."""
        for script in soup.find_all("script"):
            text = script.string or ""
            # Flickr embeds model data as modelExport or appContext
            match = re.search(
                r'modelExport\s*:\s*(\{.+?\})\s*,\s*(?:auth|register)',
                text,
                re.DOTALL,
            )
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

            # Alternative: look for Y.ClientApp.init data
            match = re.search(
                r'Y\.ClientApp\.init\s*\(\s*(\{.+?\})\s*\)',
                text,
                re.DOTALL,
            )
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        return None

    def _extract_photos_from_model(self, model_data: dict, limit: int) -> list[dict]:
        """Extract photo data from the modelExport structure."""
        photos = []
        seen_ids: set[str] = set()

        self._walk_for_photos(model_data, photos, seen_ids, limit)
        return photos

    def _walk_for_photos(
        self, data: Any, photos: list[dict], seen: set[str], limit: int
    ):
        """Recursively walk data looking for photo objects."""
        if len(photos) >= limit:
            return

        if isinstance(data, dict):
            # Check if this looks like a photo object
            photo_id = data.get("id") or data.get("photoId")
            title = data.get("title")
            owner = data.get("owner") or data.get("ownername") or data.get("pathalias")

            if photo_id and title is not None and str(photo_id) not in seen:
                seen.add(str(photo_id))
                owner_name = ""
                if isinstance(owner, dict):
                    owner_name = owner.get("username", "") or owner.get("pathAlias", "")
                elif isinstance(owner, str):
                    owner_name = owner

                photo = {
                    "photo_id": str(photo_id),
                    "title": title or "",
                    "description": (
                        data.get("description", {}).get("_content", "")
                        if isinstance(data.get("description"), dict)
                        else str(data.get("description", ""))
                    ),
                    "owner": owner_name,
                    "date_taken": data.get("datetaken", ""),
                    "date_uploaded": data.get("dateupload", ""),
                    "views": data.get("views", 0),
                    "tags": data.get("tags", ""),
                    "url": f"{FLICKR_BASE}/photos/{owner_name}/{photo_id}/" if owner_name else "",
                    "image_url": self._build_photo_url(data),
                    "thumbnail": data.get("url_sq", "") or data.get("thumbnail", ""),
                }
                photos.append(photo)

            for value in data.values():
                self._walk_for_photos(value, photos, seen, limit)

        elif isinstance(data, list):
            for item in data:
                self._walk_for_photos(item, photos, seen, limit)

    def _parse_photo_thumb(self, div_element) -> dict | None:
        """Parse photo data from a thumbnail div element."""
        # Flickr uses data attributes and background-image styles
        style = div_element.get("style", "")
        bg_match = re.search(r'url\(([^)]+)\)', style)
        thumbnail = bg_match.group(1).strip("\"'") if bg_match else ""

        # Photo link
        link = div_element.find("a")
        href = ""
        if link:
            href = link.get("href", "")
            if href and not href.startswith("http"):
                href = f"{FLICKR_BASE}{href}"

        title = div_element.get("title", "") or (link.get("title", "") if link else "")

        if not href and not thumbnail:
            return None

        return {
            "title": title,
            "url": href,
            "thumbnail": thumbnail,
            "image_url": self._thumb_to_large(thumbnail) if thumbnail else "",
        }

    @staticmethod
    def _build_photo_url(photo: dict) -> str:
        """Build a direct image URL from photo data fields."""
        # Prefer largest available size
        for key in ("url_o", "url_l", "url_m", "url_sq"):
            if photo.get(key):
                return photo[key]

        # Build from components
        farm = photo.get("farm", "")
        server = photo.get("server", "")
        pid = photo.get("id", "")
        secret = photo.get("secret", "")
        if farm and server and pid and secret:
            return f"https://farm{farm}.staticflickr.com/{server}/{pid}_{secret}_b.jpg"

        return ""

    @staticmethod
    def _thumb_to_large(thumb_url: str) -> str:
        """Convert a thumbnail URL to a larger size."""
        # Flickr size suffixes: _sq (square), _t (thumb), _s (small),
        # _m (medium), _z (640), _b (large), _o (original)
        return re.sub(r'_[sqtm]\.jpg', '_b.jpg', thumb_url)

    def _normalize_api_photo(self, photo: dict) -> dict:
        """Normalize a photo dict from the Flickr REST API."""
        owner = photo.get("owner", "")
        photo_id = photo.get("id", "")

        return {
            "photo_id": photo_id,
            "title": photo.get("title", ""),
            "description": (
                photo.get("description", {}).get("_content", "")
                if isinstance(photo.get("description"), dict)
                else str(photo.get("description", ""))
            ),
            "owner": photo.get("ownername", owner),
            "owner_nsid": owner,
            "date_taken": photo.get("datetaken", ""),
            "date_uploaded": photo.get("dateupload", ""),
            "views": int(photo.get("views", 0)),
            "tags": photo.get("tags", ""),
            "url": f"{FLICKR_BASE}/photos/{owner}/{photo_id}/",
            "image_url": self._build_photo_url(photo),
            "thumbnail": photo.get("url_sq", ""),
        }

    def _normalize_username(self, identifier: str) -> str:
        """Extract a username from various input formats."""
        if identifier.startswith("http"):
            path = urlparse(identifier).path.strip("/")
            parts = path.split("/")
            # /photos/username/... or /people/username/...
            if len(parts) >= 2 and parts[0] in ("photos", "people"):
                return parts[1]
            return parts[0] if parts else identifier
        return identifier.strip("@/")

    @staticmethod
    def _meta(soup: BeautifulSoup, name: str) -> str:
        """Extract content from a meta tag."""
        tag = (
            soup.find("meta", attrs={"property": name})
            or soup.find("meta", attrs={"name": name})
        )
        return tag.get("content", "") if tag else ""

    @staticmethod
    def _xml_text(element, tag: str) -> str:
        """Extract text from an XML element."""
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""
