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
            "suggest": fields.CompletionField(analyzer="autocomplete_analyzer"),
        },
        analyzer="russian_analyzer",
    )
    content = fields.TextField(attr="content", analyzer="russian_analyzer")
    time_create = fields.DateField(attr="time_create")
    time_update = fields.DateField(attr="time_update")
    user = fields.IntegerField(attr="user.id")

    class Index:
        name = "news"
        settings = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "filter": {
                    "russian_stemmer": {"type": "snowball", "language": "Russian"},
                    "autocomplete_filter": {
                        "type": "edge_ngram",
                        "min_gram": 2,
                        "max_gram": 20,
                    },
                },
                "analyzer": {
                    "russian_analyzer": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "russian_stemmer"],
                    },
                    "autocomplete_analyzer": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "autocomplete_filter"],
                    },
                },
            },
        }

    class Django:
        model = News
        fields = ["id"]
