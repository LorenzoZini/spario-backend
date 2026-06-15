import json
import logging
import secrets
import time
from contextvars import ContextVar
from dataclasses import asdict, dataclass

from core.config import get_retrieval_diagnostics_enabled


logger = logging.getLogger("spario.retrieval")


@dataclass
class RetrievalDiagnostics:
    request_id: str
    intent: str | None = None
    category: str | None = None
    brand: str | None = None
    budget: float | None = None
    bounded_retrieval_used: bool = False
    bounded_candidates: int = 0
    legacy_fallback_used: bool = False
    fallback_reason: str | None = None
    products_passed_to_ranking: int = 0
    offer_product_ids: int = 0
    offers_loaded: int = 0
    final_products_returned: int = 0
    total_time_ms: float = 0.0
    request_succeeded: bool = False
    started_at: float = 0.0


_current_diagnostics = ContextVar(
    "spario_retrieval_diagnostics",
    default=None,
)


def _configure_logger():
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False


def start_retrieval_diagnostics():
    try:
        if not get_retrieval_diagnostics_enabled():
            return None

        _configure_logger()
        diagnostics = RetrievalDiagnostics(
            request_id=secrets.token_hex(4),
            started_at=time.perf_counter(),
        )
        return _current_diagnostics.set(diagnostics)
    except Exception:
        return None


def _update(callback):
    try:
        diagnostics = _current_diagnostics.get()
        if diagnostics is not None:
            callback(diagnostics)
    except Exception:
        return


def record_parsed_question(parsed):
    def apply(diagnostics):
        diagnostics.intent = getattr(parsed, "intent", None)
        diagnostics.category = getattr(parsed, "category", None)
        diagnostics.brand = getattr(parsed, "brand", None)
        diagnostics.budget = getattr(parsed, "budget", None)

    _update(apply)


def record_bounded_candidates(count, used):
    def apply(diagnostics):
        diagnostics.bounded_retrieval_used = bool(used)
        diagnostics.bounded_candidates = max(0, int(count))

    _update(apply)


def record_legacy_fallback(reason):
    def apply(diagnostics):
        diagnostics.legacy_fallback_used = True
        if not diagnostics.fallback_reason:
            diagnostics.fallback_reason = reason

    _update(apply)


def record_ranking_input(count):
    _update(
        lambda diagnostics: setattr(
            diagnostics,
            "products_passed_to_ranking",
            max(0, int(count)),
        )
    )


def record_offer_lookup(product_id_count, offer_count):
    def apply(diagnostics):
        diagnostics.offer_product_ids += max(0, int(product_id_count))
        diagnostics.offers_loaded += max(0, int(offer_count))

    _update(apply)


def record_final_products(count):
    _update(
        lambda diagnostics: setattr(
            diagnostics,
            "final_products_returned",
            max(0, int(count)),
        )
    )


def finish_retrieval_diagnostics(token, succeeded):
    if token is None:
        return

    try:
        diagnostics = _current_diagnostics.get()
        if diagnostics is None:
            return

        diagnostics.request_succeeded = bool(succeeded)
        diagnostics.total_time_ms = round(
            (time.perf_counter() - diagnostics.started_at) * 1000,
            2,
        )
        payload = asdict(diagnostics)
        payload.pop("started_at", None)
        logger.info(
            "retrieval_summary %s",
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
        )
    except Exception:
        return
    finally:
        try:
            _current_diagnostics.reset(token)
        except Exception:
            pass
