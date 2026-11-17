"""Utilidades de test: un fetch falso que responde según la ruta de la URL."""
from urllib.parse import parse_qs, urlparse


class FakeFetch:
    def __init__(self, routes):
        self.routes = routes   # ruta -> dato JSON | Exception | callable(query_dict) -> dato
        self.calls = []        # (url, headers)

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        parsed = urlparse(url)
        value = self.routes[parsed.path]
        if callable(value):
            value = value({k: v[0] for k, v in parse_qs(parsed.query).items()})
        if isinstance(value, Exception):
            raise value
        return value
