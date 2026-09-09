"""Every output the README quotes, compared against the real thing.

This file exists because the one quotation in the README that had no test drifted
without anyone noticing: it listed nine parameter names where the code produced
ten, and the Rust port's equivalent test is what caught it. The rule that came
out of that is the reason this file is here - **a README that quotes real output
needs a test per quotation, or the quotation is a comment.**

Comparisons collapse whitespace. That is deliberate and it is the only slack
allowed: a paragraph in a fenced block has to be re-wrappable to stay readable at
80 columns, and nothing else about it may change. Every word still has to match.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from nodemaven import Proxy, load
from nodemaven.check import Check

README = Path(__file__).resolve().parent.parent / "README.md"


def flat(text: str) -> str:
    return " ".join(text.split())


def _headings(readme: str) -> set:
    """Every heading as GitHub would anchor it: lowered, punctuation dropped."""
    return {
        re.sub(r"[^a-z0-9 -]", "", line.lstrip("#").strip().lower()).replace(" ", "-")
        for line in readme.splitlines()
        if line.startswith("#")
    }


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prose(readme: str) -> str:
    """The README with its HTML comments removed.

    Assertions about what the file *says* run against this rather than against
    the raw text. The surviving comments are notes to whoever edits the file -
    which links must stay absolute, which blocks a test pins - and none of them
    is prose a reader sees, so counting them as prose would let an editing note
    satisfy or break an assertion about the documentation.
    """
    return re.sub(r"<!--.*?-->", "", readme, flags=re.DOTALL)


@pytest.fixture(scope="module")
def blocks(readme: str):
    """Every fenced block in the file, with its language tag."""
    return re.findall(r"```([a-z]*)\n(.*?)```", readme, re.DOTALL)


class TestTheReadmeIsSelfConsistent:
    def test_it_no_longer_claims_to_open_no_socket(self, prose: str):
        # "This library opens no socket" was true of every version up to 0.1.2
        # and false the moment `check()` landed. Pinned as a test because it is
        # the kind of sentence that gets restored by somebody tidying the intro.
        #
        # The record of the correction lives in CLAUDE.md and the CHANGELOG, not
        # in the README: shipped documentation describes the product as it is,
        # and a reader of the package has no use for what it used to say.
        assert "This library opens no socket" not in prose
        assert "`Proxy` opens no socket" in prose

    def test_it_no_longer_claims_nothing_is_raised_from_a_response(
        self, prose: str
    ):
        assert "nothing here sends one" not in prose

    def test_the_account_api_separates_what_was_called_from_what_was_not(
        self, readme: str
    ):
        # Documenting a call with an example is a claim that it works, so the
        # section has to say which calls that claim rests on. Until 2026-09-08
        # the answer was "none of them" and this test pinned the words
        # "transcribed, not measured". Calls were then sent to the live API and
        # the paragraph had to change - which is exactly what it was pinned for,
        # and it is pinned again for the same reason: the next call that gets
        # measured moves the boundary again.
        #
        # It moved a second time on 2026-09-09, in the other direction. The
        # section used to argue that transcribed paths were safe to ship because
        # a wrong one earns a 404; this host answers an unrouted path with 200
        # and the dashboard's own HTML, so that argument was never true here.
        # The retraction is pinned too, because the tempting edit is to delete a
        # wrong sentence rather than to say what it cost.
        section = readme.split("## Account API", 1)[1].split("\n## ", 1)[0]
        assert "measured" in section and "transcribed" in section
        assert "still never been called" in section
        assert "negative control" in section
        # The five are named. A count with no names cannot be checked by a
        # reader, and cannot be checked here either.
        for path in ("users/me", "countries", "regions", "cities", "isps"):
            assert f"`{path}`" in section, path

    def test_every_error_class_the_package_exports_is_in_the_table(
        self, readme: str
    ):
        import nodemaven

        exported = [
            name
            for name in nodemaven.__all__
            if name.endswith("Error") and name != "NodeMavenError"
        ]
        table = readme.split("## Errors", 1)[1].split("##", 1)[0]
        missing = [name for name in exported if f"`{name}`" not in table]
        assert missing == [], f"exported and undocumented: {missing}"

    def test_the_nav_line_points_at_headings_that_exist(self, readme: str):
        nav = readme.split("\n\n</div>", 1)[0].rsplit("\n", 1)[1]
        anchors = re.findall(r"\]\(#([a-z0-9-]+)\)", nav)
        assert anchors, "the nav line was not found, so nothing was checked"
        assert set(anchors) <= _headings(readme), set(anchors) - _headings(readme)

    def test_every_anchor_in_the_body_points_at_a_heading_too(self, readme: str):
        # Widened from the nav line after a section was renamed and two links
        # elsewhere in the file went on pointing at the old anchor. GitHub
        # renders a dead in-page link as ordinary text that does nothing when
        # clicked - no 404, no warning - so nothing but this would have said so.
        anchors = set(re.findall(r"\]\(#([a-z0-9-]+)\)", readme))
        assert len(anchors) > 5, "the anchor scan found almost nothing"
        assert anchors <= _headings(readme), anchors - _headings(readme)


class TestTheParameterTable:
    def test_every_known_parameter_has_a_row(self, readme: str):
        # The table is what a developer reads instead of the shipped TOML. A
        # parameter missing from it is reachable only by reading source, which is
        # what the table was added to stop.
        table = readme.split("| parameter |", 1)[1].split("\n\n", 1)[0]
        for name in load("nodemaven").known_params:
            assert f"`{name}`" in table, name

    def test_no_row_names_a_parameter_the_gateway_does_not_know(
        self, readme: str
    ):
        # The other direction, and the one that matters more: a documented
        # parameter this package refuses is a promise it breaks. `norotate` was
        # exactly this between 2026-08-21 and 2026-08-26.
        table = readme.split("| parameter |", 1)[1].split("\n\n", 1)[0]
        known = load("nodemaven").known_params
        for row in table.splitlines():
            cells = [cell.strip() for cell in row.split("|")]
            if len(cells) < 3 or not cells[1].startswith("`"):
                continue
            assert cells[1].strip("`") in known, cells[1]

    def test_the_ttl_values_it_names_are_the_ones_the_definition_names(
        self, readme: str
    ):
        # `ttl` is the only parameter with measured accepted values, measured
        # refused values, and no `values` entry to enforce either - a list of
        # four would refuse a fifth the gateway takes. So the README and the
        # definition's notes are the only carriers of the unit rule, and nothing
        # else makes them agree.
        #
        # Read out of the table rather than listed here: a list in this file
        # would be a third copy of the same contract.
        table = readme.split("| parameter |", 1)[1].split("\n\n", 1)[0]
        row = next(
            line for line in table.splitlines() if line.startswith("| `ttl` |")
        )
        named = re.findall(r"`([^`]+)`", row.rsplit("|", 2)[1])
        assert len(named) >= 2, named

        notes = load("nodemaven").notes
        assert [value for value in named if value not in notes] == []


class TestTheUnknownParameterMessage:
    def test_the_readme_quotes_it_word_for_word(self, readme: str):
        # This is the quotation that drifted, and the test that would have caught
        # it. It is built from the shipped definition, so adding a parameter to
        # the TOML fails here until the README is updated too.
        #
        # Every block is checked, not the first one. This test used to pin
        # `quoting[0]` against a message raised from a typo hardcoded here, so it
        # verified whichever block happened to come first and ignored the rest. A
        # second quotation was then added to the quickstart with a different
        # typo, and the version of the paragraph before it had an invented
        # message in it - "Did you mean 'filter'?", which this library does not
        # say and never has. That is the failure this test exists to catch and it
        # caught it, but only because the new block landed first in the file.
        from nodemaven import ParamError

        blocks = re.findall(r"```[a-z]*\n(.*?)```", readme, re.DOTALL)
        quoting = [body for body in blocks if "ParamError:" in body]
        assert quoting, "the README stopped quoting the message, so nothing was checked"

        for body in quoting:
            typo = re.search(r"does not know the parameter '([^']+)'", flat(body))
            assert typo, f"a ParamError block naming no parameter:\n{body}"
            with pytest.raises(ParamError) as caught:
                Proxy(login="u", password="p", **{typo.group(1): "us"})
            assert flat(str(caught.value)) in flat(body)


class TestTheFoldedRegionExample:
    def test_the_username_in_the_readme_is_what_the_code_builds(self, readme: str):
        # `region-district_of_columbia` is not an invention: it is the form the
        # dashboard itself emitted in a username for a real account, read
        # 2026-09-07. The example is the one place the README shows the fold, so
        # it is the one place a change to the fold has to be reflected.
        built = Proxy(
            login="u", password="p", region="District of Columbia"
        ).username
        assert built == "u-region-district_of_columbia"
        assert built in readme


class TestTheCheckOutput:
    """The two blocks under "Asking the gateway".

    Built here rather than captured from the gateway, and that is what makes them
    checkable: a `Check` is a plain frozen object, so the README is quoting a
    real `__str__` of a real instance and not a hand-typed approximation of one.
    """

    def test_the_200_line(self, readme: str):
        result = Check(
            status=200,
            reason="Connection established",
            server="gate.nodemaven.com:8080",
            elapsed=0.42,
            headers={"x-proxy-exit-ip": "203.0.113.7"},
            exit_ip="203.0.113.7",
            meaning=load("nodemaven").reaction(200),
        )
        assert flat(str(result)) in flat(readme)

    def test_the_407_block_including_the_gateways_own_explanation(
        self, readme: str
    ):
        # The explanation comes from the provider definition, so this asserts the
        # README and the TOML agree. They are two files and one of them is
        # published to PyPI.
        result = Check(
            status=407,
            reason="Proxy Authentication Required",
            server="gate.nodemaven.com:8080",
            elapsed=0.19,
            headers={},
            meaning=load("nodemaven").reaction(407),
        )
        assert flat(str(result)) in flat(readme)

    def test_a_200s_explanation_is_not_printed_and_the_readme_says_why(
        self, readme: str
    ):
        # `__str__` shows the meaning only for a non-200, so the 200 block above
        # must not carry the 200 explanation. This pins the asymmetry rather than
        # leaving it as a coincidence of the two fixtures.
        result = Check(
            status=200,
            reason="Connection established",
            server="gate.nodemaven.com:8080",
            elapsed=0.42,
            headers={},
            meaning=load("nodemaven").reaction(200),
        )
        assert "\n" not in str(result)

    def test_the_default_target_named_in_the_readme_is_the_default(
        self, readme: str
    ):
        from nodemaven.check import DEFAULT_TARGET

        assert f"`{DEFAULT_TARGET}`" in readme

    def test_the_documented_timeout_is_the_default(self, readme: str):
        import inspect

        from nodemaven.check import connect

        default = inspect.signature(connect).parameters["timeout"].default
        assert default == 15.0
        assert "defaults to 15 seconds" in readme


class TestTheReferenceMatchesTheCode:
    """The Reference section is a contract, so it gets the same treatment as a
    quoted output: it is compared against the real thing rather than read.

    Added with the section itself, 2026-09-08. The section exists because an
    external review said the documentation was overloaded with justifications;
    measuring that turned up the sharper version of the complaint - the package
    exports 18 names and the README gave a signature for none of them, so for
    several calls the rationale was the only coverage there was. A reference
    written once and never checked would have been a worse answer than no
    reference, because it reads as authoritative.
    """

    def test_the_proxy_signature_names_every_real_argument(self, readme: str):
        import inspect

        block = readme.split("### `Proxy`", 1)[1].split("```", 2)[1]
        for name in inspect.signature(Proxy.__init__).parameters:
            if name == "self":
                continue
            assert name in block, name

    def test_the_client_signature_names_every_real_argument(self, readme: str):
        import inspect

        from nodemaven import Client

        block = readme.split("### `Client` and `Page`", 1)[1].split("```", 2)[1]
        for name in inspect.signature(Client.__init__).parameters:
            if name == "self":
                continue
            assert name in block, name

    def test_every_public_proxy_call_is_in_the_reference(self, readme: str):
        section = readme.split("### `Proxy`", 1)[1].split("### `Check`", 1)[0]
        missing = [
            name
            for name in dir(Proxy)
            if not name.startswith("_") and f"`.{name}" not in section
        ]
        assert missing == [], f"public on Proxy and undocumented: {missing}"

    def test_every_public_client_call_is_in_the_reference(self, readme: str):
        from nodemaven import Client

        section = readme.split("### `Client` and `Page`", 1)[1]
        section = section.split("### `Provider`", 1)[0]
        missing = [
            name
            for name in dir(Client)
            if not name.startswith("_") and f"`.{name}" not in section
        ]
        assert missing == [], f"public on Client and undocumented: {missing}"

    def test_every_exported_name_appears_in_the_readme(self, readme: str):
        # The gap that produced this test: `available()` was exported and
        # appeared nowhere in 625 lines, so the only way to find it was to read
        # `__init__.py`.
        import nodemaven

        missing = [
            name
            for name in nodemaven.__all__
            if not name.startswith("_") and f"`{name}" not in readme
        ]
        assert missing == [], f"exported and unmentioned: {missing}"


class TestTheAttributesTheReadmePromises:
    def test_every_field_a_check_carries_is_in_the_reference_table(
        self, readme: str
    ):
        """Derived from the dataclass, not from a list written here.

        This test used to carry the seven names by hand and look for
        ``result.<name>`` anywhere in the file, which matched a code block under
        "Asking the gateway" that said the same thing as the reference table.
        Two copies of one contract with the test pinning one of them is how the
        other drifts - it is the failure this whole file was written after. The
        block is gone, the table is the one copy, and the names now come from
        the type so that adding a field fails here until it is documented.
        """
        import dataclasses

        names = [field.name for field in dataclasses.fields(Check)]
        # `ok` is a property rather than a field, and is the one a caller reads
        # first, so it is named explicitly rather than left to the derivation.
        names.append("ok")
        table = readme.split("### `Check`", 1)[1].split("###", 1)[0]
        missing = [name for name in names if f"`.{name}`" not in table]
        assert missing == [], f"a Check field the reference does not list: {missing}"

    @pytest.mark.parametrize(
        "attribute",
        ["ok", "status", "reason", "exit_ip", "elapsed", "headers", "meaning"],
    )
    def test_each_one_exists_on_check(self, attribute, readme: str):
        result = Check(
            status=200, reason="OK", server="h:1", elapsed=0.0, headers={}
        )
        assert hasattr(result, attribute)

    @pytest.mark.parametrize(
        "method",
        [
            "me",
            "countries",
            "regions",
            "cities",
            "isps",
            "isp_regions",
            "isp_cities",
            "zip_codes",
            "zip_code_regions",
            "zip_code_cities",
            "statistics_data",
            "statistics_requests",
            "domain_statistics",
            "sub_users",
            "create_sub_user",
            "update_sub_user",
            "delete_sub_user",
            "reset_sub_user_usage",
            "whitelist_ips",
            "whitelist_ip",
            "upsert_whitelist_ip",
            "delete_whitelist_ip",
            "iterate",
            "validate",
        ],
    )
    def test_every_client_method_the_readme_shows_exists(self, method, readme: str):
        from nodemaven import Client

        assert hasattr(Client, method)
        assert f"client.{method}(" in readme or f"`{method}()`" in readme


class TestTheEnvironmentVariableNames:
    @pytest.mark.parametrize(
        "name",
        [
            "NODEMAVEN_LOGIN",
            "NODEMAVEN_PASSWORD",
            "NODEMAVEN_HOST",
            "NODEMAVEN_PORT",
            "NODEMAVEN_APIKEY",
        ],
    )
    def test_each_one_the_readme_names_is_read_by_the_code(self, name, readme: str):
        # A documented variable the code does not read is worse than an
        # undocumented one: it silently does nothing and the developer concludes
        # their credentials are wrong.
        import nodemaven.api
        import nodemaven.proxy

        sources = "".join(
            Path(module.__file__).read_text(encoding="utf-8")
            for module in (nodemaven.proxy, nodemaven.api)
        )
        assert name in readme
        assert name in sources
