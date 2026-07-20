from radar.sources.web_search import _DDGParser

SAMPLE = """
<div class="result">
  <a class="result__a" href="https://tastry.com">Tastry uses AI for wine</a>
  <a class="result__snippet">AI sensory sciences for wineries.</a>
</div>
<div class="result">
  <a class="result__a" href="https://caskml.com">CaskML for whiskey</a>
  <a class="result__snippet">Machine learning distilling.</a>
</div>
"""


def test_ddg_parser_extracts_title_url_snippet():
    p = _DDGParser()
    p.feed(SAMPLE)
    assert len(p.results) == 2
    first = p.results[0]
    assert first["url"] == "https://tastry.com"
    assert "Tastry" in first["title"]
    assert "sensory" in first["snippet"]
