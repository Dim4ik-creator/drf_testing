from rest_framework import generics, viewsets, status
from django.shortcuts import render
from .models import News
from .serializers import NewsSerializer
from .documents import NewsDocument
from rest_framework.views import APIView
from rest_framework.response import Response
from django.forms import model_to_dict
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters
from elasticsearch_dsl import Q

class NewsListView(generics.ListCreateAPIView):
    serializer_class = NewsSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return News.objects.filter(author=self.request.user).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        search_query = request.query_params.get('search', None)
        user = request.user # Получаем текущего пользователя

        if search_query:
            # 1. Выполняем поиск в Elasticsearch
            s = NewsDocument.search().query(
                Q('multi_match', query=search_query, fields=['title', 'content'])
            ).filter('term', user=user.id) # Важно: фильтруем по ID текущего пользователя

            # 2. Настраиваем пагинацию для Elasticsearch
            page_size = self.pagination_class.page_size if hasattr(self, 'pagination_class') and self.pagination_class else 10
            page_number = int(request.query_params.get('page', 1))
            start = (page_number - 1) * page_size
            end = start + page_size
            s = s[start:end]

            response_es = s.execute() # Выполняем запрос к ES
            
            # 3. Извлекаем ID статей из результатов Elasticsearch
            #    Elasticsearch возвращает id как строку, преобразуем в int
            article_ids_from_es = [int(hit.meta.id) for hit in response_es.hits]
            
            # 4. Загружаем полные объекты Article из PostgreSQL по полученным ID
            #    Мы делаем это, чтобы использовать стандартный Django ORM и сериализаторы,
            #    которые ожидают экземпляры моделей, а не чистые словари из ES.
            #    Важно сохранить порядок, возвращенный Elasticsearch,
            #    т.к. ES ранжирует результаты по релевантности.
            articles_from_db = News.objects.filter(id__in=article_ids_from_es, author=user)
            
            # Создаем словарь для быстрого доступа по ID и сохраняем порядок
            article_map = {article.id: article for article in articles_from_db}
            ordered_articles = [article_map[article_id] for article_id in article_ids_from_es if article_id in article_map]

            # 5. Сериализуем полученные Django-объекты
            serializer = self.get_serializer(ordered_articles, many=True)
            
            # 6. Формируем ответ, имитирующий стандартный DRF-пагинатор
            #    (или используем PageNumberPagination, если она правильно настроена)
            #    Для этого нам нужно вручную рассчитать next/previous URL
            total_hits = response_es.hits.total.value
            
            next_url = None
            previous_url = None
            
            # Логика для next/previous URL
            if total_hits > end:
                next_page_num = page_number + 1
                next_url = request.build_absolute_uri(
                    f"{self.request.path}?page={next_page_num}&search={search_query}"
                )
            if start > 0:
                prev_page_num = page_number - 1
                previous_url = request.build_absolute_uri(
                    f"{self.request.path}?page={prev_page_num}&search={search_query}"
                )

            return Response({
                'count': total_hits,
                'next': next_url,
                'previous': previous_url,
                'results': serializer.data
            })
        else:
            # Если нет поискового запроса, используем обычный DRF queryset и пагинацию
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset) # self.paginate_queryset ожидает queryset, а не список
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(serializer.data)


class NewsAPIListPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 1000


class NewsViewSet(viewsets.ModelViewSet):
    queryset = News.objects.all()
    serializer_class = NewsSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NewsAPIListPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "content"]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
