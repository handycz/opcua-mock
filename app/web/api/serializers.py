from rest_framework import serializers

from .models import DataImageItem


class DataImageItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataImageItem
        fields = ["name", "value"]


class DataImageSerializer(serializers.Serializer):
    data = DataImageItemSerializer(many=True)


    def update(self, instance, validated_data):
        pass

    def create(self, validated_data):
        l = list()
        for d in validated_data:
            l.append(
                DataImageItem(name=d["name"], value=d["value"])
            )

        return l
