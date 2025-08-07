import asyncio
import ssl
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import ClientTimeout


# Родительский класс с общим функционалом
class BaseParser:
    def __init__(self, base_url, start_url, max_concurrent_requests=3):
        self.BASE_URL = base_url
        self.START_URL = start_url
        self.MAX_CONCURRENT_REQUESTS = max_concurrent_requests
        self.HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    async def fetch_html(self, session, url):
        """Загружает HTML-код по URL."""
        timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
        async with session.get(url, headers=self.HEADERS, timeout=timeout) as response:
            response.raise_for_status()
            return await response.text()

    async def extract_article_links(self, session, page_num):
        """Извлекает ссылки на статьи с одной страницы. Этот метод нужно переопределить."""
        raise NotImplementedError(
            "Метод extract_article_links должен быть реализован в дочернем классе."
        )

    async def extract_article_content(self, session, article_url):
        """Извлекает контент одной статьи. Этот метод нужно переопределить."""
        raise NotImplementedError(
            "Метод extract_article_content должен быть реализован в дочернем классе."
        )

    async def parse(self, page_to_parse):
        """Основной метод для запуска парсинга."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
        connector = aiohttp.TCPConnector(ssl=ssl_context, limit=10)

        # Это ограничит количество одновременно выполняющихся задач
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Получаем все ссылки на статьи со всех страниц
            async def bounded_extract_links(s, p):
                async with semaphore:
                    return await self.extract_article_links(s, p)

            link_tasks = [
                bounded_extract_links(session, i) for i in range(1, page_to_parse + 1)
            ]
            pages_article_urls = await asyncio.gather(*link_tasks)

            all_article_urls = [
                url for page_urls in pages_article_urls for url in page_urls
            ]

            # Извлекаем контент для каждой статьи
            async def bounded_extract_content(s, url):
                async with semaphore:
                    return await self.extract_article_content(s, url)

            content_tasks = [
                bounded_extract_content(session, url) for url in all_article_urls
            ]
            results = await asyncio.gather(*content_tasks)
            articles_data = [article for article in results if article is not None]

        return articles_data


# Дочерний класс для сайта sibac.info
class SibacParser(BaseParser):
    def __init__(self, max_concurrent_requests=3):
        super().__init__(
            base_url="https://sibac.info",
            start_url="https://sibac.info/arhive-article",
            max_concurrent_requests=max_concurrent_requests,
        )

    async def extract_article_links(self, session, page_num):
        """Переопределённый метод для парсинга sibac.info."""
        url = f"{self.START_URL}?page={page_num}"
        html = await self.fetch_html(session, url)
        soup = BeautifulSoup(html, "html.parser")
        return [
            self.BASE_URL + a_tag.get("href")
            for a_tag in soup.select("#archive-wrapp div.item a")
            if a_tag.get("href")
        ]

    async def extract_article_content(self, session, article_url):
        """Переопределённый метод для парсинга контента sibac.info."""
        html = await self.fetch_html(session, article_url)
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else "Без заголовка"
        content_block = soup.find("div", class_="field-items")

        if not content_block:
            return None

        full_text_content = content_block.get_text(separator="\n\n", strip=True)

        return {
            "title": title_text,
            "content": full_text_content,
            "source_url": article_url,
        }


# Дочерний класс для сайта rscf.ru
class RscfParser(BaseParser):
    def __init__(self, max_concurrent_requests=3):
        super().__init__(
            base_url="https://rscf.ru",
            start_url="https://rscf.ru/news/release/",
            max_concurrent_requests=max_concurrent_requests,
        )

    async def extract_article_links(self, session, page_num):
        """Переопределённый метод для парсинга rscf.ru."""
        url = f"{self.START_URL}?PAGEN_2={page_num}"
        html = await self.fetch_html(session, url)
        soup = BeautifulSoup(html, "html.parser")
        return [
            self.BASE_URL + a_tag.get("href")
            for a_tag in soup.select(".news-content .news-title")
            if a_tag.get("href")
        ]

    async def extract_article_content(self, session, article_url):
        """Переопределённый метод для парсинга контента rscf.ru."""
        html = await self.fetch_html(session, article_url)
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("h1")
        title_text = title.get_text(strip=True) if title else "Без заголовка"
        content_block = soup.find("div", class_="b-news-detail-content") or soup.find(
            "article"
        )

        if not content_block:
            return None

        full_text_content = content_block.get_text(separator="\n\n", strip=True)

        return {
            "title": title_text,
            "content": full_text_content,
            "source_url": article_url,
        }


async def parsing_all():
    # Создаём экземпляры парсеров
    sibac_parser = SibacParser(max_concurrent_requests=3)
    rscf_parser = RscfParser(max_concurrent_requests=3)

    try:
        print("Начинаем парсинг sibac.info...")
        sibac_articles = await sibac_parser.parse(page_to_parse=2)
        print(
            f"Парсинг sibac.info завершён. Найдено {len(sibac_articles)} статей. {type(sibac_articles)}"
        )
    except Exception as sibac_e:
        print(f"Ошибка во время парсинга научных статей:{sibac_e}")

    try:
        print("\nНачинаем парсинг rscf.ru...")
        rscf_articles = await rscf_parser.parse(page_to_parse=2)
        print(
            f"Парсинг rscf.ru завершён. Найдено {len(rscf_articles)} статей. {type(rscf_articles)}"
        )
    except Exception as rscf_e:
        print(f"Ошибка во время парсинга сайта РНФ:{rscf_e}")
    all_data = sibac_articles + rscf_articles
    return all_data


if __name__ == "__main__":
    print(asyncio.run(parsing_all()))
