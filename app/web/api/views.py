from rest_framework import generics

from .models import DataImageItem
from .serializers import DataImageSerializer
from app.mockserver import server


class DataImageView(generics.ListAPIView):
    raw_data = server.get_data_image()
    queryset = DataImageItem.objects.bulk_create(
        [
            DataImageItem.objects.create(name=k, value=v) for k, v in raw_data.items()
        ]
    )

    serializer_class = DataImageSerializer
