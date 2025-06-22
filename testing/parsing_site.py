import asyncio
import ssl
import time
import aiohttp
from bs4 import BeautifulSoup

BASE_URL = "https://rscf.ru"
START_URL = f"{BASE_URL}/news/release/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
PAGES_TO_PARSE = 5


async def fetch_html(session, url):

    async with session.get(url, headers=HEADERS) as response:
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
    }


async def parse_articles():
    """
    Основная функция для парсинга статей.
    Собирает ссылки на статьи и затем извлекает их заголовки и содержимое.
    """
    start_time = time.perf_counter()
    articles_data = []

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        # Шаг 1: Получаем все ссылки на статьи со всех страниц
        link_tasks = [
            extract_article_links(session, i) for i in range(1, PAGES_TO_PARSE + 1)
        ]
        pages_article_urls = await asyncio.gather(*link_tasks)

        # Объединяем списки ссылок со всех страниц в один плоский список
        all_article_urls = [
            url for page_urls in pages_article_urls for url in page_urls
        ]

        # Шаг 2: Извлекаем контент для каждой статьи
        content_tasks = [
            extract_article_content(session, url) for url in all_article_urls
        ]
        results = await asyncio.gather(*content_tasks)

        # Фильтруем None (если какие-то статьи не удалось обработать)
        articles_data = [article for article in results if article is not None]

    end_time = time.perf_counter()
    print(f"\nОбщее время выполнения: {end_time - start_time:.2f} секунд")
    print(f"Всего обработано статей: {len(articles_data)}")

    return articles_data


def CreatingNews():

    parsed_articles = asyncio.run(parse_articles())
    NewsForDB = []

    from django.db import transaction
    from .models import News
    from django.contrib.auth import get_user_model

    existing_titles = set(News.objects.values_list("title", flat=True))

    User = get_user_model()
    author_user = User.objects.get(username='admin')
    for article in parsed_articles:
        title = article["title"]
        content = article["content"]
        if title not in existing_titles:
            NewsForDB.append(
                News(
                    title=title, 
                    content=content,
                    user=author_user
                    )
                )
    if NewsForDB:
        with transaction.atomic():
            News.objects.bulk_create(NewsForDB, batch_size=50)
    else:
        print("Нет новых статей для добавления.")