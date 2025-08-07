from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth import get_user_model
from firebase_admin import auth as firebase_auth, credentials, initialize_app
from elasticsearch_dsl import Q, Search
from rest_framework_simplejwt.tokens import RefreshToken

import os
import tempfile

from .models import News
from .serializers import NewsSerializer
from .documents import NewsDocument
from .tasks import CreatingNews, transcribe_audio


class NewsAPIListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 1000


class NewsVoiseTranscribe(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [
        MultiPartParser,
        FormParser,
    ]  # Разрешает принимать FormData и файлы

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get(
            "audio_file"
        )  # 'audio_file' - это имя поля из FormData на фронтенде

        if not audio_file:
            return Response(
                {"detail": "Аудиофайл не предоставлен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Создаем временный файл для сохранения аудио
        # NamedTemporaryFile гарантирует уникальное имя и автоматическое удаление
        # после закрытия файла, но мы удалим его вручную в Celery-задаче.
        try:
            # Используем NamedTemporaryFile с суффиксом, чтобы сохранить расширение
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".webm"
            ) as temp_audio_file:
                for chunk in audio_file.chunks():
                    temp_audio_file.write(chunk)
                temp_audio_file_path = temp_audio_file.name

            # Запускаем Celery-задачу для распознавания
            task_result = transcribe_audio.delay(temp_audio_file_path)
            result = task_result.get(timeout=360)

            if result.get("status") == "success":
                return Response({"text": result.get("text")}, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"detail": result.get("text", "Ошибка распознавания речи.")},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except Exception as e:
            # Если возникла ошибка, убедимся, что временный файл удален
            if "temp_audio_file_path" in locals() and os.path.exists(
                temp_audio_file_path
            ):
                os.remove(temp_audio_file_path)
            return Response(
                {"detail": f"Ошибка обработки аудио: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ParseNewsAPIView(APIView):
    # permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        page_to_parse = 5
        CreatingNews.delay(page_to_parse)  # запускаем парсинг в фоне
        return Response({"detail": "Задача парсинга запущена."})


class NewsViewSet(viewsets.ModelViewSet):
    serializer_class = NewsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NewsAPIListPagination

    def get_queryset(self):
        return News.objects.filter(user=self.request.user).order_by("-time_create")

    def list(self, request, *args, **kwargs):
        search_query = request.query_params.get("search", None)
        user = request.user

        if search_query:
            # Выполняем поиск в Elasticsearch
            s = (
                NewsDocument.search()
                .query(
                    Q(
                        "bool",
                        should=[
                            Q(
                                "multi_match",
                                query=search_query,
                                fields=["title"],
                                fuzziness="AUTO",
                                type="most_fields",
                            ),
                            Q(
                                "match_phrase_prefix",
                                title={"query": search_query, "max_expansions": 50},
                            ),
                        ],
                        minimum_should_match=1,
                    )
                )
                .filter("term", user=user.id)
            )

            # Настраиваем пагинацию для результатов Elasticsearch
            page_size = self.pagination_class.page_size
            page_number = int(request.query_params.get("page", 1))
            start = (page_number - 1) * page_size
            end = start + page_size
            s = s[start:end]

            response_es = s.execute()

            # Извлекаем ID статей из результатов Elasticsearch
            article_ids_from_es = [int(hit.meta.id) for hit in response_es.hits]

            # Загружаем полные объекты News из PostgreSQL по полученным ID,
            # и дополнительно фильтруем по текущему автору для безопасности
            articles_from_db = News.objects.filter(
                id__in=article_ids_from_es, user=user
            )

            # Создаем словарь для быстрого доступа по ID и сохраняем порядок
            article_map = {article.id: article for article in articles_from_db}
            ordered_articles = [
                article_map[article_id]
                for article_id in article_ids_from_es
                if article_id in article_map
            ]

            serializer = self.get_serializer(ordered_articles, many=True)

            total_hits = response_es.hits.total.value

            next_url = None
            previous_url = None

            current_path = request.build_absolute_uri(request.path)
            current_path_base = current_path.split("?")[0]

            def build_paginated_url(page_num, search_q):
                params = f"page={page_num}"
                if search_q:
                    params += f"&search={search_q}"
                return f"{current_path_base}?{params}"

            if total_hits > end:
                next_page_num = page_number + 1
                next_url = build_paginated_url(next_page_num, search_query)
            if start > 0:
                prev_page_num = page_number - 1
                previous_url = build_paginated_url(prev_page_num, search_query)

            return Response(
                {
                    "count": total_hits,
                    "next": next_url,
                    "previous": previous_url,
                    "results": serializer.data,
                }
            )
        else:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


cred = credentials.Certificate(
    "C:\\Users\\Дмитрий\\VS\\rest_training\\drf\\testing\\drf-aouth-firebase-adminsdk-fbsvc-b4c5ed1091.json"
)
if not cred:
    print(
        f"Файл serviceAccountKey.json не найден по пути: {cred}. Firebase Admin SDK не будет инициализирован."
    )

    try:
        initialize_app(cred)
        print("Firebase Admin SDK успешно инициализирован в AppConfig.")
    except Exception as e:
        print(f"Ошибка инициализации Firebase Admin SDK в AppConfig: {e}")
else:
    print("Firebase Admin SDK уже инициализирован. Пропускаем повторную инициализацию.")

User = get_user_model()
initialize_app(cred)


class FirebaseLoginView(APIView):
    # Эти классы могут быть необходимы, если вы хотите, чтобы этот View был доступен
    # без предварительной аутентификации.
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        """
        Верифицирует Firebase ID Token и возвращает JWT-токены.
        """
        id_token = request.data.get("idToken")

        if not id_token:
            print("Получен запрос на FirebaseLoginView без ID Token.")
            return Response(
                {"error": "ID Token is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Верификация токена Firebase
            # Firebase Admin SDK должен быть инициализирован до этого вызова
            decoded_token = firebase_auth.verify_id_token(id_token)
            uid = decoded_token.get("uid")
            email = decoded_token.get("email")

            print(
                f"Firebase ID Token успешно верифицирован для UID: {uid}, Email: {email}"
            )

            # Проверка, существует ли пользователь в Django
            user, created = User.objects.get_or_create(email=email)
            if created:
                # Если пользователь новый, установите ему имя и другие поля
                user.username = (
                    uid  # Можно использовать email или сгенерировать уникальное имя
                )
                user.save()
                print(
                    f"Новый пользователь Django создан: {user.username} ({user.email})"
                )
            else:
                print(
                    f"Существующий пользователь Django найден: {user.username} ({user.email})"
                )

            # Генерация JWT-токенов
            refresh = RefreshToken.for_user(user)
            print(f"JWT-токены сгенерированы для пользователя: {user.username}")

            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }
            )

        except firebase_auth.InvalidIdTokenError as e:
            # Эта ошибка возникает, если токен недействителен (истек, подделан и т.д.)
            print(f"Ошибка верификации Firebase ID Token: {e}")
            return Response(
                {"error": f"Invalid Firebase ID token: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,  # Или HTTP_401_UNAUTHORIZED, в зависимости от политики
            )
        except Exception as e:
            # Ловим любые другие неожиданные ошибки
            print(
                "Непредвиденная ошибка в FirebaseLoginView:"
            )  # Используем exception для вывода полного traceback
            return Response(
                {"error": "Непредвиденная ошибка сервера."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
