from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions

from elasticsearch_dsl import Q

from .models import News
from .serializers import NewsSerializer
from .documents import NewsDocument
from .tasks import CreatingNews
import asyncio

class NewsAPIListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 1000


class ParseNewsAPIView(APIView):
    # permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        CreatingNews.delay()  # запускаем парсинг в фоне
        return Response(
            {"detail": "Задача парсинга запущена."}
        )


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
                        "multi_match",
                        query=search_query,
                        fields=[
                            "title",
                        ],
                        fuzziness="AUTO",  # Автоматическая нечеткость для опечаток
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
