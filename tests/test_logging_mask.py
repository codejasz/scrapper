import logging

from scrapper.logging_setup import JwtMaskingFilter, mask_jwt, setup_logging


def test_mask_jwt_keeps_prefix_and_last_8_chars():
    token = "eyJ" + "A" * 100 + "deadbeef"
    masked = mask_jwt(token)
    assert masked.startswith("eyJ")
    assert masked.endswith("deadbeef")
    assert "..." in masked
    assert len(masked) < len(token)


def test_mask_jwt_short_token_fully_masked():
    assert mask_jwt("short") == "***"


def test_mask_jwt_none_returns_none():
    assert mask_jwt(None) is None


def test_filter_redacts_jwt_in_message(caplog):
    logger = logging.getLogger("scrapper.test")
    logger.addFilter(JwtMaskingFilter())

    fake_jwt = "eyJhbGciOiJIUzI1NiJ9." + "x" * 100 + ".signature"
    with caplog.at_level(logging.INFO, logger="scrapper.test"):
        logger.info("Got token=%s done", fake_jwt)

    assert any("eyJhbGci" in r.getMessage() for r in caplog.records)
    assert not any(("x" * 100) in r.getMessage() for r in caplog.records)
