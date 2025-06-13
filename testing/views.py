from rest_framework import generics, viewsets, status
from django.shortcuts import render
from .models import News
from .serializers import NewsSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from django.forms import model_to_dict
from rest_framework.permissions import IsAuthenticated


class NewsViewSet(viewsets.ModelViewSet):
    queryset = News.objects.all()
    serializer_class = NewsSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


# class NewsAPIList(generics.ListCreateAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer


# class NewsAPIUpdate(generics.UpdateAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer


# class NewsAPIDetailNView(generics.RetrieveUpdateDestroyAPIView):
#     queryset = News.objects.all()
#     serializer_class = NewsSerializer
