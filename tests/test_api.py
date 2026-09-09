"""The account API, driven through the transport seam. No socket, no key.

Every case here supplies its own ``transport=``, which is the reason that seam
exists: the whole error mapping, the whole paging loop and every response shape
this module *assumes* can be exercised without an account and without a network.
The shapes are the interesting part - the module docstring in ``nodemaven.api``
records that the paginated envelope is inferred from the vendor's own query
parameter names and has never been seen from this machine, so the cases below
include the shapes it might turn out to be instead.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from nodemaven import (
    ApiError,
    AuthError,
    Client,
    CredentialsError,
    NotFoundError,
    Page,
    Proxy,
    RateLimitError,
)
from nodemaven.api import API_ROOT, DEFAULT_BASE_URL, DEFAULT_PAGE_SIZE


@pytest.fixture(autouse=True)
def no_api_env(monkeypatch):
    """A developer's own ``.env`` must not reach into the suite.

    Both names are the vendor's, so they are plausibly already set on this
    machine - and a test that silently picked up a real key would be a test that
    passes here and fails in CI, or worse, one that spends a real call.
    """
    monkeypatch.delenv("NODEMAVEN_APIKEY", raising=False)
    monkeypatch.delenv("NODEMAVEN_BASE_URL", raising=False)


class Fake:
    """A scripted transport that records what it was handed.

    ``responses`` is a list of ``(status, body)``, consumed in order; the last
    one repeats, so a paging test does not have to count its own requests. A
    body that is not ``bytes`` is JSON-encoded, because most cases care about the
    shape rather than the encoding.
    """

    def __init__(self, *responses):
        self.responses = list(responses) or [(200, {})]
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "body": json.loads(body.decode()) if body else None,
            }
        )
        status, payload = (
            self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        )
        if isinstance(payload, bytes):
            return status, payload
        return status, json.dumps(payload).encode()

    @property
    def url(self):
        return self.calls[-1]["url"]

    @property
    def headers(self):
        return self.calls[-1]["headers"]


def client(*responses, **kwargs):
    fake = Fake(*responses)
    return Client(api_key="k3y", transport=fake, **kwargs), fake


class TestCredentialsAndTheirSecrecy:
    def test_no_key_anywhere_is_refused_at_construction(self):
        with pytest.raises(CredentialsError, match="NODEMAVEN_APIKEY"):
            Client()

    def test_the_message_distinguishes_the_two_secrets(self):
        # There are two credentials on this account and they come from different
        # places. A program that treats them as one tells you to fix the key
        # when the password is wrong.
        with pytest.raises(CredentialsError, match="not the proxy password"):
            Client()

    def test_the_key_is_read_from_the_vendors_own_variable(self, monkeypatch):
        # Their name and not one of ours, so a `.env` written for their client
        # works here unchanged. Two .env files that disagree is worse than a
        # name we did not choose.
        monkeypatch.setenv("NODEMAVEN_APIKEY", "from-the-environment")
        fake = Fake((200, {}))
        Client(transport=fake).me()
        assert fake.headers["Authorization"] == "x-api-key from-the-environment"

    def test_the_repr_never_carries_the_key(self):
        api, _ = client()
        assert "k3y" not in repr(api)
        assert "***" in repr(api)

    def test_the_key_travels_in_a_header_and_never_in_a_url(self):
        api, fake = client((200, {}))
        api.countries(country__code="us")
        assert "k3y" not in fake.url
        assert fake.headers["Authorization"] == "x-api-key k3y"

    def test_the_header_form_is_the_unusual_one_the_server_wants(self):
        # `Authorization: x-api-key <key>`, not an `X-API-Key` header. The
        # conventional spelling would be answered 401, which reads as a bad key
        # and sends the caller to regenerate a key that was fine.
        api, fake = client((200, {}))
        api.me()
        assert "X-API-Key" not in fake.headers
        assert fake.headers["Authorization"].startswith("x-api-key ")


class TestTheAccount:
    def test_me_hits_the_documented_path(self):
        api, fake = client((200, {"data": 123}))
        api.me()
        assert fake.url == f"{DEFAULT_BASE_URL}{API_ROOT}/users/me"

    def test_me_returns_the_servers_own_object_unmodelled(self):
        # Deliberately not a dataclass, and the live response is the argument
        # for it. Measured 2026-09-08, `users/me` answers the six fields below:
        # traffic left is `data` and not `traffic_left`, and `is_traffic_frozen`
        # is a string and not a bool. A dataclass written the day before from
        # the vendor's client would have got both wrong - the first as an
        # AttributeError on a working answer, the second as a value that is
        # truthy whichever way it reads.
        body = {
            "data": 54316316722,
            "email": "someone@example.test",
            "is_traffic_frozen": "no",
            "proxy_password": "p",
            "proxy_username": "u",
            "subscription_status": "active",
        }
        api, _ = client((200, body))
        assert api.me() == body

    def test_a_field_nobody_here_predicted_survives(self):
        # The other half of not modelling it: an added field reaches the caller
        # instead of being dropped by a schema written before it existed.
        body = {"data": 1, "a_field_nobody_here_predicted": 2}
        api, _ = client((200, body))
        assert api.me() == body

    def test_a_list_where_an_object_was_expected_is_refused_loudly(self):
        api, _ = client((200, [1, 2, 3]))
        with pytest.raises(ApiError, match="where an object was expected"):
            api.me()

    def test_the_base_url_is_overridable_and_its_trailing_slash_is_dropped(self):
        api, fake = client((200, {}), base_url="https://staging.example.test/")
        api.me()
        assert fake.url == f"https://staging.example.test{API_ROOT}/users/me"

    def test_the_base_url_comes_from_the_environment_too(self, monkeypatch):
        monkeypatch.setenv("NODEMAVEN_BASE_URL", "https://env.example.test")
        fake = Fake((200, {}))
        Client(api_key="k", transport=fake).me()
        assert fake.url.startswith("https://env.example.test")


class TestTheCatalogue:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("countries", "/locations/countries/"),
            ("regions", "/locations/regions/"),
            ("cities", "/locations/cities/"),
            ("isps", "/locations/isps/"),
            ("isp_regions", "/locations/isps/regions/"),
            ("isp_cities", "/locations/isps/cities/"),
            ("zip_codes", "/locations/zipcodes/"),
            ("zip_code_regions", "/locations/zipcodes/regions/"),
            ("zip_code_cities", "/locations/zipcodes/cities/"),
        ],
    )
    def test_each_endpoint_is_where_the_spec_says_it_is(self, method, path):
        # `zip_codes` said `/locations/zip-codes/` here until 2026-09-09,
        # transcribed from the vendor's client, and this test passed the whole
        # time - because it asserted the transcription against itself. The real
        # path is solid, `zipcodes`, and there is no naming rule on this API to
        # have derived it from: `sub-users` is hyphenated and `users/me` carries
        # no trailing slash where its neighbours do. A test that pins a path
        # can only ever pin where the path came from.
        api, fake = client((200, {"count": 0, "results": []}))
        getattr(api, method)()
        assert fake.url.split("?")[0] == f"{DEFAULT_BASE_URL}{API_ROOT}{path}"

    @pytest.mark.parametrize(
        "method",
        [
            "countries",
            "regions",
            "cities",
            "isps",
            "isp_regions",
            "isp_cities",
            "zip_codes",
            "zip_code_regions",
            "zip_code_cities",
        ],
    )
    def test_every_list_call_sends_limit_and_offset(self, method):
        # Not a default, a requirement. Measured 2026-09-08 against the live
        # API: `locations/isps` refuses a request that omits them, and the other
        # three location endpoints answer such a request with exactly 50 rows
        # and no reported total - byte-for-byte what a complete collection looks
        # like. The refusal is visible on the first call; the truncation is not
        # visible ever, which is why these are sent rather than left out.
        api, fake = client((200, {"count": 0, "results": []}))
        getattr(api, method)()
        assert f"limit={DEFAULT_PAGE_SIZE}" in fake.url
        assert "offset=0" in fake.url

    def test_a_callers_limit_and_offset_win_over_the_defaults(self):
        # Parsed rather than matched as a substring: `limit=50` is a substring
        # of `limit=500`, so the obvious `not in` assertion passes for the
        # wrong reason and fails for the right one. It did, once.
        api, fake = client((200, {"count": 0, "results": []}))
        api.countries(limit=500, offset=50)
        query = parse_qs(urlsplit(fake.url).query)
        assert query["limit"] == ["500"]
        assert query["offset"] == ["50"]

    def test_djangos_double_underscore_filter_is_passed_through_untranslated(self):
        # The server's spelling, not a typo. Renaming it to `country_code` would
        # be one alias to maintain and one more place a caller's filter is
        # dropped in silence, because an unknown query parameter is ignored by
        # every REST framework there is.
        api, fake = client((200, {"results": []}))
        api.cities(country__code="us", region__code="dc")
        assert "country__code=us" in fake.url
        assert "region__code=dc" in fake.url

    def test_a_none_filter_is_dropped_rather_than_sent_as_the_word_none(self):
        # `countries(name=None)` must send nothing. Sent, the string "None"
        # matches zero rows and comes back as an empty catalogue, which reads as
        # "the product has no countries".
        api, fake = client((200, {"results": []}))
        api.countries(name=None, country__code="us")
        assert "name=" not in fake.url
        assert "country__code=us" in fake.url

    def test_no_connection_type_default_is_added_here(self):
        # The server defaults it to residential. Sending a default of our own
        # would show up in a support ticket as something the caller chose.
        api, fake = client((200, {"results": []}))
        api.countries()
        assert "connection_type" not in fake.url


class TestThePageShapeIsInferredSoEveryShapeIsHandled:
    def test_the_paginated_envelope(self):
        api, _ = client(
            (200, {"count": 250, "next": "u", "previous": None, "results": [1, 2]})
        )
        page = api.countries()
        assert isinstance(page, Page)
        assert page.count == 250
        assert page.next == "u"
        assert list(page) == [1, 2]
        assert len(page) == 2

    def test_a_bare_list(self):
        # What the endpoint answers if it is not paginated after all.
        api, _ = client((200, [{"code": "us"}, {"code": "de"}]))
        page = api.countries()
        assert len(page) == 2
        assert page.count is None

    def test_a_single_object_is_wrapped_and_the_wrapping_is_visible(self):
        # Real servers do this for a filter matching one row. `count is None` is
        # how a caller can tell it was wrapped rather than counted.
        api, _ = client((200, {"code": "us", "name": "United States"}))
        page = api.countries()
        assert len(page) == 1
        assert page.results[0]["code"] == "us"
        assert page.count is None

    def test_an_empty_object_is_an_empty_page_and_not_a_page_of_one(self):
        api, _ = client((200, {}))
        assert len(api.countries()) == 0

    def test_something_that_is_neither_names_what_came_back(self):
        # The alternative is `body["results"]`, whose KeyError describes this
        # package's assumption instead of the server's answer - on the one code
        # path where the assumption is explicitly untested.
        api, _ = client((200, b'"a captive portal wrote this"'))
        with pytest.raises(ApiError, match="neither a page nor a list"):
            api.countries()

    def test_the_refusal_mentions_the_two_things_that_actually_do_this(self):
        api, _ = client((200, b"42"))
        with pytest.raises(ApiError, match="captive portal"):
            api.countries()


class TestIspsPutsItsRowsUnderADifferentKey:
    """``locations/isps`` answers a different envelope from the other four.

    Measured 2026-09-08 with ``country__code="us"``: the object is keyed
    ``city``, ``country``, ``isps``, ``region``, there is no ``results``, and
    ``isps`` is a list of 358. The bodies below are that shape.

    For one day this method returned a page of exactly one row - the envelope
    itself - and was documented as broken rather than fixed, because the first
    probe printed key *names* and not values. These cases are what the second
    probe bought.
    """

    ENVELOPE = {
        "city": "",
        "country": "us",
        "region": "",
        "isps": [{"id": 1, "name": "Comcast"}, {"id": 2, "name": "Charter"}],
    }

    def test_the_rows_are_the_isps_list_and_not_the_envelope(self):
        api, _ = client((200, self.ENVELOPE))
        page = api.isps(country__code="us")
        assert len(page) == 2
        assert [row["name"] for row in page] == ["Comcast", "Charter"]

    def test_the_three_string_fields_are_not_rows(self):
        # They are strings whose contents have never been printed, so this
        # package says nothing about them - including by handing them back
        # inside a list of ISPs.
        api, _ = client((200, self.ENVELOPE))
        assert all(isinstance(row, dict) for row in api.isps())

    def test_the_key_is_per_endpoint_and_not_a_search_for_any_list(self):
        # The control for the fix. An envelope carrying two lists would be
        # resolved by dict order if `_page` went looking for "whichever value
        # is a list", silently and differently per server version. So the same
        # body through `countries()` takes the single-object branch, because
        # `countries` reads `results` and this body has none.
        api, _ = client((200, self.ENVELOPE))
        page = api.countries()
        assert len(page) == 1
        assert page.results[0] == self.ENVELOPE

    def test_a_body_with_no_isps_key_still_falls_through_to_the_old_branches(self):
        api, _ = client((200, {"detail": "one row"}))
        assert len(api.isps()) == 1

    def test_the_walk_reads_the_second_page_the_same_way_as_the_first(self):
        # `iterate` reparses each page it fetches, so the key has to travel on
        # the Page. Without that it would read page one as ISPs and page two as
        # a one-row envelope, and stop - a truncation wearing the shape of an
        # ending.
        api, fake = client(
            (200, {"isps": list(range(50))}),
            (200, {"isps": list(range(50, 60))}),
            (200, {"isps": []}),
        )
        assert list(api.iterate(api.isps(limit=50))) == list(range(60))
        assert len(fake.calls) == 3

    def test_an_offset_past_the_end_ends_the_walk(self):
        # Arm E and arm H of the live run, 2026-09-08: `offset=1000000` and
        # `offset=1000` both answer 200 with `isps` an empty list rather than
        # the last page. That is the ending `iterate` stops on, and it is also
        # what rules out the server accepting `offset` and dropping it - an
        # ignored offset would have answered all 358 rows.
        api, _ = client(
            (200, {"isps": list(range(50))}),
            (200, {"isps": []}),
        )
        assert list(api.iterate(api.isps(limit=50))) == list(range(50))


class TestErrorsAreClassesACallerWouldBranchOn:
    def test_401_is_an_auth_error_naming_which_secret(self):
        api, _ = client((401, {"detail": "Invalid token."}))
        with pytest.raises(AuthError, match="NODEMAVEN_APIKEY") as caught:
            api.me()
        assert caught.value.status == 401
        assert caught.value.body == {"detail": "Invalid token."}

    def test_403_is_the_same_class(self):
        api, _ = client((403, {"detail": "no"}))
        with pytest.raises(AuthError):
            api.me()

    def test_404_is_its_own_class_because_crud_branches_on_it(self):
        api, _ = client((404, {"detail": "Not found."}))
        with pytest.raises(NotFoundError) as caught:
            api.delete_sub_user(7)
        assert caught.value.status == 404

    def test_429_says_it_cannot_report_the_interval_and_retries_nothing(self):
        # This was called `..._carries_the_servers_own_interval_...` and the
        # message told the caller to read `retry_after`, while this same
        # assertion pinned it as `None`. It can never be anything else from
        # this client: `Transport` returns `(status, bytes)` and the headers
        # are gone before `_interpret` sees them, so a `Retry-After` the server
        # sent cannot reach the attribute. Found by review 2026-09-09.
        #
        # The test and the defect were three lines apart. The assertion was
        # read as "the server did not send one" for as long as it existed, and
        # nothing said the other branch was unreachable.
        api, _ = client((429, {"detail": "Request was throttled."}))
        with pytest.raises(RateLimitError, match="Nothing here retries") as caught:
            api.me()
        assert caught.value.retry_after is None
        assert "retry_after is always None" in str(caught.value)

    def test_5xx_says_that_hammering_it_is_the_thing_we_decline_to_do(self):
        api, _ = client((503, {"detail": "upstream down"}))
        with pytest.raises(ApiError) as caught:
            api.me()
        assert caught.value.status == 503
        assert not isinstance(caught.value, (AuthError, NotFoundError, RateLimitError))

    def test_400_stays_on_the_base_class_because_the_fix_is_your_program(self):
        # A class exists here only if a caller would plausibly write different
        # code for it. 401 means fix your key, 429 means wait, 404 in CRUD means
        # the row is gone - a 400 means fix the call, and there is nothing to
        # branch on.
        api, _ = client((400, {"expiry_date": ["Enter a valid date."]}))
        with pytest.raises(ApiError) as caught:
            api.me()
        assert type(caught.value) is ApiError
        assert "Enter a valid date." in str(caught.value)

    def test_every_api_error_is_a_nodemaven_error(self):
        from nodemaven import NodeMavenError

        for cls in (ApiError, AuthError, NotFoundError, RateLimitError):
            assert issubclass(cls, NodeMavenError)

    def test_the_url_is_in_the_message_and_the_key_is_not(self):
        api, _ = client((500, {"detail": "boom"}))
        with pytest.raises(ApiError) as caught:
            api.me()
        assert "/users/me" in str(caught.value)
        assert "k3y" not in str(caught.value)


class TestTheServersOwnMessageSurvives:
    def test_a_detail_string(self):
        api, _ = client((400, {"detail": "the useful sentence"}))
        with pytest.raises(ApiError, match="the useful sentence"):
            api.me()

    def test_field_errors_are_flattened_rather_than_str_of_a_dict(self):
        # `str()` of a dict shows Python syntax to somebody debugging an HTTP
        # call.
        api, _ = client((400, {"username": ["too short", "taken"]}))
        with pytest.raises(ApiError) as caught:
            api.me()
        assert "username: too short; taken" in str(caught.value)
        assert "{" not in str(caught.value)

    def test_a_bare_list_body(self):
        api, _ = client((400, ["first", "second"]))
        with pytest.raises(ApiError, match="first; second"):
            api.me()

    def test_a_body_that_is_not_json_at_all(self):
        api, _ = client((502, b"<html>Bad Gateway</html>"))
        with pytest.raises(ApiError, match="Bad Gateway"):
            api.me()

    def test_an_empty_error_body_falls_back_to_the_status(self):
        api, _ = client((418, b""))
        with pytest.raises(ApiError, match="HTTP 418"):
            api.me()


class TestSubUsers:
    """Five write calls and one read, none of which has ever been sent.

    Each one costs a real object on a production account, so every shape below
    is the vendor's OpenAPI document of 2026-09-09 and nothing more. What these
    cases pin is that this package sends what that document describes - not that
    the document is right, which is a separate claim and an unmeasured one.

    The bodies here were ``username``/``password`` against
    ``sub-users/{id}/`` until that document was read. Both were wrong, and the
    tests asserting them passed, because they were written from the same
    transcription the code was.
    """

    ENVELOPE = {
        "success": True,
        "description": "",
        "errors": [],
        "payload": {"id": "4", "proxy_username": "kid"},
    }

    def test_the_rows_come_out_of_payload_and_not_results(self):
        # Measured 2026-09-09 and declared by the spec as SubUserManyResponse.
        # Reading `results` here returned an empty page against a populated
        # account and said nothing about it.
        many = dict(self.ENVELOPE, payload=[{"id": "1"}, {"id": "2"}])
        api, _ = client((200, many))
        assert [row["id"] for row in api.sub_users()] == ["1", "2"]

    def test_create_sends_the_fields_the_spec_names_required(self):
        api, fake = client((200, self.ENVELOPE))
        api.create_sub_user("kid", "pw")
        assert fake.calls[-1]["method"] == "POST"
        assert fake.calls[-1]["body"] == {
            "proxy_username": "kid",
            "proxy_password": "pw",
        }

    def test_the_envelope_is_unwrapped_so_callers_never_see_payload(self):
        api, _ = client((200, self.ENVELOPE))
        assert api.create_sub_user("kid", "pw") == {"id": "4", "proxy_username": "kid"}

    def test_a_2xx_carrying_success_false_is_refused(self):
        # The envelope has a success flag, which is a server reserving the right
        # to disagree with its own status line. Reading the status alone would
        # report this as done.
        api, _ = client(
            (200, {"success": False, "description": "no", "errors": [], "payload": None})
        )
        with pytest.raises(ApiError, match="success=false"):
            api.create_sub_user("kid", "pw")

    def test_the_optional_fields_are_omitted_when_unset(self):
        api, fake = client((200, self.ENVELOPE))
        api.create_sub_user("kid", "pw", traffic_limit=1024)
        assert fake.calls[-1]["body"] == {
            "proxy_username": "kid",
            "proxy_password": "pw",
            "traffic_limit": 1024,
        }

    def test_extra_fields_pass_through(self):
        api, fake = client((200, self.ENVELOPE))
        api.create_sub_user("kid", "pw", note="whatever the server calls it")
        assert fake.calls[-1]["body"]["note"] == "whatever the server calls it"

    def test_update_is_a_put_to_the_collection_with_the_id_in_the_body(self):
        # There is no `sub-users/{id}/` path in the spec at all. The old
        # spelling would have been a 404 - or, on this host, a 200 carrying the
        # dashboard's HTML, which is worse.
        api, fake = client((200, self.ENVELOPE))
        api.update_sub_user("9", traffic_limit=2048)
        assert fake.calls[-1]["method"] == "PUT"
        assert fake.calls[-1]["url"].endswith(f"{API_ROOT}/sub-users/")
        assert fake.calls[-1]["body"] == {"traffic_limit": 2048, "id": "9"}

    def test_an_empty_change_set_is_refused_and_nothing_is_sent(self):
        # A body of nothing but an id can be answered 200, and a call that
        # reports success while changing nothing is the failure mode this whole
        # package is organised against.
        api, fake = client((200, {}))
        with pytest.raises(ApiError, match="answered 200"):
            api.update_sub_user("9")
        assert fake.calls == []

    def test_delete_sends_the_id_as_a_query_parameter(self):
        api, fake = client((204, b""))
        assert api.delete_sub_user("9") == {}
        assert fake.calls[-1]["method"] == "DELETE"
        assert parse_qs(urlsplit(fake.url).query)["id"] == ["9"]
        assert urlsplit(fake.url).path == f"{API_ROOT}/sub-users/"

    def test_reset_usage_takes_a_list_even_for_one(self):
        # So the one-and-many cases cannot diverge. `ids` is the endpoint's only
        # required field and it is an array.
        api, fake = client((200, dict(self.ENVELOPE, payload=[])))
        api.reset_sub_user_usage(["9"])
        assert fake.calls[-1]["method"] == "POST"
        assert fake.calls[-1]["url"].endswith(f"{API_ROOT}/sub-users/reset/usage")
        assert fake.calls[-1]["body"] == {"ids": ["9"]}


class TestWhitelistIps:
    def test_the_list_path_has_no_trailing_slash(self):
        # `whitelist-ips/` was an invention. Measured 2026-09-09: it answered
        # 200 with 6415 bytes of the dashboard's HTML, byte-identical to a path
        # nobody registered.
        api, fake = client((200, {"results": []}))
        api.whitelist_ips()
        assert urlsplit(fake.url).path == f"{API_ROOT}/whitelist/ips"

    def test_page_size_is_sent_because_the_documented_default_is_five(self):
        api, fake = client((200, {"results": []}))
        api.whitelist_ips()
        assert parse_qs(urlsplit(fake.url).query)["page_size"] == ["100"]

    def test_page_one_is_sent_because_the_base_was_measured(self):
        # This asserted `"page" not in query` until 2026-09-09, when nothing said
        # whether the base was 0 or 1. Phase 9 of `probe_account_api.py` says 1:
        # page 1 is the only number this endpoint answers 200, against 404 on 0,
        # 2 and 9999.
        api, fake = client((200, {"results": []}))
        api.whitelist_ips()
        assert parse_qs(urlsplit(fake.url).query)["page"] == ["1"]

    def test_upsert_posts_protocol_as_well_as_the_required_pair(self):
        # `protocol` is sent because the server does not apply the
        # `default: "HTTP"` its own document declares for it. Measured
        # 2026-09-09 16:18 by the ladder in `lab\probes\probe_account_api.py`:
        # ip + ports_count + name is refused 400 "Please enter a valid
        # protocol(HTTP or SOCKS5)."; the same body plus protocol is accepted
        # 201. Drop it from the body and every call to this endpoint fails.
        api, fake = client((200, {"message": "ok"}))
        api.upsert_whitelist_ip("203.0.113.7", 4, name="the office")
        assert fake.calls[-1]["method"] == "POST"
        assert fake.calls[-1]["url"].endswith(f"{API_ROOT}/whitelist/ip/upsert")
        assert fake.calls[-1]["body"] == {
            "ip": "203.0.113.7",
            "ports_count": 4,
            "protocol": "HTTP",
            "name": "the office",
        }

    def test_protocol_can_be_overridden(self):
        api, fake = client((200, {"message": "ok"}))
        api.upsert_whitelist_ip("203.0.113.7", 4, protocol="SOCKS5")
        assert fake.calls[-1]["body"]["protocol"] == "SOCKS5"

    def test_it_is_named_upsert_because_that_is_what_it_does(self):
        # Passing an id updates an existing row. A method called `add` that
        # silently updates is a worse bug than a wrong path, because the wrong
        # path fails.
        assert not hasattr(Client, "add_whitelist_ip")
        assert hasattr(Client, "upsert_whitelist_ip")

    def test_one_row_is_read_by_id(self):
        api, fake = client((200, {"id": "3", "ip": "203.0.113.7"}))
        api.whitelist_ip(3)
        assert fake.calls[-1]["method"] == "GET"
        assert fake.calls[-1]["url"].endswith(f"{API_ROOT}/whitelist/ip/3")

    def test_delete_targets_one_row(self):
        api, fake = client((204, b""))
        api.delete_whitelist_ip(3)
        assert fake.calls[-1]["method"] == "DELETE"
        assert fake.calls[-1]["url"].endswith(f"{API_ROOT}/whitelist/ip/3")

    def test_an_id_cannot_rewrite_the_path(self):
        # Ids come from the server, which makes this look unnecessary - and the
        # day one comes from a config file or an argv instead, it is the
        # difference between a 404 and a DELETE against something else.
        #
        # The assertion is about slashes and not about the text: the traversal
        # still reads as `../../sub-users/1` in the url, escaped, and that is
        # harmless. What would not be harmless is one surviving `/`, because
        # that is the character that ends a path segment.
        api, fake = client((204, b""))
        api.delete_whitelist_ip("../../sub-users/1")
        segment = fake.url.split(f"{API_ROOT}/whitelist/ip/")[1]
        assert "/" not in segment
        assert segment == "..%2F..%2Fsub-users%2F1"


class TestStatistics:
    """One method became three, because `/statistics/` was never a path.

    Measured 2026-09-09: it answered 200 with the dashboard's HTML. The three
    that exist are `statistics/data/`, `.../requests/` and `.../domains/`, and
    all three require `proxy_username`.
    """

    def test_there_is_no_bare_statistics_call_any_more(self):
        assert not hasattr(Client, "statistics")

    @pytest.mark.parametrize(
        "method,path",
        [
            ("statistics_data", "/statistics/data/"),
            ("statistics_requests", "/statistics/requests/"),
        ],
    )
    def test_the_two_series_endpoints_return_the_two_arrays_unmodelled(
        self, method, path
    ):
        body = {"labels": ["2026-09-01"], "data": [5]}
        api, fake = client((200, body))
        assert getattr(api, method)("acct-1") == body
        assert urlsplit(fake.url).path == f"{API_ROOT}{path}"

    def test_proxy_username_is_positional_because_the_server_requires_it(self):
        # The difference between a 400 at run time and a TypeError at the call
        # site.
        api, fake = client((200, {"labels": [], "data": []}))
        with pytest.raises(TypeError):
            api.statistics_data()
        assert fake.calls == []

    def test_the_optional_filters_are_passed_through_untranslated(self):
        # Dates are not validated here. The server has to check them anyway, and
        # the spec cannot make up its mind what the format is - the prose says
        # "dd-mm-yyyy" and the type says `format: date`, which is `yyyy-mm-dd`.
        api, fake = client((200, {"labels": [], "data": []}))
        api.statistics_data("acct-1", start="2026-09-01", period="hours24")
        query = parse_qs(urlsplit(fake.url).query)
        assert query["start"] == ["2026-09-01"]
        assert query["period"] == ["hours24"]
        assert query["proxy_username"] == ["acct-1"]

    def test_domain_rows_come_out_of_data_and_the_call_does_not_page(self):
        # `{"data": [...]}` with no cursor of any kind - `limit` there is a
        # top-N cut and there is no `offset` in the spec's parameter list. So
        # iterating it yields these rows and makes no second request.
        api, fake = client(
            (200, {"data": [{"domain_name": "a", "requests": 2, "data": 3}]})
        )
        page = api.domain_statistics("acct-1", limit=10)
        assert isinstance(page, Page)
        assert [row["domain_name"] for row in page] == ["a"]
        assert list(api.iterate(page)) == page.results
        assert len(fake.calls) == 1
        assert urlsplit(fake.url).path == f"{API_ROOT}/statistics/domains/"


class TestIterate:
    def test_it_follows_next_to_the_end(self):
        api, fake = client(
            (200, {"count": 4, "next": f"{DEFAULT_BASE_URL}/p2", "results": [1, 2]}),
            (200, {"count": 4, "next": None, "results": [3, 4]}),
            (200, {"count": 4, "next": None, "results": []}),
        )
        assert list(api.iterate(api.countries(limit=2))) == [1, 2, 3, 4]

    def test_an_absolute_next_url_on_the_same_host_is_used_as_given(self):
        # Paging links come back absolute, so they are followed rather than
        # re-derived: the server has said where the next page is, including
        # whatever query it needs, and rebuilding that from the path would be
        # guessing at a shape this module has never seen from the live API.
        api, fake = client(
            (200, {"next": f"{DEFAULT_BASE_URL}/api/v2/base/x?offset=50", "results": [1]}),
            (200, {"next": None, "results": []}),
        )
        list(api.iterate(api.countries()))
        assert fake.calls[1]["url"] == f"{DEFAULT_BASE_URL}/api/v2/base/x?offset=50"

    def test_a_next_that_repeats_is_a_loop_and_is_refused(self):
        # A server whose `next` points at the page you are on turns `while
        # next:` into an unbounded run of real HTTP requests, whose first
        # symptom is a rate limit rather than a hang.
        api, _ = client((200, {"next": f"{DEFAULT_BASE_URL}/same", "results": [1]}))
        with pytest.raises(ApiError, match="already returned"):
            list(api.iterate(api.countries()))

    def test_the_bound_raises_rather_than_truncating_silently(self):
        api, _ = client(
            *[
                (200, {"next": f"{DEFAULT_BASE_URL}/p{n}", "results": [n]})
                for n in range(2, 12)
            ]
        )
        with pytest.raises(ApiError, match="max_pages"):
            list(api.iterate(api.countries(), max_pages=3))

    def test_an_endpoint_that_does_not_page_makes_no_further_request(self):
        # `domain_statistics` is the only one. Everything else costs the spare
        # request below, on purpose.
        api, fake = client((200, {"data": [1, 2]}))
        assert list(api.iterate(api.domain_statistics("acct-1"))) == [1, 2]
        assert len(fake.calls) == 1


class TestIterateWalksByOffsetWhenThereIsNoNext:
    """What an envelope that fills nothing forces, measured 2026-09-08.

    `countries`, `regions` and `cities` answer with a paging envelope, and that
    envelope reported **no `count`** on a page of 50 out of 192. Confirmed
    against the vendor's spec on 2026-09-09: `PaginatedCountryList` and its
    siblings declare `results` and nothing else, so there is no `count` and no
    `next` field to fill. Stopping at an empty `next` would yield the first page
    and call it the collection, which the caller could not tell apart from a
    complete answer.

    **The walk stops on an empty page, not on a short one, and that changed on
    2026-09-09.** The old rule was "shorter than the limit asked for", and it
    truncates against a server that caps the size below the request. This one
    does: `cities(limit=10000)` is answered with 1000 rows out of 1965, and the
    old rule reads those 1000 as the end. The measurement was already written in
    `api.py` and the stop rule was never checked against it.

    This class said "a bare JSON array" and pinned the opposite behaviour for
    part of 2026-09-08. See `Client.iterate` for what that reading was built on.
    """

    def test_a_full_page_is_followed_at_the_next_offset(self):
        api, fake = client(
            (200, {"results": list(range(0, 50))}),
            (200, {"results": list(range(50, 100))}),
            (200, {"results": list(range(100, 110))}),
            (200, {"results": []}),
        )
        assert list(api.iterate(api.countries(limit=50))) == list(range(110))
        offsets = [parse_qs(urlsplit(c["url"]).query)["offset"] for c in fake.calls]
        # The third page is short - 10 rows against a limit of 50 - so the
        # fourth offset is 110 and not 150. This asserted 150 until 2026-09-09:
        # the cursor advanced by the limit that was *asked for*, which is only
        # the same number while the server never returns fewer.
        assert offsets == [["0"], ["50"], ["100"], ["110"]]

    def test_a_short_page_is_followed_because_the_server_caps_the_limit(self):
        # This asserted the opposite until 2026-09-09 and it was the reason the
        # old rule survived: a short page really is the end most of the time, so
        # the test passed and the truncating case was never written down.
        api, fake = client(
            (200, {"results": list(range(49))}), (200, {"results": []})
        )
        assert list(api.iterate(api.countries(limit=50))) == list(range(49))
        assert len(fake.calls) == 2

    def test_the_capped_page_that_the_old_rule_truncated(self):
        # The live case, 2026-09-08: `cities(limit=10000)` is answered with 1000
        # rows because 1000 is the server ceiling, and there are 1965. Under
        # "stop on a short page" this walk returned 1000 and reported nothing.
        #
        # **The offsets are asserted here from 2026-09-09, and until they were
        # this test could not fail on the case it is named after.** It checked
        # the row count only, and `FakeTransport` replays its queue whatever the
        # query string says, so a walk asking for offset 0, 10000, 20000 gets
        # the same three responses as one asking for 0, 1000, 1965 and counts
        # 1965 either way. Against the real server the second request would have
        # started 8035 rows past the end of the collection. The two tests in
        # this class that do read the offsets were asserting the wrong numbers,
        # so the defect sat between a test that could not see it and two that
        # pinned it.
        api, fake = client(
            (200, {"results": list(range(0, 1000))}),
            (200, {"results": list(range(1000, 1965))}),
            (200, {"results": []}),
        )
        assert len(list(api.iterate(api.cities(limit=10000)))) == 1965
        offsets = [parse_qs(urlsplit(c["url"]).query)["offset"] for c in fake.calls]
        assert offsets == [["0"], ["1000"], ["1965"]]

    def test_a_caller_who_raised_the_limit_pages_by_the_rows_returned(self):
        # This was called `..._pages_at_that_limit` and asserted 400 as the
        # third offset until 2026-09-09, so its own name stated the defect as
        # the intended behaviour. The second page holds 3 rows, so everything
        # from 203 to 399 was skipped whenever the server had it.
        api, fake = client(
            (200, {"results": list(range(200))}),
            (200, {"results": list(range(3))}),
            (200, {"results": []}),
        )
        list(api.iterate(api.countries(limit=200)))
        offsets = [parse_qs(urlsplit(c["url"]).query)["offset"] for c in fake.calls]
        assert offsets == [["0"], ["200"], ["203"]]

    def test_the_default_limit_is_what_a_caller_who_asks_for_nothing_pages_at(self):
        api, fake = client(
            (200, {"results": list(range(DEFAULT_PAGE_SIZE))}),
            (200, {"results": [1]}),
            (200, {"results": []}),
        )
        list(api.iterate(api.countries()))
        offsets = [parse_qs(urlsplit(c["url"]).query)["offset"] for c in fake.calls]
        assert offsets[:2] == [["0"], [str(DEFAULT_PAGE_SIZE)]]

    def test_a_bare_array_pages_the_same_way(self):
        # The shape this whole class was written for and which has never been
        # seen from this server. `_page` still accepts it, so it is still
        # exercised - a branch nothing tests is a branch that has already rotted.
        api, fake = client(
            (200, list(range(0, 50))),
            (200, list(range(50, 60))),
            (200, []),
        )
        assert list(api.iterate(api.countries(limit=50))) == list(range(60))
        assert len(fake.calls) == 3

    def test_a_server_that_ignores_offset_raises_rather_than_repeating(self):
        # The guard that makes the offset walk safe to infer. The server was
        # measured to *require* `limit` and `offset` on `locations/isps`, never
        # to *honour* them across pages, and those are different claims. A
        # server that accepts `offset` and ignores it hands back the same 50
        # rows for every page; without this, `iterate()` would return them a
        # hundred times over and call it a collection.
        api, _ = client(
            (200, {"results": list(range(50))}), (200, {"results": list(range(50))})
        )
        with pytest.raises(ApiError, match="accepting `offset` and ignoring it"):
            list(api.iterate(api.countries(limit=50)))

    def test_an_envelope_with_an_empty_next_is_not_read_as_the_end(self):
        # The inverse of what this asserted for a few hours on 2026-09-08, when
        # it was written against a hand-made Django REST Framework envelope
        # carrying a real `count`. The live envelope leaves `count` empty on a
        # page of 50 out of 192, so an empty `next` beside it is absence and not
        # an answer, and honouring it stopped every catalogue read after one
        # page. One spare request is the price, and the second answer here is
        # what a genuine ending looks like.
        api, fake = client(
            (200, {"count": None, "next": None, "results": list(range(50))}),
            (200, {"count": None, "next": None, "results": []}),
        )
        assert list(api.iterate(api.countries(limit=50))) == list(range(50))
        assert len(fake.calls) == 2


class TestIterateRefusesToGuessAPageNumber:
    """`sub-users/` and `whitelist/ips` number their pages, and both start at 1.

    **This class used to pin the opposite, and the name is kept so the retired
    behaviour stays findable.** Until 2026-09-09 nothing measured said whether
    the first page was 0 or 1. The two readings are not symmetric - guessing 1
    against a 0-based server drops the first page in silence - so no cursor was
    sent and `iterate()` raised rather than invent one.

    What retired it is `probe_account_api.py --phase 9`, run 2026-09-09 from the
    user's own connection, asking each endpoint for pages 0, 1, 2 and 9999 at one
    row a page. `sub-users/` answered page 0 with no rows and page 1 with the
    account's single sub-user, which a 0-based server cannot produce.
    `whitelist/ips` holds nothing and answers `200` on page 1 against `404` on 0,
    2 and 9999, which is the weaker reading and is recorded as such in `Paging`.
    """

    def test_the_first_page_is_asked_for_by_number(self):
        body = {"success": True, "description": "", "errors": [], "payload": [{"id": 1}]}
        api, fake = client((200, body))
        api.sub_users()
        assert parse_qs(urlsplit(fake.calls[0]["url"]).query)["page"] == ["1"]

    def test_an_unnumbered_call_is_walked_from_page_one(self):
        pages = [
            {"success": True, "description": "", "errors": [], "payload": [{"id": 1}]},
            {"success": True, "description": "", "errors": [], "payload": [{"id": 2}]},
            {"success": True, "description": "", "errors": [], "payload": []},
        ]
        api, fake = client(*[(200, body) for body in pages])
        assert [row["id"] for row in api.iterate(api.sub_users())] == [1, 2]
        numbers = [parse_qs(urlsplit(c["url"]).query)["page"] for c in fake.calls]
        assert numbers == [["1"], ["2"], ["3"]]

    def test_the_rows_of_the_first_page_are_still_returned(self):
        body = {"success": True, "description": "", "errors": [], "payload": [{"id": 1}]}
        api, _ = client((200, body))
        assert [row["id"] for row in api.sub_users()] == [1]

    def test_a_caller_who_names_a_page_is_walked_from_it(self):
        pages = [
            {"success": True, "description": "", "errors": [], "payload": [{"id": 1}]},
            {"success": True, "description": "", "errors": [], "payload": [{"id": 2}]},
            {"success": True, "description": "", "errors": [], "payload": []},
        ]
        api, fake = client(*[(200, body) for body in pages])
        assert [row["id"] for row in api.iterate(api.sub_users(page=1))] == [1, 2]
        numbers = [parse_qs(urlsplit(c["url"]).query)["page"] for c in fake.calls]
        assert numbers == [["1"], ["2"], ["3"]]

    def test_the_whitelist_walks_by_its_own_parameter_names(self):
        api, fake = client(
            (200, {"results": [{"id": "a"}]}),
            (200, {"results": []}),
        )
        list(api.iterate(api.whitelist_ips(page=1)))
        query = parse_qs(urlsplit(fake.calls[-1]["url"]).query)
        assert query["page"] == ["2"]
        assert query["page_size"] == ["100"]

    def test_the_whitelist_ends_its_walk_on_a_404(self):
        # Measured 2026-09-09: this endpoint answers a page past the end with
        # 404 rather than with an empty page, so the stop-on-empty rule never
        # fires and the walk would raise at the end of every collection.
        api, _ = client(
            (200, {"results": [{"id": "a"}]}),
            (404, {"detail": "Invalid page."}),
        )
        assert [row["id"] for row in api.iterate(api.whitelist_ips())] == ["a"]

    def test_a_404_still_raises_where_it_was_not_measured(self):
        # The two page-number endpoints do not agree: `sub-users/` answers 200
        # with an empty payload past the end. Treating 404 as an ending
        # everywhere would swallow a path this module got wrong, which is
        # exactly the failure four of these paths had on 2026-09-09.
        first = {"success": True, "description": "", "errors": [], "payload": [{"id": 1}]}
        api, _ = client((200, first), (404, {"detail": "no such thing"}))
        with pytest.raises(NotFoundError):
            list(api.iterate(api.sub_users()))


class TestTheKeyOnlyEverGoesToOneHost:
    """Where an API key is allowed to travel, and what pinned the opposite.

    Until 2026-09-08 the case above this class read
    ``test_an_absolute_next_url_is_used_as_given``, answered ``next`` with
    ``https://elsewhere.example.test/p2``, and asserted that the request went
    there. It was a real property of the paging loop, written deliberately, and
    it was pinning the defect: ``_request`` attaches
    ``Authorization: x-api-key <key>`` to whatever url it is handed, so "used as
    given" is "the credential goes wherever the response says". A test can be
    correct about behaviour and wrong about whether that behaviour should exist.

    It was not caught by writing more tests of the same kind. It came from an
    external review on 2026-09-08 and was reproduced through this same transport
    seam the same day.
    """

    def test_a_next_on_another_host_is_refused_before_the_key_is_sent(self):
        api, fake = client(
            (200, {"next": "https://evil.example/api/v2/base/x", "data": [1]}),
            (200, {"next": None, "data": [2]}),
        )
        with pytest.raises(ApiError, match="refusing to send the API key"):
            list(api.iterate(api.domain_statistics("acct")))
        assert len(fake.calls) == 1

    def test_the_measured_leak_was_the_key_in_a_header_and_not_just_a_request(self):
        # What made this worth fixing over merely noting: reproduced 2026-09-08,
        # the second request carried `Authorization: x-api-key SECRET-KEY` to a
        # host nobody configured. The assertion is on the header and not on the
        # url, because a request to a stranger with no credential in it is a
        # different and much smaller problem.
        sent = []

        def transport(method, url, headers, body):
            sent.append((url, headers.get("Authorization")))
            if len(sent) == 1:
                return 200, json.dumps(
                    {"next": "https://evil.example/p2", "data": [1]}
                ).encode()
            return 200, json.dumps({"next": None, "data": [2]}).encode()

        api = Client(api_key="SECRET-KEY", transport=transport)
        with pytest.raises(ApiError):
            list(api.iterate(api.domain_statistics("acct")))
        assert not any("evil.example" in url for url, _ in sent)
        assert all("SECRET-KEY" in auth for _, auth in sent)

    def test_a_downgrade_to_http_on_the_right_host_is_refused_too(self):
        # The same leak on a wire rather than to a stranger. The key travels in
        # a header and a header is plaintext, so scheme is part of the rule and
        # not decoration on it.
        host = DEFAULT_BASE_URL.split("://", 1)[1]
        api, _ = client((200, {"next": f"http://{host}/p2", "data": [1]}))
        with pytest.raises(ApiError, match="refusing to send the API key"):
            list(api.iterate(api.domain_statistics("acct")))

    def test_a_lookalike_host_is_not_the_same_origin(self):
        for url in [
            "https://dashboard.nodemaven.com.evil.example/p2",
            "https://evil.example/dashboard.nodemaven.com/p2",
            # Userinfo: everything before the `@` is a login, so this one goes
            # to `evil.example` while reading as if it went to the dashboard.
            "https://dashboard.nodemaven.com@evil.example/p2",
        ]:
            api, _ = client((200, {"next": url, "data": [1]}))
            with pytest.raises(ApiError, match="refusing to send the API key"):
                list(api.iterate(api.domain_statistics("acct")))

    def test_the_default_port_written_out_is_the_same_origin(self):
        # The control on the rule, and the direction it is expensive to be wrong
        # in: `https://host` and `https://host:443` are one origin, a server
        # building paging links from its own absolute URI may emit the explicit
        # form behind a proxy, and this check has never run against the live API.
        # Comparing `netloc` as text would refuse a legitimate page.
        host = DEFAULT_BASE_URL.split("://", 1)[1]
        api, fake = client(
            (200, {"next": f"https://{host}:443/p2", "data": [1]}),
            (200, {"next": None, "data": [2]}),
        )
        assert list(api.iterate(api.domain_statistics("acct"))) == [1, 2]
        assert fake.calls[-1]["url"] == f"https://{host}:443/p2"

    def test_a_next_with_a_port_that_is_not_a_number_is_refused_and_does_not_crash(
        self,
    ):
        # `urlsplit(...).port` raises ValueError on a port that is not a number,
        # so without the catch the paging loop would die of a ValueError inside
        # the function added to make it safe - past a module that maps every
        # failure onto its own exception type.
        api, _ = client((200, {"next": "https://host:notaport/p2", "data": [1]}))
        with pytest.raises(ApiError, match="refusing to send the API key"):
            list(api.iterate(api.domain_statistics("acct")))

    def test_a_custom_base_url_moves_the_boundary_with_it(self):
        # The rule is "the host this client was pointed at", not a constant. A
        # self-hosted or staging dashboard has to page, and hard-coding the
        # production host would break it while looking like security.
        api, fake = client(
            (200, {"next": "https://staging.example.test/p2", "data": [1]}),
            (200, {"next": None, "data": [2]}),
            base_url="https://staging.example.test",
        )
        assert list(api.iterate(api.domain_statistics("acct"))) == [1, 2]
        assert fake.calls[-1]["url"] == "https://staging.example.test/p2"


class TestValidateAgainstTheLiveCatalogue:
    def test_a_country_in_the_catalogue_produces_no_complaints(self):
        api, _ = client(
            (200, {"next": None, "results": [{"code": "US"}]}),
            (200, {"next": None, "results": []}),
        )
        proxy = Proxy(login="acct", password="pw", country="us")
        assert api.validate(proxy) == []

    def test_a_country_that_is_not_there_is_named_along_with_the_gateways_answer(self):
        # This is the gap the empty `values` table leaves open: the SDK refuses
        # a parameter *name* it does not know and passes any *value* through, so
        # `country="zz"` builds a username and earns a 407 that does not say
        # which parameter was wrong - and reads as a credentials problem, which
        # is the whole reason naming the country here is worth the network call.
        api, _ = client(
            (200, {"next": None, "results": [{"code": "us"}]}),
            (200, {"next": None, "results": []}),
        )
        proxy = Proxy(login="acct", password="pw", country="zz")
        problems = api.validate(proxy)
        assert len(problems) == 1
        assert "407" in problems[0]
        assert "zz" in problems[0]

    def test_it_is_a_client_method_and_not_a_check_inside_proxy(self):
        # A refusal that ships in a release can be wrong forever, and the
        # catalogue moves. Asking the live catalogue cannot go stale, and it
        # costs a network call - so it has to be the caller's decision.
        assert not hasattr(Proxy(login="a", password="b"), "validate")

    def test_no_country_asks_the_catalogue_nothing(self):
        api, fake = client((200, {"results": []}))
        assert api.validate(Proxy(login="acct", password="pw")) == []
        assert fake.calls == []

    def test_country_any_is_not_a_place_and_is_skipped(self):
        api, _ = client(
            (200, {"next": None, "results": [{"code": "us"}]}),
            (200, {"next": None, "results": []}),
        )
        proxy = Proxy(login="acct", password="pw", country="any")
        assert api.validate(proxy) == []

    def test_the_connection_type_follows_the_proxys_own_type_parameter(self):
        # `type` selects the network rather than labelling it - measured
        # 2026-08-26, `type=mobile` draws mobile ASNs and `residential` does
        # not - so validating a mobile proxy against the residential catalogue
        # would refuse a country the mobile pool has.
        api, fake = client(
            (200, {"next": None, "results": [{"code": "us"}]}),
            (200, {"next": None, "results": []}),
        )
        proxy = Proxy(login="acct", password="pw", country="us", type="mobile")
        api.validate(proxy)
        assert "connection_type=mobile" in fake.calls[0]["url"]

    def test_an_unreadable_catalogue_is_a_complaint_and_not_a_pass(self):
        # The dangerous outcome is a validator that returns [] because it
        # understood nothing. It says so instead, and says whose bug it is.
        api, _ = client(
            (200, {"next": None, "results": ["not an object"]}),
            (200, {"next": None, "results": []}),
        )
        proxy = Proxy(login="acct", password="pw", country="us")
        problems = api.validate(proxy)
        assert len(problems) == 1
        assert "do not treat it as a pass" in problems[0]


class TestTheTransportSeam:
    def test_a_custom_transport_replaces_the_socket_entirely(self):
        # The seam is why this file needs no network. It is also the answer to
        # "why no async": a caller who needs one puts it here.
        seen = []

        def transport(method, url, headers, body):
            seen.append(url)
            return 200, b'{"ok": true}'

        assert Client(api_key="k", transport=transport).me() == {"ok": True}
        assert len(seen) == 1

    def test_the_default_transport_is_the_standard_library(self):
        # Zero required dependencies is a property worth a test, because the day
        # somebody imports `requests` here it will still pass every other case.
        import nodemaven.api as module

        assert module._urllib_transport.__module__ == "nodemaven.api"
        source = module.__file__
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        assert "import requests" not in text
        assert "import httpx" not in text

    def test_the_default_transport_disables_environment_proxies(self):
        # `ProxyHandler({})` is load-bearing. Left out, urlopen reads
        # http_proxy/https_proxy from the environment - set on exactly the
        # machines that use proxies - and an API call goes through a proxy
        # nobody asked for.
        import nodemaven.api as module

        with open(module.__file__, encoding="utf-8") as handle:
            text = handle.read()
        assert "ProxyHandler({})" in text

    def test_a_2xx_with_an_empty_body_is_an_empty_dict(self):
        # 204 and an empty 200 are both real answers to a DELETE. An empty dict
        # rather than None, so a caller can index the result of every method
        # without branching on which one they called.
        api, _ = client((204, b""))
        assert api.delete_whitelist_ip(1) == {}
