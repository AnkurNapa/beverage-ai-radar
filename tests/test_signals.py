from radar.signals import parse_feed

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Brewery deploys AI for quality control</title>
  <description>machine learning on the canning line</description>
  <link>https://ex.com/a</link><pubDate>Mon, 01 Jun 2026</pubDate></item>
<item><title>New taproom opens downtown</title>
  <description>a cozy beer bar, no tech</description>
  <link>https://ex.com/b</link><pubDate>Mon, 01 Jun 2026</pubDate></item>
</channel></rss>"""

# AgFunder-style broad agtech: an AI item with no beverage term must be dropped
AGTECH = """<?xml version="1.0"?><rss><channel>
<item><title>AI startup raises for corn yield</title>
  <description>machine learning for row crops</description>
  <link>https://ex.com/corn</link></item>
<item><title>AI vineyard sensor firm funded</title>
  <description>computer vision for grape disease</description>
  <link>https://ex.com/vine</link></item>
</channel></rss>"""

ENTITY_BOMB = """<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>
<rss><channel><item><title>AI beer</title><link>https://x/1</link></item></channel></rss>"""


def test_keeps_ai_items_drops_non_ai():
    out = parse_feed(RSS, "ex.com", beverage_specific=True)
    links = {i["link"] for i in out}
    assert "https://ex.com/a" in links
    assert "https://ex.com/b" not in links


def test_non_beverage_feed_requires_beverage_term():
    out = parse_feed(AGTECH, "agfundernews.com", beverage_specific=False)
    links = {i["link"] for i in out}
    assert "https://ex.com/vine" in links  # has "vineyard"/"grape"
    assert "https://ex.com/corn" not in links  # AI but not beverage


def test_doctype_entity_feed_is_refused():
    assert parse_feed(ENTITY_BOMB, "x", beverage_specific=True) == []
