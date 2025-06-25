from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import News
from .documents import NewsDocument


@receiver(post_save, sender=News)
def update_document(sender, instance, **kwargs):
    instance.indexing()


@receiver(post_delete, sender=News)
def delete_document(sender, instance, **kwargs):
    instance.indexing_delete()
