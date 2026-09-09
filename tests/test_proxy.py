"""Offline in full: no network, no credentials, no gateway.

These cases are the seed of the golden vectors the other language SDKs will run.
Anything asserted here is a statement about what a correct username is, not about
how this implementation happens to be written.
"""

from __future__ import annotations

import pytest

from nodemaven import (
    CredentialsError,
    ParamError,
    ProviderError,
    Proxy,
    available,
    load,
    load_file,
)

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


class TestThePort:
    """One rule for what a port is, in the one place that already held it.

    Both cases below were measured 2026-09-08 from an external review. The
    constructor did `int(raw_port)` and then tested the result for truthiness,
    while `check._port_number` two modules away already had the rule written
    out with the three defects that produced it recorded beside it. The fix is
    the import, not a new predicate.
    """

    @pytest.mark.parametrize("port", ["abc", "8o80", "\xb2", "12.5", " 8080"])
    def test_a_port_that_is_not_a_number_raises_this_packages_own_error(self, port):
        # Measured: `port='abc'` raised `ValueError: invalid literal for int()
        # with base 10: 'abc'`. A caller catching this package's exceptions did
        # not catch that, and the message names neither the parameter nor what a
        # port is. `'\xb2'` is in the list for the same reason it is in
        # `test_check.py`: `str.isdigit()` is True for it and `int()` refuses.
        # `' 8080'` is there because `int()` accepts leading whitespace and a
        # port with a space in it is a typo, not a port.
        with pytest.raises(CredentialsError, match="not a TCP port"):
            Proxy(**{**CREDS, "port": port})

    @pytest.mark.parametrize("port", [0, "0", -1, 65536, 70000, "99999999999999"])
    def test_a_port_outside_1_to_65535_says_what_is_wrong_with_it(self, port):
        # Measured: `port='0'` raised `CredentialsError` - the right class - with
        # the message "no gateway address ... pass host= and port=", although
        # the port *was* passed. A truthiness test standing in for a range check
        # turns 0 into "missing", and the sentence sends the caller to look at
        # the one thing they got right.
        with pytest.raises(CredentialsError, match="not a TCP port"):
            Proxy(**{**CREDS, "port": port})

    def test_a_port_from_the_environment_is_held_to_the_same_rule(self, monkeypatch):
        # The environment is where a port arrives as a string in real use, and
        # it was the path where `int()` was most likely to be handed something
        # that is not a number.
        monkeypatch.setenv("NODEMAVEN_PORT", "not-a-port")
        with pytest.raises(CredentialsError, match="not a TCP port"):
            Proxy(login="acct", password="pw", host="gate.example.com")

    def test_the_ports_a_caller_actually_uses_still_work(self):
        # The control. A guard that refuses a real port is worse than the defect
        # it replaces, and `1` and `65535` are the two the range check itself is
        # most likely to get wrong. The assertion reads `server` because there is
        # no `port` property: the port is a private slot, and the address is the
        # only public place its value appears.
        for port in (1, 8080, 65535, "8080"):
            proxy = Proxy(**{**CREDS, "port": port})
            assert proxy.server == f"gate.example.com:{int(port)}"


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

    def test_type_is_known_and_selects_the_mobile_pool(self):
        # Refusing this refused a product tier. It was missing from this list
        # until 2026-09-07, so a customer paying for mobile proxies could not
        # ask for them and the error they got said the gateway does not know
        # the parameter - the exact failure this package exists to prevent,
        # produced by the package.
        #
        # Probed from the VPS on 2026-08-26: a junk value is answered 407,
        # which an unrecognised name cannot produce - the negative control
        # `zzqqx` gives 200 and the positive control `filter` gives 407. Then
        # verified functionally, 5 requests per arm with a fresh sid and
        # `country=us`: `type=mobile` drew T-Mobile and Cellco ASNs where
        # `type=residential` and the unset arm drew wireline carriers only.
        assert "type" in load("nodemaven").known_params
        assert Proxy(type="mobile", **CREDS).username == "acct-type-mobile"


