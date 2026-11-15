from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from .models import City, Province
from .serializers import CitySerializer, ProvinceSerializer


class _ReferenceList(ListAPIView):
    """Small reference data: public, not paginated."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    pagination_class = None
    filter_backends: list = []


class ProvinceListView(_ReferenceList):
    serializer_class = ProvinceSerializer
    queryset = Province.objects.all()


class CityListView(_ReferenceList):
    """GET /locations/cities/?province=<id>"""

    serializer_class = CitySerializer

    def get_queryset(self):
        qs = City.objects.all()
        province = self.request.query_params.get("province")
        if province and province.isdigit():
            qs = qs.filter(province_id=int(province))
        return qs
