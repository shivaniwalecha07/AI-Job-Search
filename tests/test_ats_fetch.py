from job_agent.connectors.ats_fetch import (
    html_to_text,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
)


def test_parse_greenhouse_variants():
    assert parse_greenhouse("https://job-boards.greenhouse.io/schonfeld/jobs/8180089?utm=x") == ("schonfeld", "8180089")
    assert parse_greenhouse("https://boards.greenhouse.io/acme/jobs/12345") == ("acme", "12345")
    assert parse_greenhouse("https://www.zipline.com/roles?gh_jid=7986848003") is None  # no board


def test_parse_lever():
    assert parse_lever("https://jobs.lever.co/brex/2b8f1c2d-0000-4a1a-9b2c-abcdef012345") == (
        "brex", "2b8f1c2d-0000-4a1a-9b2c-abcdef012345")
    assert parse_lever("https://example.com/x") is None


def test_parse_ashby():
    assert parse_ashby("https://jobs.ashbyhq.com/rivianvw.tech/c5c0f2e3-ae78-4ca6-94f8-b6940d3cdb69/application") == (
        "rivianvw.tech", "c5c0f2e3-ae78-4ca6-94f8-b6940d3cdb69")


def test_html_to_text_strips_and_unescapes():
    raw = "&lt;p&gt;We are &lt;b&gt;unable to sponsor&lt;/b&gt; visas.&lt;/p&gt;&lt;p&gt;Apply now.&lt;/p&gt;"
    txt = html_to_text(raw)
    assert "unable to sponsor" in txt
    assert "<" not in txt and "&lt;" not in txt
    assert "Apply now." in txt


def test_html_to_text_truncates():
    assert len(html_to_text("x" * 20000)) <= 12000


class _FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return _FakeResp(200, self._payload)


def test_fetch_description_greenhouse_extracts_and_feeds_sponsorship():
    from job_agent.connectors.ats_fetch import fetch_description
    from job_agent.sponsorship.assessor import assess
    from job_agent.schemas.core import SponsorshipStatus

    payload = {"content": "&lt;p&gt;Responsibilities: build APIs in Python and AWS.&lt;/p&gt;"
                          "&lt;p&gt;We are unable to provide visa sponsorship for this role.&lt;/p&gt;"}
    client = _FakeClient(payload)
    desc = fetch_description("https://job-boards.greenhouse.io/acme/jobs/123", "greenhouse", client=client)
    assert "unable to provide visa sponsorship" in desc
    assert "boards-api.greenhouse.io/v1/boards/acme/jobs/123" in client.calls[0]

    # Downstream: the assessor now reads a real signal instead of defaulting to UNKNOWN.
    a = assess({"description": desc, "employment_type": "internship", "source_url": "http://x"})
    assert a.status == SponsorshipStatus.NO


def test_fetch_description_unsupported_ats_returns_none():
    from job_agent.connectors.ats_fetch import fetch_description

    assert fetch_description("https://example.com/x", "workday") is None
