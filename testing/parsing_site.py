import asyncio
import ssl
import aiohttp
from bs4 import BeautifulSoup
from aiohttp import ClientTimeout


BASE_URL = "https://rscf.ru"
START_URL = f"{BASE_URL}/news/release/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
MAX_CONCURRENT_REQUESTS = 3


async def fetch_html(session, url):
    timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
    async with session.get(url, headers=HEADERS, timeout=timeout) as response:
        response.raise_for_status()
        return await response.text()


async def extract_article_links(session, page_num):
    """
    Извлекает ссылки на статьи с указанной страницы новостей.
    """
    url = f"{START_URL}?PAGEN_2={page_num}"
    html = await fetch_html(session, url)
    soup = BeautifulSoup(html, "html.parser")
    # Ищем все ссылки на статьи в блоках .news-content с классом .news-title
    return [
        BASE_URL + a_tag.get("href")
        for a_tag in soup.select(".news-content .news-title")
        if a_tag.get("href")
    ]


async def extract_article_content(session, article_url):
    """
    Извлекает заголовок и текстовое содержимое статьи по ее URL.
    Изображения игнорируются.
    """
    html = await fetch_html(session, article_url)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.find("h1")
    title_text = title.get_text(strip=True) if title else "Без заголовка"

    # Ищем основной блок контента статьи
    content_block = soup.find("div", class_="b-news-detail-content") or soup.find(
        "article"
    )
    if not content_block:
        return None  # Если блок контента не найден, возвращаем None

    # Извлекаем весь текст из найденного блока контента
    full_text_content = content_block.get_text(separator="\n\n", strip=True)

    return {
        "title": title_text,
        "content": full_text_content,
        "source_url": article_url
    }


async def parse_articles(page_to_parse):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
    connector = aiohttp.TCPConnector(ssl=ssl_context, limit=10)

    # Это ограничит количество одновременно выполняющихся задач
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Получаем все ссылки на статьи со всех страниц
        # Обертываем вызовы extract_article_links в async with semaphore:
        async def bounded_extract_article_links(s, p):
            async with semaphore:
                return await extract_article_links(s, p)

        link_tasks = [
            bounded_extract_article_links(session, i)
            for i in range(1, page_to_parse + 1)
        ]
        pages_article_urls = await asyncio.gather(*link_tasks)

        all_article_urls = [
            url for page_urls in pages_article_urls for url in page_urls
        ]

        # Извлекаем контент для каждой статьи
        # Обертываем вызовы extract_article_content в async with semaphore:
        async def bounded_extract_article_content(s, url):
            async with semaphore:
                return await extract_article_content(s, url)

        content_tasks = [
            bounded_extract_article_content(session, url) for url in all_article_urls
        ]
        results = await asyncio.gather(*content_tasks)

        articles_data = [article for article in results if article is not None]

    return articles_data
