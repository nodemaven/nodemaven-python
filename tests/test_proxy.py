"""Offline in full: no network, no credentials, no gateway.

These cases are the seed of the golden vectors the other language SDKs will run.
Anything asserted here is a statement about what a correct username is, not about
how this implementation happens to be written.
"""

from __future__ import annotations

import pytest

from nodemaven import ParamError, ProviderError, Proxy, available, load, load_file

CREDS = {"login": "acct", "password": "pw", "host": "gate.example.com", "port": 8080}


@pytest.fixture(autouse=True)
def no_gateway_env(monkeypatch):
    """A test that reached for real credentials would spend real traffic."""
    for name in ("LOGIN", "PASSWORD", "HOST", "PORT"):
        monkeypatch.delenv(f"NODEMAVEN_{name}", raising=False)


class TestTheUsername:
    def test_parameters_are_spelled_in_the_gateway_dialect(self):
        proxy = Proxy(country="us", filter="medium", sid="abc123", **CREDS)
        assert proxy.username == "acct-country-us-filter-medium-sid-abc123"

    def test_no_parameters_is_the_bare_login(self):
        assert Proxy(**CREDS).username == "acct"

    def test_order_follows_the_call(self):
        a = Proxy(country="us", sid="x", **CREDS).username
        b = Proxy(sid="x", country="us", **CREDS).username
        assert a == "acct-country-us-sid-x"
        assert b == "acct-sid-x-country-us"


class TestValidationTheGatewayCannotDo:
    def test_an_unknown_name_is_refused_before_anything_is_sent(self):
        # The gateway answers this with 200 and drops the setting, so the run
        # completes claiming a setting that was never applied.
        with pytest.raises(ParamError, match="does not know the parameter"):
            Proxy(contry="us", **CREDS)

    def test_an_empty_value_is_refused(self):
        # The gateway does not reply at all; the connection hangs about 20 s.
        with pytest.raises(ParamError, match="empty value"):
            Proxy(country="", **CREDS)

    def test_a_separator_inside_a_value_is_refused(self):
        # "us-east" would be parsed as country=us plus a parameter named east.
        with pytest.raises(ParamError, match="separate parameters"):
            Proxy(country="us-east", **CREDS)


class TestTheUrlIsSafeToHandToAClient:
    def test_credentials_are_percent_encoded(self):
        proxy = Proxy(country="us", **{**CREDS, "password": "pa/ss@1:2"})
        assert proxy.url() == (
            "http://acct-country-us:pa%2Fss%401%3A2@gate.example.com:8080"
        )

    def test_the_slash_is_encoded_and_that_is_the_whole_point(self):
        # quote() defaults to safe="/", which leaves the one character that ends
        # the authority. Unencoded, the host below becomes "pa".
        proxy = Proxy(**{**CREDS, "password": "pa/ss"})
        assert "%2F" in proxy.url()
        assert proxy.url().endswith("@gate.example.com:8080")

    def test_the_playwright_dict_is_not_encoded(self):
        # Playwright encodes the fields itself; encoding here too would send
        # pa%252Fss and fail authentication while blaming the credentials.
        proxy = Proxy(**{**CREDS, "password": "pa/ss"})
        assert proxy.playwright()["password"] == "pa/ss"
        assert proxy.playwright()["server"] == "http://gate.example.com:8080"


class TestTheReprCarriesNoSecret:
    def test_the_password_is_redacted(self):
        proxy = Proxy(country="us", **{**CREDS, "password": "hunter2"})
        assert "hunter2" not in repr(proxy)
        assert "***" in repr(proxy)

    def test_it_survives_being_put_in_a_container(self):
        # A container's __str__ calls __repr__ on its elements, which is how a
        # careful __str__ gets bypassed in a log line.
        proxy = Proxy(**{**CREDS, "password": "hunter2"})
        assert "hunter2" not in str([proxy])
        assert "hunter2" not in str({"p": proxy})

    def test_the_parameters_are_still_visible(self):
        assert "country='us'" in repr(Proxy(country="us", **CREDS))


