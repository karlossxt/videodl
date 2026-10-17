from videodl.utils import (
    centered_crop,
    even,
    human_size,
    parse_extractor_args,
    sanitize_filename,
    time_tag,
)


def test_sanitize_filename_removes_forbidden_chars():
    assert sanitize_filename('a<b>c:d/e\\f|g?h*i"j') == "abcdefghij"


def test_sanitize_filename_collapses_whitespace_and_strips_dots():
    assert sanitize_filename("  hola   mundo.  ") == "hola mundo"


def test_sanitize_filename_falls_back_to_video():
    assert sanitize_filename("") == "video"
    assert sanitize_filename("   ") == "video"


def test_sanitize_filename_is_bounded():
    assert len(sanitize_filename("x" * 500)) == 150


def test_human_size():
    assert human_size(None) is None
    assert human_size(0) is None
    assert human_size(512) == "512.0 B"
    assert human_size(1024) == "1.0 KB"
    assert human_size(1024 * 1024) == "1.0 MB"


def test_time_tag():
    assert time_tag(None) == ""
    assert time_tag(65) == "1m05s"
    assert time_tag(3725) == "1h02m05s"


def test_even():
    assert even(3) == 4
    assert even(4) == 4
    assert even(0) == 2  # nunca por debajo de 2


def test_centered_crop_stays_within_bounds():
    for w, h in [(1920, 1080), (1080, 1920), (1000, 1000)]:
        cw, ch, x, y = centered_crop(w, h, 9, 16)
        assert cw % 2 == 0 and ch % 2 == 0
        assert x >= 0 and y >= 0
        assert x + cw <= w
        assert y + ch <= h


def test_parse_extractor_args_cliente_con_lista():
    assert parse_extractor_args("youtube:player_client=tv,web_safari") == {
        "youtube": {"player_client": ["tv", "web_safari"]}
    }


def test_parse_extractor_args_varios_argumentos_y_extractores():
    assert parse_extractor_args("youtube:player_client=tv;po_token=web+abc; vimeo:key=1") == {
        "youtube": {"player_client": ["tv"], "po_token": ["web+abc"]},
        "vimeo": {"key": ["1"]},
    }


def test_parse_extractor_args_vacio_o_invalido():
    assert parse_extractor_args("") == {}
    assert parse_extractor_args("   ") == {}
    # Sin extractor o sin "=" no hay nada que aplicar.
    assert parse_extractor_args("player_client=tv") == {}
    assert parse_extractor_args("youtube:") == {}
