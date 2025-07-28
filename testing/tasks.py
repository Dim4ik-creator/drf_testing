from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from pydub import AudioSegment

from .parsing_site import parse_articles
from .models import News

import whisperx
import logging
import asyncio
import torch
import tempfile
import os
logger = logging.getLogger(__name__)


@shared_task()
def CreatingNews(page_to_parse):
    try:
        logger.info("[Celery] Запуск задачи CreatingNews...")

        # Вызываем асинхронную функцию напрямую с await
        try:
            parsed_articles = asyncio.run(parse_articles(page_to_parse))
        except asyncio.TimeoutError as e:
            logger.warning(
                f"[Celery] Таймаут во время парсинга: {e}. Повторная попытка..."
            )
        except Exception as parse_e:
            logger.exception(
                f"[Celery] Ошибка во время парсинга в parse_articles(): {parse_e}"
            )
            # Возвращаем ошибку, если парсинг не удался
            return {"status": "error", "details": f"Ошибка парсинга: {str(parse_e)}"}

        if not parsed_articles:
            logger.warning("[Celery] Парсер вернул пустой список.")
            return {
                "status": "empty",
                "message": "Нет данных",
            }

        user_model = get_user_model()
        author_user = user_model.objects.filter(username="admin").first()
        if not author_user:
            logger.error("[Celery] Пользователь 'admin' не найден.")
            return {"error": "admin user not found"}

        NewsForDB = []
        existing_titles = set(News.objects.values_list("title", flat=True))

        for article in parsed_articles:
            title = article.get("title")
            content = article.get("content")
            if title and content and title not in existing_titles:
                NewsForDB.append(News(title=title, content=content, user=author_user))

        if NewsForDB:
            with transaction.atomic():
                News.objects.bulk_create(NewsForDB, batch_size=50)
            logger.info(f"[Celery] Добавлено статей: {len(NewsForDB)}")
            return {
                "status": "success",
                "added": len(NewsForDB),
            }
        else:
            logger.info("[Celery] Нет новых статей для добавления.")
            return {"status": "no new articles"}

    except Exception as e:
        logger.exception(f"[Celery ERROR] Общая ошибка в задаче CreatingNews: {e}")
        return {
            "status": "error",
            "details": str(e),
        }


WHISPER_MODEL_NAME = "base"
WHISPER_BATCH_SIZE = 8
WHISPER_COMPUTE_TYPE = "float64"
WHISPER_DEVICE = "cpu"

WHISPER_MODEL = None
WHIPSER_ALIGN_MODEL = None
WHIPSER_METADATA = None

try:
    logger.info(f"Загрузка модели WhisperX '{WHISPER_MODEL_NAME}' на устройстве: {WHISPER_DEVICE}...")
    WHISPER_MODEL = whisperx.load_model(WHISPER_MODEL_NAME, WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    logger.info("Модель WhisperX успешно загружена.")

    # Загрузка модели для выравнивания (нужна для получения временных меток слов)
    logger.info(f"Загрузка модели для выравнивания (lang=ru)...")
    WHISPER_ALIGN_MODEL, WHISPER_METADATA = whisperx.load_align_model(language_code="ru", device=WHISPER_DEVICE)
    logger.info("Модель для выравнивания успешно загружена.")
except Exception as e:
    logger.error(f"Ошибка загрузки моделей WhisperX: {e}")
    WHISPER_MODEL = None
    WHISPER_ALIGN_MODEL = None
    WHISPER_METADATA = None


@shared_task()
def transcribe_audio(audio_file_path):
    """
    Celery-задача для распознавания речи с помощью WhisperX.
    Принимает путь к аудиофайлу, распознает его и возвращает текст.
    """
    if WHISPER_MODEL is None or WHISPER_ALIGN_MODEL is None:
        logger.error("Модели WhisperX не загружены. Невозможно выполнить распознавание.")
        return {"status": "error", "text": "Ошибка: Модели распознавания речи недоступны."}

    logger.info(f"Начато распознавание аудиофайла: {audio_file_path}")

    try:
        # 1. Загрузка аудиофайла и конвертация в нужный формат (если необходимо)
        audio_segment = AudioSegment.from_file(audio_file_path)
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)

        with tempfile.NamedTemporaryFile(delete=False,suffix=".wav") as temp_wav_file:
            audio_segment.export(temp_wav_file.name, format="wav")
            audio_np = whisperx.load_audio(temp_wav_file.name)

        # 2. Распознание речи
        result = WHISPER_MODEL.transcribe(audio_np, batch_size= WHISPER_BATCH_SIZE)

        # 3. Выравнивание временных меток (для получения временных меток слов)
        aligned_result = whisperx.align(result["segments"], WHISPER_ALIGN_MODEL, WHISPER_METADATA, audio_np, WHISPER_DEVICE, return_char_alignments=False)
        transcribed_text = ""
        for segment in aligned_result["segments"]:
            transcribed_text += segment.get("text", "") + " "
        
        transcribed_text = transcribed_text.strip() # Удаляем лишние пробелы в начале/конце

        logger.info(f"Распознанный текст: {transcribed_text}")
        return {"status": "success", "text": transcribed_text}


    except Exception as e:
        logger.exception(f"Ошибка при распознавании аудиофайла {audio_file_path}: {e}")
    finally:
        # Очищаем временные файлы после обработки
        if os.path.exists(audio_file_path):
            os.remove(audio_file_path)
            logger.info(f"Временный входной файл удален: {audio_file_path}")
        if 'temp_wav_file' in locals() and os.path.exists(temp_wav_file.name):
            os.remove(temp_wav_file.name)
            logger.info(f"Временный WAV файл удален: {temp_wav_file.name}")
