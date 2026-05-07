"""CLI: scrapper search / services / smoke."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import requests

from .booking import lock
from .catalog import find_service_by_id, find_services_by_name
from .client import AuthError, LuxmedClient
from .config import Settings, load_settings
from .logging_setup import setup_logging
from .models import Place, SearchContext, Term
from .notify import TelegramNotifier
from .search import SearchCriteria, find_matching_term, poll_loop, watch_loop

logger = logging.getLogger(__name__)


def parse_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scrapper", description="Luxmed scrapper")
    parser.add_argument("--debug", action="store_true",
                        help="Verbose logging do ~/.luxmed-scrapper/scrapper.log")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # search
    search = sub.add_parser("search", help="Pollowanie + LockTerm")
    svc = search.add_mutually_exclusive_group(required=True)
    svc.add_argument("--service-id", type=int)
    svc.add_argument("--service-name", type=str)
    search.add_argument("--city", required=True)
    search.add_argument("--from", dest="date_from", required=True, type=parse_datetime)
    search.add_argument("--to", dest="date_to", required=True, type=parse_datetime)
    search.add_argument("--doctor", default=None)
    search.add_argument("--facility", default=None)
    search.add_argument("--once", action="store_true",
                        help="Jeden sweep (bez pętli, bez reservation check)")
    search.add_argument("--auto-book", action="store_true",
                        help="Eksperymentalnie: LockTerm po znalezieniu (broken — patrz Task #18)")
    search.add_argument("--max-iterations", type=int, default=None)
    search.add_argument("--cooldown", type=int, default=300,
                        help="Sekundy między alertem a kolejnym reservation check (default 300)")

    # services
    services = sub.add_parser("services", help="Listuj services")
    services.add_argument("--query", default=None)

    # smoke
    sub.add_parser("smoke", help="End-to-end smoke (login + groups + 1 search)")

    return parser


CITY_IDS = {
    "warszawa": 1, "kraków": 2, "krakow": 2, "łódź": 3, "lodz": 3,
    "wrocław": 5, "wroclaw": 5, "poznań": 6, "poznan": 6,
    "gdańsk": 9, "gdansk": 9, "katowice": 7, "lublin": 8,
}


def _resolve_place(city: str) -> Place:
    key = city.casefold()
    if key in CITY_IDS:
        return Place(id=CITY_IDS[key], name=city)
    raise SystemExit(f"Nieznane miasto '{city}'. Dodaj do CITY_IDS w cli.py.")


def _resolve_service(client: LuxmedClient, args: argparse.Namespace) -> tuple[int, str]:
    groups = client.get_service_groups()
    if args.service_id:
        match = find_service_by_id(groups, args.service_id)
        if not match:
            raise SystemExit(f"Service id {args.service_id} nie istnieje")
        logger.info("Service: %s — %s", match.service_id, match.name)
        return match.service_id, match.name
    matches = find_services_by_name(groups, args.service_name)
    if not matches:
        raise SystemExit(f"Brak service pasującego do '{args.service_name}'")
    if len(matches) > 1:
        print("Wiele dopasowań — sprecyzuj przez --service-id:", file=sys.stderr)
        for m in matches:
            print(f"  {m.service_id}  {m.name}  ({' / '.join(m.path)})", file=sys.stderr)
        raise SystemExit(2)
    logger.info("Service: %s — %s", matches[0].service_id, matches[0].name)
    return matches[0].service_id, matches[0].name


SEARCH_PAGE_URL = "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/Search"


def _format_alert(term: Term) -> str:
    return (
        f"<b>Wolny termin Luxmed</b>\n"
        f"{term.doctor.full_name()}\n"
        f"{term.date_time_from.strftime('%Y-%m-%d %H:%M')}\n"
        f"{term.facility_name}\n"
        f'<a href="{SEARCH_PAGE_URL}">Zarezerwuj</a>'
    )


def _format_booked(term: Term) -> str:
    return (
        f"<b>Wizyta zarezerwowana (5-10 min)</b>\n"
        f"{term.doctor.full_name()}\n"
        f"{term.date_time_from.strftime('%Y-%m-%d %H:%M')}\n"
        f"{term.facility_name}\n"
        f"https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/Page/MyVisits"
    )


def _cmd_search(args: argparse.Namespace, settings: Settings) -> int:
    if not args.auto_book and not settings.telegram_enabled:
        logger.error(
            "Telegram niezakonfigurowany (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) — "
            "default flow wymaga notyfikacji. Dodaj env albo użyj --auto-book."
        )
        return 1

    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()

    service_id, service_name = _resolve_service(client, args)
    place = _resolve_place(args.city)
    crit = SearchCriteria(
        service_id=service_id, place=place,
        date_from=args.date_from, date_to=args.date_to,
        doctor_filter=args.doctor, facility_filter=args.facility,
    )

    if args.auto_book:
        return _run_auto_book(client, crit, service_id, service_name, place, args, settings)

    return _run_watch(client, crit, service_name, args, settings)


def _run_watch(
    client: LuxmedClient,
    crit: SearchCriteria,
    service_name: str,
    args: argparse.Namespace,
    settings: Settings,
) -> int:
    notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    if args.once:
        term = find_matching_term(client, crit)
        if not term:
            logger.info("Brak slotów w zakresie")
            return 0
        term.service_variant_name = service_name
        notifier.send(_format_alert(term))
        logger.info("Alert wysłany (--once): %s %s",
                    term.date_time_from.isoformat(), term.doctor.full_name())
        return 0

    try:
        baseline = {r.reservation_id for r in client.get_my_reservations()}
    except NotImplementedError:
        logger.warning(
            "get_my_reservations niewdrożone (recon pending) — baseline pusty, "
            "reservation check będzie no-op. Alerty Telegram działają normalnie."
        )
        baseline = set()

    def on_alert(term: Term) -> None:
        term.service_variant_name = service_name
        notifier.send(_format_alert(term))

    def fetch_reservations():
        try:
            return client.get_my_reservations()
        except NotImplementedError:
            return []

    result = watch_loop(
        client, crit,
        on_alert=on_alert,
        fetch_reservations=fetch_reservations,
        baseline_reservation_ids=baseline,
        cooldown_seconds=args.cooldown,
        max_iterations=args.max_iterations,
    )
    if result.exit_reason == "new_reservation" and result.new_reservation:
        r = result.new_reservation
        logger.info("Wykryta nowa rezerwacja: %s — %s %s",
                    r.reservation_id, r.date_time_from.isoformat(), r.doctor_name)
        return 0
    if result.exit_reason == "max_iterations":
        logger.info("Koniec po %d iteracjach (max-iterations)", result.iterations)
        return 0
    return 0


def _run_auto_book(
    client: LuxmedClient,
    crit: SearchCriteria,
    service_id: int,
    service_name: str,
    place: Place,
    args: argparse.Namespace,
    settings: Settings,
) -> int:
    if args.once:
        term = find_matching_term(client, crit)
        if not term:
            logger.info("Brak slotów w zakresie")
            return 0
    else:
        term = poll_loop(client, crit, max_iterations=args.max_iterations)

    term.service_variant_name = service_name

    import uuid
    ctx = SearchContext(
        process_id=str(uuid.uuid4()),
        correlation_id=None,
        search_parameters={
            "serviceVariantId": service_id,
            "cityId": place.id,
        },
    )
    response = client.get_one_day_terms(
        service_id=service_id, place=place, day=term.date_time_from.date(),
    )
    ctx.correlation_id = response.correlation_id

    result = lock(client, term, ctx)
    if not result.success:
        logger.error("LockTerm fail: %s", result.error)
        return 1

    logger.info("Slot zarezerwowany: %s", result.temporary_reservation_id)
    if settings.telegram_enabled:
        TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id).send(
            _format_booked(term)
        )
    return 0


def _cmd_services(args: argparse.Namespace, settings: Settings) -> int:
    if not args.query:
        print("Podaj --query, np. --query ortop", file=sys.stderr)
        return 2
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()
    groups = client.get_service_groups()
    matches = find_services_by_name(groups, args.query)
    if not matches:
        print(f"Brak service pasującego do '{args.query}'")
        return 0
    for m in matches:
        print(f"{m.service_id}\t{m.name}\t({' / '.join(m.path)})")
    return 0


def _cmd_smoke(args: argparse.Namespace, settings: Settings) -> int:
    from datetime import date
    client = LuxmedClient(settings.luxmed_email, settings.luxmed_password)
    client.login()
    groups = client.get_service_groups()
    if not groups:
        logger.error("serviceVariantsGroups puste")
        return 1
    logger.info("Groups OK (%d top-level)", len(groups))

    def _first_leaf(nodes):
        for n in nodes:
            children = n.get("children") or []
            if not children and n.get("id"):
                return n["id"]
            found = _first_leaf(children)
            if found:
                return found
        return None
    first_service_id = _first_leaf(groups)
    if not first_service_id:
        logger.error("Brak leaf-service w groups")
        return 1

    place = Place(id=5, name="Wrocław")
    response = client.get_one_day_terms(
        service_id=first_service_id, place=place, day=date.today(),
    )
    logger.info("oneDayTerms OK: %d terms, correlationId=%s",
                len(response.terms), response.correlation_id)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log_file = Path.home() / ".luxmed-scrapper" / "scrapper.log" if args.debug else None
    setup_logging(verbose=args.debug, log_file=log_file)

    try:
        settings = load_settings()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    try:
        if args.subcommand == "search":
            return _cmd_search(args, settings)
        if args.subcommand == "services":
            return _cmd_services(args, settings)
        if args.subcommand == "smoke":
            return _cmd_smoke(args, settings)
    except AuthError as exc:
        logger.error("Auth: %s", exc)
        return 1
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        logger.error("HTTP %s z Luxmeda: %s", status, exc.request.url if exc.request else "")
        if status == 429:
            logger.error("Rate-limit. Odczekaj 1-5 minut przed kolejną próbą.")
        return 1
    except KeyboardInterrupt:
        logger.info("Przerwane przez użytkownika")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
