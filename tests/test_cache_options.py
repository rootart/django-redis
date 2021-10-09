import copy

import pytest
from django.core.cache import caches
from redis.exceptions import ConnectionError

from django_redis.client import ShardClient


def make_key(key, prefix, version):
    return f"{prefix}#{version}#{key}"


def reverse_key(key):
    return key.split("#", 2)[2]


@pytest.fixture
def ignore_exceptions_cache(settings):
    caches_setting = copy.deepcopy(settings.CACHES)
    caches_setting["doesnotexist"]["OPTIONS"]["IGNORE_EXCEPTIONS"] = True
    settings.CACHES = caches_setting
    settings.DJANGO_REDIS_IGNORE_EXCEPTIONS = True
    cache = caches["doesnotexist"]
    yield cache


def test_get_django_omit_exceptions_many_returns_default_arg(ignore_exceptions_cache):
    assert ignore_exceptions_cache._ignore_exceptions is True
    assert ignore_exceptions_cache.get_many(["key1", "key2", "key3"]) == {}


def test_get_django_omit_exceptions(ignore_exceptions_cache):
    assert ignore_exceptions_cache._ignore_exceptions is True
    assert ignore_exceptions_cache.get("key") is None
    assert ignore_exceptions_cache.get("key", "default") == "default"
    assert ignore_exceptions_cache.get("key", default="default") == "default"


def test_get_django_omit_exceptions_priority_1(settings):
    caches_setting = copy.deepcopy(settings.CACHES)
    caches_setting["doesnotexist"]["OPTIONS"]["IGNORE_EXCEPTIONS"] = True
    settings.CACHES = caches_setting
    settings.DJANGO_REDIS_IGNORE_EXCEPTIONS = False
    cache = caches["doesnotexist"]
    assert cache._ignore_exceptions is True
    assert cache.get("key") is None


def test_get_django_omit_exceptions_priority_2(settings):
    caches_setting = copy.deepcopy(settings.CACHES)
    caches_setting["doesnotexist"]["OPTIONS"]["IGNORE_EXCEPTIONS"] = False
    settings.CACHES = caches_setting
    settings.DJANGO_REDIS_IGNORE_EXCEPTIONS = True
    cache = caches["doesnotexist"]
    assert cache._ignore_exceptions is False
    with pytest.raises(ConnectionError):
        cache.get("key")


@pytest.fixture
def key_prefix_cache(settings):
    caches_setting = copy.deepcopy(settings.CACHES)
    caches_setting["default"]["KEY_PREFIX"] = "*"
    settings.CACHES = caches_setting
    cache = caches["default"]
    yield cache
    cache.clear()


@pytest.fixture
def with_prefix_cache():
    with_prefix = caches["with_prefix"]
    yield with_prefix
    with_prefix.clear()


class TestDjangoRedisCacheEscapePrefix:
    def test_delete_pattern(self, key_prefix_cache, with_prefix_cache):
        key_prefix_cache.set("a", "1")
        with_prefix_cache.set("b", "2")
        key_prefix_cache.delete_pattern("*")
        assert key_prefix_cache.has_key("a") is False
        assert with_prefix_cache.get("b") == "2"

    def test_iter_keys(self, key_prefix_cache, with_prefix_cache):
        if isinstance(key_prefix_cache.client, ShardClient):
            pytest.skip("ShardClient doesn't support iter_keys")

        key_prefix_cache.set("a", "1")
        with_prefix_cache.set("b", "2")
        assert list(key_prefix_cache.iter_keys("*")) == ["a"]

    def test_keys(self, key_prefix_cache, with_prefix_cache):
        key_prefix_cache.set("a", "1")
        with_prefix_cache.set("b", "2")
        keys = key_prefix_cache.keys("*")
        assert "a" in keys
        assert "b" not in keys


def test_custom_key_function(settings):
    caches_setting = copy.deepcopy(settings.CACHES)
    caches_setting["default"]["KEY_FUNCTION"] = "test_cache_options.make_key"
    caches_setting["default"]["REVERSE_KEY_FUNCTION"] = "test_cache_options.reverse_key"
    settings.CACHES = caches_setting
    cache = caches["default"]

    if isinstance(cache.client, ShardClient):
        pytest.skip("ShardClient doesn't support get_client")

    for key in ["foo-aa", "foo-ab", "foo-bb", "foo-bc"]:
        cache.set(key, "foo")

    res = cache.delete_pattern("*foo-a*")
    assert bool(res) is True

    keys = cache.keys("foo*")
    assert set(keys) == {"foo-bb", "foo-bc"}
    # ensure our custom function was actually called
    assert {k.decode() for k in cache.client.get_client(write=False).keys("*")} == (
        {"#1#foo-bc", "#1#foo-bb"}
    )
    cache.clear()
