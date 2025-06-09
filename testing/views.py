from rest_framework import generics
from django.shortcuts import render
from .models import News
from .serializers import NewsSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.forms import model_to_dict

# class NewsAPIView(generics.ListAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer


class NewsAPIView(APIView):
    def get(self, request):
        lst = News.objects.all()
        return Response({"posts": NewsSerializer(lst, many=True).data})

    def post(self, request):
        serilizer = NewsSerializer(data=request.data)
        serilizer.is_valid(raise_exception=True)
        post_new = News.objects.create(
            title=request.data["title"],
            content=request.data["content"],
        )
        return Response({"post": NewsSerializer(post_new).data})
