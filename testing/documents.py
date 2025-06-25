from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry
from .models import News


@registry.register_document
class NewsDocument(Document):
    # Поля, которые вы хотите индексировать
    title = fields.TextField(
        attr="title",
        fields={
            "raw": fields.KeywordField(),
            "suggest": fields.CompletionField(),  # Для автодополнения (опционально)
        },
    )
    content = fields.TextField(attr="content")
    time_create = fields.DateField(attr="time_create")
    time_update = fields.DateField(attr="time_update")
    user = fields.IntegerField(attr="user.id")

    class Index:
        name = "news"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}

    class Django:
        model = News
        fields = ["id"]
