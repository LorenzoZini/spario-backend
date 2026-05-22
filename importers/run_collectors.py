import argparse
import importlib
import time
from dataclasses import dataclass
from datetime import datetime


DEFAULT_CATEGORIES = [
    "smartphone",
    "cuffie",
    "laptop",
    "tv",
    "desktop",
    "casse_audio",
]


@dataclass(frozen=True)
class CollectorConfig:
    name: str
    module_name: str
    function_name: str
    categories: tuple[str, ...]


COLLECTORS = {
    "unieuro": CollectorConfig(
        name="unieuro",
        module_name="importers.unieuro_collector",
        function_name="import_unieuro_category",
        categories=tuple(DEFAULT_CATEGORIES),
    ),
    "mediaworld": CollectorConfig(
        name="mediaworld",
        module_name="importers.mediaworld_collector",
        function_name="import_mediaworld_category",
        categories=tuple(DEFAULT_CATEGORIES),
    ),
}


def parse_csv(value):
    if not value or value == "all":
        return []

    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_retailers(retailer):
    if retailer == "all":
        return list(COLLECTORS.keys())

    if retailer not in COLLECTORS:
        raise ValueError(f"Retailer non supportato: {retailer}")

    return [retailer]


def resolve_categories(category_value, collector_config):
    requested = parse_csv(category_value)

    if not requested:
        return list(collector_config.categories)

    allowed = set(collector_config.categories)
    invalid = [category for category in requested if category not in allowed]

    if invalid:
        raise ValueError(
            f"Categorie non supportate per {collector_config.name}: {', '.join(invalid)}"
        )

    return requested


def load_collector_function(collector_config):
    module = importlib.import_module(collector_config.module_name)
    collector_function = getattr(module, collector_config.function_name)

    if not callable(collector_function):
        raise TypeError(
            f"{collector_config.module_name}.{collector_config.function_name} non e callable"
        )

    return collector_function


def run_collector_once(
    retailer,
    categories,
    limit,
    execute=False,
    sleep_seconds_between_categories=5,
):
    collector_config = COLLECTORS[retailer]

    print(
        f"\n[{datetime.now().isoformat(timespec='seconds')}] "
        f"collector={retailer} categories={','.join(categories)} "
        f"limit={limit} execute={execute}"
    )

    if not execute:
        for category in categories:
            print(
                "DRY_RUN "
                f"collector={retailer} category={category} limit={limit} "
                "azione=nessuna_chiamata_collector"
            )
        return {
            "retailer": retailer,
            "categories": categories,
            "executed": False,
            "errors": [],
        }

    try:
        collector_function = load_collector_function(collector_config)
    except Exception as exc:
        print(f"ERRORE collector={retailer} fase=import detail={exc}")
        return {
            "retailer": retailer,
            "categories": categories,
            "executed": False,
            "errors": [str(exc)],
        }

    errors = []

    for index, category in enumerate(categories):
        try:
            print(f"START collector={retailer} category={category} limit={limit}")
            collector_function(category, limit=limit)
            print(f"DONE collector={retailer} category={category}")
        except Exception as exc:
            message = f"collector={retailer} category={category} detail={exc}"
            errors.append(message)
            print(f"ERRORE {message}")

        if index < len(categories) - 1 and sleep_seconds_between_categories > 0:
            time.sleep(sleep_seconds_between_categories)

    return {
        "retailer": retailer,
        "categories": categories,
        "executed": True,
        "errors": errors,
    }


def run_once(args):
    summaries = []

    for retailer in resolve_retailers(args.retailer):
        collector_config = COLLECTORS[retailer]
        categories = resolve_categories(args.categories, collector_config)
        summary = run_collector_once(
            retailer=retailer,
            categories=categories,
            limit=args.limit,
            execute=args.execute,
            sleep_seconds_between_categories=args.sleep_seconds,
        )
        summaries.append(summary)

    total_errors = sum(len(summary["errors"]) for summary in summaries)
    print(
        "\nSUMMARY "
        f"retailers={len(summaries)} execute={args.execute} errors={total_errors}"
    )

    return 1 if total_errors else 0


def run_loop(args):
    if args.interval_hours is None:
        return run_once(args)

    if args.interval_hours <= 0:
        raise ValueError("--interval-hours deve essere maggiore di zero")

    if not args.execute:
        print(
            "DRY_RUN scheduler_loop_non_avviato: "
            "aggiungi --execute per chiamare davvero i collector ogni intervallo."
        )
        return run_once(args)

    interval_seconds = args.interval_hours * 60 * 60

    while True:
        run_once(args)
        print(f"Scheduler in pausa per {args.interval_hours} ore...")
        time.sleep(interval_seconds)


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Orchestrator collector Spario. Di default e dry-run: usa --execute "
            "solo quando vuoi chiamare davvero i collector."
        )
    )

    parser.add_argument(
        "--retailer",
        choices=["all", *COLLECTORS.keys()],
        default="all",
        help="Retailer da eseguire",
    )
    parser.add_argument(
        "--categories",
        default="all",
        help="Categorie comma-separated oppure all",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Limite prodotti per categoria passato ai collector",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Esegue davvero i collector. Senza questo flag non chiama Firecrawl.",
    )
    parser.add_argument(
        "--interval-hours",
        type=float,
        default=None,
        help="Se impostato con --execute, ripete il run ogni N ore",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=5,
        help="Pausa tra categorie nello stesso retailer",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.limit <= 0:
        parser.error("--limit deve essere maggiore di zero")

    try:
        return run_loop(args)
    except KeyboardInterrupt:
        print("\nScheduler interrotto manualmente.")
        return 130
    except Exception as exc:
        print(f"ERRORE scheduler detail={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())