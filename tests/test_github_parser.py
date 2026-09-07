"""Parser tests against the real README HTML shape (continuation, multi-location, closed)."""
from job_agent.connectors.github_list import parse_readme

SAMPLE = """
<table>
<thead>
<tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th><th>Age</th></tr>
</thead>
<tbody>
<tr>
<td><strong><a href="https://simplify.jobs/c/Schonfeld">Schonfeld</a></strong></td>
<td>Software Engineering Intern</td>
<td>NYC</td>
<td><div align="center"><a href="https://job-boards.greenhouse.io/schonfeld/jobs/8180089?ref=Simplify"><img src="x" alt="Apply"></a> <a href="https://simplify.jobs/p/1679d1fa-953d-4b83-b4f5-e2e3a9f4cdd0"><img src="y" alt="Simplify"></a></div></td>
<td>0d</td>
</tr>
<tr>
<td>↳</td>
<td>Technology Intern - DMFI</td>
<td>NYC</td>
<td><div align="center"><a href="https://job-boards.greenhouse.io/schonfeld/jobs/8171772?ref=Simplify"><img src="x" alt="Apply"></a></div></td>
<td>1d</td>
</tr>
<tr>
<td>🔥 <strong><a href="https://simplify.jobs/c/PayPal">PayPal</a></strong></td>
<td>Software Engineer Intern</td>
<td>Austin, TX<br>San Jose, CA<br>Chicago, IL</td>
<td><div align="center"><a href="https://paypal.eightfold.ai/careers/job/274922260559?ref=Simplify"><img src="x" alt="Apply"></a></div></td>
<td>2d</td>
</tr>
<tr>
<td><strong><a href="https://simplify.jobs/c/ClosedCo">ClosedCo</a></strong></td>
<td>SWE Intern 🔒</td>
<td>Remote</td>
<td>🔒</td>
<td>30d</td>
</tr>
</tbody>
</table>
"""


def _by_company(records):
    out = {}
    for r in records:
        out.setdefault(r.payload["company"], []).append(r)
    return out


def test_parses_all_rows_including_closed():
    records = parse_readme(SAMPLE, "github:test", "http://example/README.md")
    assert len(records) == 4


def test_continuation_inherits_company():
    records = parse_readme(SAMPLE, "github:test", "http://example/README.md")
    schonfeld = [r for r in records if r.payload["company"] == "Schonfeld"]
    assert len(schonfeld) == 2
    assert schonfeld[1].payload["role"] == "Technology Intern - DMFI"


def test_apply_url_skips_simplify_and_detects_ats():
    records = parse_readme(SAMPLE, "github:test", "http://example/README.md")
    first = records[0].payload
    assert "greenhouse.io" in first["apply_url"]
    assert "simplify.jobs" not in first["apply_url"]
    assert first["ats"] == "greenhouse"
    assert first["ats_job_id"] == "8180089"


def test_multi_location_split():
    records = parse_readme(SAMPLE, "github:test", "http://example/README.md")
    paypal = _by_company(records)["PayPal"][0].payload
    assert paypal["locations"] == ["Austin, TX", "San Jose, CA", "Chicago, IL"]
    assert paypal["ats"] == "eightfold"


def test_emoji_stripped_from_company_and_role():
    records = parse_readme(SAMPLE, "github:test", "http://example/README.md")
    paypal = _by_company(records)["PayPal"][0].payload
    assert paypal["company"] == "PayPal"  # 🔥 stripped
    closed = _by_company(records)["ClosedCo"][0].payload
    assert closed["role"] == "SWE Intern"  # 🔒 stripped
    assert closed["is_closed"] is True


# ---- Markdown pipe-table format (e.g. vanshb03) ----
SAMPLE_MD = """
| Company | Role | Location | Application/Link | Date Posted |
| ------- | ---- | -------- | ---------------- | ----------- |
| Vertiv | Product Management Intern 🛂 | Westerville, OH | <a href="https://egup.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/20278933?utm_source=github-vansh"><img src="x.png" alt="Apply"></a> | Aug 21 |
| ↳ | Product Management Intern, MBA 🛂 | Delaware, OH | <a href="https://egup.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX/job/20278958?utm_source=github-vansh"><img src="x.png" alt="Apply"></a> | Aug 21 |
| **[Ramp](https://ramp.com)** | Software Engineer Intern | New York, NY | <a href="https://job-boards.greenhouse.io/ramp/jobs/4512345"><img src="x.png" alt="Apply"></a> | Sep 05 |
"""


def test_markdown_table_parses():
    records = parse_readme(SAMPLE_MD, "github:vansh", "http://example/README.md")
    assert len(records) == 3  # header + separator skipped


def test_markdown_plaintext_and_continuation_company():
    records = parse_readme(SAMPLE_MD, "github:vansh", "http://example/README.md")
    assert records[0].payload["company"] == "Vertiv"
    assert records[1].payload["company"] == "Vertiv"  # ↳ inherits
    assert records[1].payload["role"] == "Product Management Intern, MBA"  # 🛂 stripped


def test_markdown_bold_link_company():
    records = parse_readme(SAMPLE_MD, "github:vansh", "http://example/README.md")
    ramp = records[2].payload
    assert ramp["company"] == "Ramp"
    assert ramp["ats"] == "greenhouse"
    assert ramp["ats_job_id"] == "4512345"


def test_markdown_date_string_parsed():
    records = parse_readme(SAMPLE_MD, "github:vansh", "http://example/README.md")
    assert records[0].payload["posting_date"] is not None  # "Aug 21" -> a real date
    assert records[0].payload["ats"] == "oracle"
