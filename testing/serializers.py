from rest_framework import serializers
from .models import News
from django.contrib.auth import get_user_model

User = get_user_model()


class NewsSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(max_length=255)
    source_url = serializers.URLField(max_length=500, allow_null=True, required=False)
    content = serializers.CharField()
    time_create = serializers.DateTimeField(read_only=True)
    time_update = serializers.DateTimeField(read_only=True)
    is_published = serializers.BooleanField(default=True)
    user_username = serializers.ReadOnlyField(source="user.username")
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def create(self, validated_data):
        user_instance = validated_data.pop("user", None)

        if user_instance:
            return News.objects.create(user=user_instance, **validated_data)
        else:
            raise serializers.ValidationError(
                "Пользователь обязателен для создания новости."
            )

    def update(self, instance, validated_data):
        instance.title = validated_data.get("title", instance.title)
        instance.content = validated_data.get("content", instance.content)
        instance.source_url = validated_data.get("source_url", instance.source_url)
        # instance.time_update = validated_data.get("time_update", instance.time_update)
        instance.is_published = validated_data.get(
            "is_published", instance.is_published
        )
        instance.save()
        return instance