class TestMovingIsANewIdentity:
    def test_replace_returns_a_new_object(self):
        first = Proxy(country="us", **CREDS)
        second = first.replace(country="de")
        assert first.username == "acct-country-us"
        assert second.username == "acct-country-de"
        assert first is not second

    def test_none_removes_a_parameter(self):
        proxy = Proxy(country="us", filter="medium", **CREDS).replace(filter=None)
        assert proxy.username == "acct-country-us"

    def test_session_uses_the_providers_own_name_for_it(self):
        proxy = Proxy(country="us", **CREDS).session("order4417")
        assert proxy.username == "acct-country-us-sid-order4417"

    def test_a_session_id_carrying_the_separator_is_refused(self):
        # `order-4417` is the obvious thing to use as a session key and this
        # dialect cannot carry it: separator and pair separator are both "-",
        # so `sid-order-4417` reads as sid=order followed by a parameter named
        # 4417. Measured 2026-08-20 rather than assumed: tunnels opened with
        # `sid-order<x>-4417` and with `sid-order<x>` landed on one exit across
        # four interleaved rounds each, while `sid-order<x>4417` held another
        # one - so the gateway cuts the tail off and every order id beginning
        # `order` would silently share a session.
        with pytest.raises(ParamError, match="cannot carry"):
            Proxy(country="us", **CREDS).session("order-4417")


class TestLegalValues:
    """The values half of the check, and the reason it is off by default.

    Names are validated against `known_params`; values are validated against
    `values`, which is empty for the shipped definition. The mechanism is here
    before the data is, because four language SDKs parse this schema and a key
    added later is four parsers rather than one data file.
    """

    def _provider(self, tmp_path, body):
        path = tmp_path / "p.toml"
        path.write_text(body, encoding="utf-8")
        return load_file(path)

    def test_an_unlisted_parameter_is_not_value_checked(self, tmp_path):
        # No entry means nobody established the legal values, so the caller is
        # left exactly where they were rather than being refused on a guess.
        provider = self._provider(tmp_path, """
label = "P"
known_params = ["country", "filter"]
values = { filter = ["medium", "high"] }
""")
        assert Proxy(provider=provider, country="whatever", **CREDS).username

    def test_a_value_outside_the_list_is_refused(self, tmp_path):
        provider = self._provider(tmp_path, """
label = "P"
known_params = ["filter"]
values = { filter = ["medium", "high"] }
""")
        with pytest.raises(ParamError, match="not a value"):
            Proxy(provider=provider, filter="medim", **CREDS)

    def test_a_value_inside_the_list_passes(self, tmp_path):
        provider = self._provider(tmp_path, """
label = "P"
known_params = ["filter"]
values = { filter = ["medium", "high"] }
""")
        assert Proxy(provider=provider, filter="high", **CREDS).username == "acct-filter-high"

    def test_values_for_an_unknown_parameter_are_refused_at_load(self, tmp_path):
        # Otherwise the entry looks like a working check and never runs.
        with pytest.raises(ProviderError, match="not in known_params"):
            self._provider(tmp_path, """
label = "P"
known_params = ["country"]
values = { filter = ["medium"] }
""")

    def test_an_empty_list_is_refused_at_load(self, tmp_path):
        # It would mean "every value of this parameter is illegal". Leaving the
        # entry out is how you say "not established".
        with pytest.raises(ProviderError, match="non-empty list"):
            self._provider(tmp_path, """
label = "P"
known_params = ["filter"]
values = { filter = [] }
""")


class TestTheShippedDefinition:
    def test_nodemaven_is_shipped_and_is_measured(self):
        assert "nodemaven" in available()
        assert load("nodemaven").is_measured

    def test_norotate_is_refused(self):
        # This test asserted the opposite between 2026-08-21 and 2026-08-26, on
        # the strength of `norotate` appearing in the vendor's proxy generator.
        # Probed from the VPS on 2026-08-26: with `norotate=true` and no `sid`
        # the gateway hands out 6 distinct exits in 6 draws, and with a fixed
        # `sid` and `ttl=1m` it hands out 3 distinct in 3 - the same as a
        # negative control carrying a name nobody has implemented. It is
        # answered 200 and dropped, which is the exact failure this package
        # exists to catch, so it belongs on the refused side.
        assert "norotate" not in load("nodemaven").known_params
        with pytest.raises(ParamError, match="norotate"):
            Proxy(country="any", norotate="true", **CREDS)

    def test_no_value_is_checked_for_the_shipped_definition_yet(self):
        # Guards the difference between "not established" and "nothing is
        # legal". If this ever fails, somebody filled in `values` - which is
        # wanted, but the vectors and the README claim have to move with it.
        provider = load("nodemaven")
        assert provider.values == {}
        assert provider.allowed("filter") is None

    def test_the_session_parameter_is_asked_for_rather_than_spelled(self):
        # Eleven call sites in the benchmark wrote "sid" directly. It is the name
        # this gateway happens to use, which is exactly why the literal survived.
        assert load("nodemaven").session_param == "sid"
