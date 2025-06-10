from rest_framework import generics, viewsets
from django.shortcuts import render
from .models import News
from .serializers import NewsSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.forms import model_to_dict


class NewsViewSet(viewsets.ModelViewSet):
    queryset = News.objects.all()
    serializer_class = NewsSerializer


# class NewsAPIList(generics.ListCreateAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer


# class NewsAPIUpdate(generics.UpdateAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer


# class NewsAPIDetailNView(generics.RetrieveUpdateDestroyAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer
