from digital_spotter.api.workout import allowed_mutation, is_private_research_origin


def test_mutations_require_exact_private_origin_and_custom_header():
    origins = {'http://127.0.0.1:4174'}
    assert allowed_mutation({'Origin': 'http://127.0.0.1:4174', 'X-DS-Workout': '1'}, origins=origins)
    assert not allowed_mutation({'Origin': 'http://evil.test', 'X-DS-Workout': '1'}, origins=origins)
    assert not allowed_mutation({'Origin': 'http://127.0.0.1:4174'}, origins=origins)
    assert not allowed_mutation({'X-DS-Workout': '1'}, origins=origins)


def test_private_origin_accepts_only_loopback_http_or_tailscale_https():
    assert is_private_research_origin('http://127.0.0.1:4174')
    assert is_private_research_origin('https://pidigitalspotter.example-tailnet.ts.net')
    assert not is_private_research_origin('http://pidigitalspotter.example-tailnet.ts.net')
    assert not is_private_research_origin('https://example.com')
    assert not is_private_research_origin('https://pidigitalspotter.example-tailnet.ts.net/path')
    assert not is_private_research_origin('https://user@example-tailnet.ts.net')
