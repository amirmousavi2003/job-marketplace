from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Response: {count, next, previous, results}. Query: ?page=&page_size= (max 50)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50
