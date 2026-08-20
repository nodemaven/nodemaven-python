"""Offline in full: no network, no credentials, no gateway.

These cases are the seed of the golden vectors the other language SDKs will run.
Anything asserted here is a statement about what a correct username is, not about
how this implementation happens to be written.
"""

from __future__ import annotations

import pytest

from nodemaven import ParamError, Proxy, available, load

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
        # 4417. Refusing is inference from the dialect rather than a measured
        # gateway reply - see the open question in CLAUDE.md - and it errs
        # towards a loud error over a silently different exit.
        with pytest.raises(ParamError, match="cannot carry"):
            Proxy(country="us", **CREDS).session("order-4417")


class TestTheShippedDefinition:
    def test_nodemaven_is_shipped_and_is_measured(self):
        assert "nodemaven" in available()
        assert load("nodemaven").is_measured

    def test_the_session_parameter_is_asked_for_rather_than_spelled(self):
        # Eleven call sites in the benchmark wrote "sid" directly. It is the name
        # this gateway happens to use, which is exactly why the literal survived.
        assert load("nodemaven").session_param == "sid"
