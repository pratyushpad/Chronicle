"""plain_text is the single HTML→text step every extractor (pay, tags, sponsorship)
and the content hash read from. Its two jobs: never split a token that the markup
split (`$150,<strong>000</strong>`), and never merge two blocks into one word."""
import html
import json
from pathlib import Path

from app.ingest.normalize import plain_text

FIXTURES = Path(__file__).parent / "fixtures"


def _gh_job(job_id: int) -> dict:
    jobs = json.loads((FIXTURES / "pr1_greenhouse.json").read_text())["jobs"]
    return next(j for j in jobs if j["id"] == job_id)


def test_inline_markup_inside_a_number_does_not_split_it():
    # Real Asana posting: the closing "000" of the band sits in its own <span>.
    content = html.unescape(_gh_job(8104491)["content"])
    text = plain_text(content)
    assert "$207,000 – $261,000" in text


def test_number_split_across_many_spans_rejoins():
    # Real CoreWeave posting (syntax-highlighter spans around every number).
    content = html.unescape(_gh_job(4692243006)["content"])
    assert "Salary: $243,800-$303,000" in plain_text(content)


def test_block_elements_end_in_a_single_newline():
    assert plain_text("<p>Hello</p><p>World</p>") == "Hello\nWorld"
    assert plain_text("<ul><li>Python</li><li>Go</li></ul>") == "Python\nGo"
    assert plain_text("line one<br>line two") == "line one\nline two"
    assert plain_text("<h2>Pay</h2><div>$30</div>") == "Pay\n$30"
    assert plain_text("<table><tr><td>A</td><td>B</td></tr></table>") == "A\nB"


def test_inline_elements_join_without_inserting_spaces():
    assert plain_text("<p>$150,<strong>000</strong></p>") == "$150,000"
    assert plain_text("<p>Hello <em>there</em> friend</p>") == "Hello there friend"
    assert plain_text("<span>ab</span><span>cd</span>") == "abcd"


def test_script_style_and_friends_are_dropped():
    raw = (
        "<div><style>p{color:red}</style><script>var salary = '$1,000,000';</script>"
        "<noscript>enable js</noscript><template>tmpl</template>"
        "<svg><text>svg text</text></svg><iframe>frame</iframe><p>Real text</p></div>"
    )
    assert plain_text(raw) == "Real text"


def test_head_content_is_dropped():
    raw = "<html><head><title>Job</title><style>x</style></head><body><p>Body</p></body></html>"
    assert plain_text(raw) == "Body"


def test_entities_are_decoded():
    # Greenhouse content is escaped once in the payload; after the adapter's unescape
    # the markup still carries entities like &mdash; / &amp; / &nbsp;.
    assert plain_text("<p>$30&mdash;$45 USD &amp; benefits&nbsp;here</p>") == "$30—$45 USD & benefits here"


def test_whitespace_is_collapsed_and_trimmed():
    # Raw newlines inside a text node are plain whitespace in HTML; only blocks break lines.
    assert plain_text("  <p>  a \n\n\t b  </p>  ") == "a b"
    assert plain_text("<p> a </p>\n\n<p> b </p>") == "a\nb"


def test_comments_are_dropped():
    assert plain_text("<p>keep<!-- drop me --> this</p>") == "keep this"


def test_empty_inputs_return_none():
    assert plain_text(None) is None
    assert plain_text("") is None
    assert plain_text("   ") is None
    assert plain_text("<p> </p><script>x</script>") is None


def test_plain_text_input_passes_through():
    assert plain_text("Just words & symbols") == "Just words & symbols"


def test_deeply_nested_markup_does_not_blow_the_stack():
    raw = "<div>" * 3000 + "deep" + "</div>" * 3000
    assert plain_text(raw) == "deep"


def test_real_greenhouse_pay_block_keeps_its_heading_line():
    # Anduril's pay-transparency block: title div, then spans for min / divider / max.
    content = html.unescape(_gh_job(5148101007)["content"])
    assert "US Salary Range\n$30—$45 USD" in plain_text(content)
