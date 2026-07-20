from radar.model import Company
from radar.outputs.people_fmt import people_md


def test_structured_people_render_as_markdown_links():
    c = Company(
        name="X",
        people=[
            {"name": "Jane Doe", "role": "CEO", "linkedin": "https://linkedin.com/in/janedoe"},
            {"name": "Sam Roe", "role": "CTO", "linkedin": None},
        ],
    )
    md = people_md(c)
    assert "[Jane Doe](https://linkedin.com/in/janedoe) (CEO)" in md
    assert "Sam Roe (CTO)" in md  # no link when linkedin is null
    assert "](" in md  # at least one link present


def test_falls_back_to_key_people_string():
    c = Company(name="X", key_people="Only Name (Founder)")
    assert people_md(c) == "Only Name (Founder)"


def test_empty_when_no_people():
    assert people_md(Company(name="X")) == ""
