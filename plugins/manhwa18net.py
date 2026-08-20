from typing import List, AsyncIterable
from urllib.parse import urlparse, urljoin, quote_plus
from html import unescape
import json

from bs4 import BeautifulSoup

from plugins.client import MangaClient, MangaCard, MangaChapter, LastChapter


class Manhwa18NetClient(MangaClient):
    base_url = urlparse("https://manhwa18.net/")
    search_url = urljoin(base_url.geturl(), "tim-kiem")
    updates_url = base_url.geturl()

    pre_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
            "Gecko/20100101 Firefox/128.0"
        )
    }

    def __init__(self, *args, name="Manhwa18", **kwargs):
        super().__init__(
            *args,
            name=name,
            headers=self.pre_headers,
            **kwargs
        )

    def _get_page_data(self, page: bytes):
        bs = BeautifulSoup(page, "html.parser")
        app = bs.find("div", id="app")

        if not app:
            return {}

        data = app.get("data-page")
        if not data:
            return {}

        try:
            return json.loads(unescape(data))
        except (json.JSONDecodeError, TypeError):
            return {}

    def mangas_from_page(self, page: bytes):
        data = self._get_page_data(page)
        props = data.get("props", {})

        # Search results may be inside different pagination structures.
        # Try the common keys used by the site.
        candidates = [
            props.get("mangas"),
            props.get("results"),
            props.get("searchResults"),
        ]

        items = []

        for candidate in candidates:
            if isinstance(candidate, list):
                items = candidate
                break

            if isinstance(candidate, dict):
                items = (
                    candidate.get("data")
                    or candidate.get("items")
                    or []
                )
                if items:
                    break

        mangas = []

        for item in items:
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("title")
            slug = item.get("slug")
            image = (
                item.get("cover_url")
                or item.get("cover")
                or item.get("coverUrl")
            )

            if not name or not slug:
                continue

            manga_url = urljoin(
                self.base_url.geturl(),
                f"manga/{slug}"
            )

            mangas.append(
                MangaCard(
                    self,
                    name,
                    manga_url,
                    image or ""
                )
            )

        return mangas

    def chapters_from_page(
        self,
        page: bytes,
        manga: MangaCard = None
    ):
        data = self._get_page_data(page)
        props = data.get("props", {})

        manga_data = props.get("manga") or {}

        chapters = (
            manga_data.get("chapters")
            or props.get("chapters")
            or props.get("listChapters")
            or []
        )

        if isinstance(chapters, dict):
            chapters = (
                chapters.get("data")
                or chapters.get("items")
                or []
            )

        result = []

        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue

            name = chapter.get("name")
            slug = chapter.get("slug")

            if not name or not slug:
                continue

            chapter_url = urljoin(
                manga.url.rstrip("/") + "/",
                slug
            )

            result.append(
                MangaChapter(
                    self,
                    name,
                    chapter_url,
                    manga,
                    []
                )
            )

        return result

    def updates_from_page(self, page: bytes):
        """
        Extract latest chapter URLs from the homepage.

        The homepage structure can change, so this checks
        several possible data keys from the Inertia payload.
        """
        data = self._get_page_data(page)
        props = data.get("props", {})

        candidates = [
            props.get("latestChapters"),
            props.get("chapters"),
            props.get("updates"),
            props.get("latest"),
        ]

        urls = {}

        for candidate in candidates:
            if not isinstance(candidate, list):
                continue

            for item in candidate:
                if not isinstance(item, dict):
                    continue

                manga = item.get("manga") or {}

                manga_slug = (
                    manga.get("slug")
                    or item.get("mangaSlug")
                )

                chapter_slug = item.get("slug")

                if manga_slug and chapter_slug:
                    manga_url = urljoin(
                        self.base_url.geturl(),
                        f"manga/{manga_slug}"
                    )

                    chapter_url = urljoin(
                        manga_url.rstrip("/") + "/",
                        chapter_slug
                    )

                    urls[manga_url] = chapter_url

            if urls:
                break

        return urls

    async def pictures_from_chapters(
        self,
        content: bytes,
        response=None
    ):
        data = self._get_page_data(content)
        props = data.get("props", {})

        images = props.get("chapterImages") or []

        result = []

        for image in images:
            if not isinstance(image, dict):
                continue

            src = image.get("src")

            if src:
                result.append(
                    quote(src, safe=":/%?=&")
                )

        # Fallback: chapterContent contains <img src="...">
        if not result:
            chapter_content = props.get("chapterContent")

            if chapter_content:
                bs = BeautifulSoup(
                    chapter_content,
                    "html.parser"
                )

                for img in bs.find_all("img"):
                    src = img.get("src")

                    if src:
                        result.append(
                            quote(src, safe=":/%?=&")
                        )

        return result

    async def search(
        self,
        query: str = "",
        page: int = 1
    ) -> List[MangaCard]:

        query = quote_plus(query)

        request_url = self.search_url

        if query:
            request_url += f"?q={query}"

        content = await self.get_url(request_url)

        return self.mangas_from_page(content)

    async def get_chapters(
        self,
        manga_card: MangaCard,
        page: int = 1
    ) -> List[MangaChapter]:

        content = await self.get_url(manga_card.url)

        chapters = self.chapters_from_page(
            content,
            manga_card
        )

        start = (page - 1) * 20
        end = page * 20

        return chapters[start:end]

    async def iter_chapters(
        self,
        manga_url: str,
        manga_name
    ) -> AsyncIterable[MangaChapter]:

        manga_card = MangaCard(
            self,
            manga_name,
            manga_url,
            ""
        )

        content = await self.get_url(manga_url)

        for chapter in self.chapters_from_page(
            content,
            manga_card
        ):
            yield chapter

    async def contains_url(self, url: str):
        return url.startswith(
            self.base_url.geturl()
        )

    async def check_updated_urls(
        self,
        last_chapters: List[LastChapter]
    ):

        content = await self.get_url(
            self.updates_url
        )

        updates = self.updates_from_page(content)

        updated = [
            lc.url
            for lc in last_chapters
            if (
                updates.get(lc.url)
                and updates.get(lc.url) != lc.chapter_url
            )
        ]

        not_updated = [
            lc.url
            for lc in last_chapters
            if (
                not updates.get(lc.url)
                or updates.get(lc.url) == lc.chapter_url
            )
        ]

        return updated, not_updated
