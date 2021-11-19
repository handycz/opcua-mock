from typing import Any

from django.db import models


# class DataImageItemManager(models.Manager):
#     def create_item(self, name: str, value: Any):
#         return self.create(name=name, value=value)


class DataImageItem(models.Model):
    name = models.CharField()
    value = models.CharField()

    objects = models.Manager()

    class Meta:
        ordering = ["name"]
        managed = False
