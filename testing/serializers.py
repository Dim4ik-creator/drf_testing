from rest_framework import serializers
from .models import News


class NewsSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=50)
    content = serializers.CharField()
    time_create = serializers.DateTimeField(read_only=True)
    time_update = serializers.DateTimeField(read_only=True)
    is_published = serializers.BooleanField(default=True)
