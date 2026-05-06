import pytest

from scrapper.cli import build_parser, parse_datetime


def test_parse_datetime_accepts_yyyy_mm_dd_hh_mm():
    dt = parse_datetime("2026-05-08 17:00")
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 8
    assert dt.hour == 17
    assert dt.minute == 0


def test_parse_datetime_invalid_raises():
    with pytest.raises(ValueError):
        parse_datetime("nie-data")


def test_search_parser_requires_either_service_id_or_name():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--city", "Wrocław",
                           "--from", "2026-05-05 16:00",
                           "--to", "2026-05-05 19:00"])


def test_search_parser_accepts_service_id():
    parser = build_parser()
    args = parser.parse_args([
        "search", "--service-id", "4436",
        "--city", "Wrocław",
        "--from", "2026-05-05 16:00",
        "--to", "2026-05-05 19:00",
    ])
    assert args.subcommand == "search"
    assert args.service_id == 4436
    assert args.city == "Wrocław"
    assert args.no_lock is False
    assert args.once is False


def test_search_parser_no_lock_and_once_flags():
    parser = build_parser()
    args = parser.parse_args([
        "search", "--service-name", "Ortopeda",
        "--city", "Wrocław",
        "--from", "2026-05-05 16:00",
        "--to", "2026-05-05 19:00",
        "--no-lock", "--once",
    ])
    assert args.no_lock is True
    assert args.once is True


def test_services_subcommand():
    parser = build_parser()
    args = parser.parse_args(["services", "--query", "ortop"])
    assert args.subcommand == "services"
    assert args.query == "ortop"


def test_smoke_subcommand():
    parser = build_parser()
    args = parser.parse_args(["smoke"])
    assert args.subcommand == "smoke"
