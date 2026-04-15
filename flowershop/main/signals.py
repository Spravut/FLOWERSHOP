from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order
from .nats_events import publish_order_created, publish_order_status_changed


@receiver(post_save, sender=Order)
def order_post_save(sender, instance, created, **kwargs):
    if created:
        publish_order_created(instance)
    else:
        if instance.tracker.has_changed("status"):
            old_status = instance.tracker.previous("status")
            publish_order_status_changed(instance, old_status)
