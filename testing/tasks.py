from celery import shared_task
import asyncio
from .parsing_site import parse_articles
from .models import News
from django.contrib.auth import get_user_model
from django.db import transaction
import logging


logger = logging.getLogger(__name__) # Добавьте этот импорт и инициализацию

@shared_task() # Добавим 'bind=True' и ретраи
def CreatingNews(): # <--- Теперь задача async def
    try:
        logger.info("[Celery] Запуск задачи CreatingNews...")

        # Вызываем асинхронную функцию напрямую с await
        try:
            parsed_articles = asyncio.run(parse_articles())
        except asyncio.TimeoutError as e:
            logger.warning(f"[Celery] Таймаут во время парсинга: {e}. Повторная попытка...")
        except Exception as parse_e:
            logger.exception(f"[Celery] Ошибка во время парсинга в parse_articles(): {parse_e}")
            # Возвращаем ошибку, если парсинг не удался
            return {"status": "error", "details": f"Ошибка парсинга: {str(parse_e)}"}


        if not parsed_articles:
            logger.warning("[Celery] Парсер вернул пустой список.")
            return {"status": "empty", "message": "Нет данных"} # Возвращаем сериализуемый результат

        user_model = get_user_model()
        author_user = user_model.objects.filter(username="admin").first()
        if not author_user:
            logger.error("[Celery] Пользователь 'admin' не найден.")
            return {"error": "admin user not found"} # Возвращаем сериализуемый результат

        NewsForDB = []
        existing_titles = set(News.objects.values_list("title", flat=True))

        for article in parsed_articles:
            # Используйте .get() для безопасного доступа к ключам словаря
            title = article.get("title")
            content = article.get("content")
            # Проверьте, что title и content существуют
            if title and content and title not in existing_titles:
                NewsForDB.append(News(title=title, content=content, user=author_user))
        
        if NewsForDB:
            with transaction.atomic():
                News.objects.bulk_create(NewsForDB, batch_size=50)
            logger.info(f"[Celery] Добавлено статей: {len(NewsForDB)}")
            return {"status": "success", "added": len(NewsForDB)} # Возвращаем сериализуемый результат
        else:
            logger.info("[Celery] Нет новых статей для добавления.")
            return {"status": "no new articles"} # <--- Добавляем явный возврат здесь!


    except Exception as e:
        logger.exception(f"[Celery ERROR] Общая ошибка в задаче CreatingNews: {e}")
        return {"status": "error", "details": str(e)} # Возвращаем сериализуемый результат