class TestTheReadmeShowsRealOutput:
    """The README quotes this message. This pins it, because a README showing a
    message the code no longer produces is worse than one showing none.

    Added 2026-09-07 after the README drifted: it listed nine parameter names
    here and the code produced ten, because `type` was added to the shipped
    definition and the quoted block was not regenerated. The Rust port carried
    this test from the start and it caught the same drift on its first run;
    this package did not have it, which is why the drift got as far as being
    committed to the source tree.
    """

    def test_the_unknown_parameter_message_is_quoted_verbatim(self):
        with pytest.raises(ParamError) as caught:
            Proxy(login="u", password="p", contry="us")
        assert str(caught.value) == (
            "NodeMaven does not know the parameter 'contry': it is answered "
            "with 200 and dropped, so the connection would succeed and your "
            "setting would NOT be applied. Known: ['city', 'country', "
            "'filter', 'ipv4', 'isp', 'region', 'sid', 'speed', 'ttl', 'type']"
        )


class TestValuesAreFoldedToTheFormTheGatewayEmits:
    """The fold to the wire form, and the refusal that completes it.

    The evidence for the fold is in the provider TOML: a username this gateway
    generated for a real account carries ``region-district_of_columbia``, and
    the vendor's own client applies the same transformation. So these cases
    assert a form the gateway has been seen to emit, not one that looked tidy.

    The refusal is the other half. A parameter nobody folds cannot carry
    whitespace either, because there is no spelling of a space in a proxy
    username that works - so between the two, no value with whitespace in it
    can reach the wire by any path.
    """

    def test_it_reproduces_a_username_the_gateway_generated(self):
        # The case this whole class exists for. The login is `acct` here and
        # the real one is not written down anywhere in this repository;
        # everything to the right of it is the generated string unchanged.
        # Before the fold this same call produced
        # `region-District of Columbia`, which is not a thing that can be sent.
        proxy = Proxy(
            country="us",
            region="District of Columbia",
            sid="bfd1c859433a4",
            filter="medium",
            **CREDS,
        )
        assert proxy.username == (
            "acct-country-us-region-district_of_columbia"
            "-sid-bfd1c859433a4-filter-medium"
        )

    def test_a_space_becomes_an_underscore(self):
        assert Proxy(city="New York", **CREDS).username == "acct-city-new_york"

    def test_case_is_folded(self):
        assert Proxy(country="US", **CREDS).username == "acct-country-us"

    def test_the_stored_value_is_the_folded_one(self):
        # A proxy reporting `District of Columbia` while sending
        # `district_of_columbia` would let two callers with the same visible
        # configuration sit on different sticky sessions and see no reason why.
        proxy = Proxy(city="New York", country="US", **CREDS)
        assert proxy.params == {"city": "new_york", "country": "us"}

    def test_folding_a_folded_value_changes_nothing(self):
        # Idempotence is what makes `replace` safe to chain.
        once = Proxy(city="New York", **CREDS)
        twice = once.replace(city=once.params["city"])
        assert once.username == twice.username

    def test_surrounding_whitespace_is_trimmed_rather_than_refused(self):
        assert Proxy(country="  US  ", **CREDS).username == "acct-country-us"

    def test_a_value_of_only_whitespace_is_refused_as_empty(self):
        # It trims to empty, and the empty refusal is the more useful of the
        # two messages: the gateway does not answer an empty value at all, it
        # hangs for twenty seconds.
        with pytest.raises(ParamError, match="empty value"):
            Proxy(country="   ", **CREDS)

    def test_a_parameter_nobody_folds_refuses_whitespace_instead(self):
        with pytest.raises(ParamError, match="contains whitespace") as caught:
            Proxy(sid="order 4417", **CREDS)
        # The message names what is folded, so the caller can tell a refusal
        # from a parameter that would have been converted.
        assert "'region'" in str(caught.value)

    @pytest.mark.parametrize("bad", [" ", "\t", "\n", "\r", "\v", "\f"])
    def test_every_ascii_whitespace_character_is_refused(self, bad):
        # The set is spelled out in providers.py rather than delegated -
        # `str.isspace` is Unicode-wide and Rust's `is_ascii_whitespace`
        # excludes the vertical tab that Python's includes, so a shared
        # contract cannot use either name.
        with pytest.raises(ParamError, match="contains whitespace"):
            Proxy(sid=f"a{bad}b", **CREDS)

    def test_a_no_break_space_is_not_ascii_whitespace_and_passes(self):
        # Deliberate rather than an oversight. A no-break space is a character
        # the gateway has never been asked about, and the ASCII set is the one
        # four languages agree on without depending on their Unicode tables.
        #
        # Written as an escape and not as the character. As a literal this
        # test passes for the right reason only until an editor or a
        # formatter normalises the byte to an ordinary space, at which point
        # it asserts the opposite of what it says - or gets "fixed".
        assert Proxy(sid="a\u00a0b", **CREDS).username == "acct-sid-a\u00a0b"

    def test_a_session_id_keeps_its_case(self):
        # `sid` is excluded from the fold on purpose: a session id is opaque
        # and caller-chosen, and lowercasing it would silently move the caller
        # to a different sticky session than the one they named.
        assert Proxy(sid="Order4417", **CREDS).username == "acct-sid-Order4417"
        assert Proxy(**CREDS).session("Order4417").username == "acct-sid-Order4417"

    def test_filter_and_ttl_keep_their_case(self):
        # The vendor's client does not fold `filter`, not even to lower case,
        # and the generated username that evidences the fold says nothing
        # either way because `medium` was already lower case. Folding it would
        # be a guess.
        proxy = Proxy(filter="MEDIUM", ttl="10M", **CREDS)
        assert proxy.username == "acct-filter-MEDIUM-ttl-10M"

    def test_the_fold_is_ascii_only(self):
        # The Turkish dotted capital I lower-cases to two code points under
        # full Unicode rules in some languages and to one in others, so a
        # vector built on it would fail in one SDK for a reason that has
        # nothing to do with proxies. `str.lower()` would fold this; the
        # translate table does not.
        assert Proxy(city="\u0130stanbul", **CREDS).username == "acct-city-\u0130stanbul"

    def test_a_definition_that_folds_nothing_still_refuses_whitespace(self, tmp_path):
        # The whitespace refusal is about what a username can carry rather than
        # about any gateway's dialect, so it applies with no `normalize` at all.
        path = tmp_path / "plain.toml"
        path.write_text('label = "Plain"\nknown_params = ["country"]\n', encoding="utf-8")
        provider = load_file(path)
        assert Proxy(provider=provider, country="US", **CREDS).username == "acct-country-US"
        with pytest.raises(ParamError, match="contains whitespace"):
            Proxy(provider=provider, country="New York", **CREDS)


