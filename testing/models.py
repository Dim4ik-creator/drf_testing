from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    username = models.CharField("Логин", max_length=50, unique=True)
    email = models.EmailField(unique=True)

    # Добавьте эти строки для разрешения конфликтов
    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name=("groups"),
        blank=True,
        help_text=(
            "The groups this user belongs to. A user will get all permissions "
            "granted to each of their groups."
        ),
        related_name="testing_user_set",  # Уникальное related_name
        related_query_name="testing_user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name=("user permissions"),
        blank=True,
        help_text=("Specific permissions for this user."),
        related_name="testing_user_permissions_set",  # Уникальное related_name
        related_query_name="testing_user_permission",
    )

    def __str__(self):
        return self.username


class News(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True)
    time_create = models.DateTimeField(auto_now_add=True)
    time_update = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)
    user = models.ForeignKey(
        "User", verbose_name="Пользователь", on_delete=models.CASCADE
    )

    def __str__(self):
        return self.title
