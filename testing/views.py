from rest_framework import generics
from django.shortcuts import render
from .models import News
from .serializers import NewsSerializer


class NewsAPIView(generics.ListAPIView):
    queryset = News.objects.all()
    serializer_class = NewsSerializer