class TestADefinitionCannotDeclareAnImpossibleFold:
    """Refused when it loads, not when somebody calls it.

    Same principle as the checks already there: a declaration that reads like a
    working setting and can never fire is the class of mistake this package
    exists to make loud.
    """

    def test_normalizing_a_parameter_that_is_not_known_is_refused(self, tmp_path):
        path = tmp_path / "wrong.toml"
        path.write_text(
            'label = "Wrong"\n'
            'known_params = ["country"]\n'
            'normalize = ["country", "city"]\n',
            encoding="utf-8",
        )
        with pytest.raises(ProviderError, match="normalizes"):
            load_file(path)

    def test_folding_into_the_separator_is_refused(self, tmp_path):
        # The fold inserts an underscore, so a gateway that separates on one
        # would have the value cut in half by the very step meant to make it
        # sendable. The caller would be blamed for input that is correct.
        path = tmp_path / "underscored.toml"
        path.write_text(
            'label = "Underscored"\n'
            'known_params = ["city"]\n'
            'separator = "_"\n'
            'normalize = ["city"]\n',
            encoding="utf-8",
        )
        with pytest.raises(ProviderError, match="Pick one"):
            load_file(path)


class TestWhatAStatusMeansIsPerGateway:
    """`connect_reactions` - the machine-readable half of the reactions table.

    A status code on this gateway is not a diagnosis. Five parameters answer a
    value the gateway will not take with 407, which reads as a credentials
    problem and is not one, so the translation from a code to a sentence is part
    of the dialect and belongs beside the separators rather than in a dict in a
    module. Four languages read this schema, and this is the third key added to
    it before the golden vectors freeze.
    """

    def test_the_shipped_definition_explains_the_misleading_407(self):
        meaning = load("nodemaven").reaction(407)
        assert meaning is not None
        assert "NOT your credentials" in meaning

    def test_a_200_says_what_it_does_not_prove(self):
        # The one entry that is not about a failure, and the reason it exists:
        # an unrecognised parameter name is also answered 200 and dropped, so a
        # 200 means the parameters were accepted and not that they were applied.
        meaning = load("nodemaven").reaction(200)
        assert meaning is not None
        assert "not that they were all" in meaning

    def test_each_reaction_names_the_parameters_it_can_come_from(self):
        # Naming the parameter is the only thing the status code itself does
        # not do. It is deliberately not "four parameters, four codes":
        # measured 2026-09-08, `region`, `city` and `isp` all answer 406, so
        # the 406 entry has to name all three.
        provider = load("nodemaven")
        ambiguous = provider.reaction(406)
        assert "region" in ambiguous
        assert "city" in ambiguous
        assert "isp" in ambiguous
        assert "city" in provider.reaction(500)
        assert "isp" in provider.reaction(410)
        assert "country" in provider.reaction(407)

    def test_the_500_names_the_missing_region_and_not_an_unreachable_city(self):
        # This entry said the opposite for most of 2026-09-08 - that every
        # `city` tried was refused and the value should be treated as unusable.
        # Six CONNECTs the same day: `us`/`louisiana`/`abbeville` answers 200
        # and the same city without its region answers 500, so the 500 is an
        # incomplete request and `city` works. All seven earlier values had been
        # sent without a region, held fixed across every arm and therefore
        # invisible in the comparison between them.
        meaning = load("nodemaven").reaction(500)
        assert "region" in meaning
        assert "unusable" not in meaning

    def test_the_406_does_not_claim_to_know_which_parameter_it_means(self):
        # A junk `region`, a junk `isp` and `charter` - a real ISP - all answer
        # 406, so the entry must neither say which parameter was refused nor
        # tell a caller their name was misspelled. This is the row asked to
        # report an ambiguity rather than a diagnosis, and the one most likely
        # to be tidied into a confident sentence later.
        meaning = load("nodemaven").reaction(406)
        assert "charter" in meaning
        assert "unavailable" in meaning

    def test_the_410_says_how_narrow_its_sample_is(self):
        # One ISP produced it. An entry stating a rule from one value is the
        # same mistake as a default sentence for an unmeasured status.
        meaning = load("nodemaven").reaction(410)
        assert "comcast" in meaning
        assert "one value" in meaning

    def test_a_status_nobody_measured_has_no_entry_rather_than_a_guess(self):
        # The table is only as long as the measurements. A default sentence
        # here would be this package inventing a diagnosis, which is the thing
        # it exists to stop the gateway doing.
        assert load("nodemaven").reaction(502) is None

    def test_the_keys_are_strings_because_no_wire_format_has_integer_keys(
        self, tmp_path
    ):
        # TOML has no integer keys and neither does JSON, and the golden
        # vectors are JSON. Storing them as strings and converting at the
        # lookup is one line; the alternative is a schema that cannot round
        # trip through the format the four SDKs share.
        path = tmp_path / "stringkeys.toml"
        path.write_text(
            'label = "Keys"\n'
            'known_params = ["country"]\n'
            "[connect_reactions]\n"
            '407 = "not the password"\n',
            encoding="utf-8",
        )
        provider = load_file(path)
        assert set(provider.connect_reactions) == {"407"}
        assert provider.reaction(407) == "not the password"

    def test_an_empty_explanation_is_refused_at_load(self, tmp_path):
        # Same principle as an empty `values` list: a key that is present and
        # says nothing reads like a working entry and can only ever print a
        # blank line next to a status code.
        path = tmp_path / "blank.toml"
        path.write_text(
            'label = "Blank"\n'
            'known_params = ["country"]\n'
            "[connect_reactions]\n"
            '407 = ""\n',
            encoding="utf-8",
        )
        with pytest.raises(ProviderError):
            load_file(path)

    def test_a_definition_need_not_have_the_table_at_all(self, tmp_path):
        path = tmp_path / "bare.toml"
        path.write_text(
            'label = "Bare"\nknown_params = ["country"]\n', encoding="utf-8"
        )
        provider = load_file(path)
        assert provider.connect_reactions == {}
        assert provider.reaction(407) is None
