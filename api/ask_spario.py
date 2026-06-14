from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ai.shopping_assistant import answer_question_payload
from core.config import CORS_ORIGINS, HOST, PORT


ERROR_ANSWER = "Spario AI non è disponibile al momento."


class AskSparioRequest(BaseModel):
    question: str | None = None


class AskSparioResponse(BaseModel):
    success: bool
    answer: str
    products: list[dict] | None = None


def get_cors_origins():
    raw_origins = CORS_ORIGINS

    if raw_origins.strip() == "*":
        return ["*"]

    return [
        origin.strip()
        for origin in raw_origins.split(",")
        if origin.strip()
    ]


app = FastAPI(
    title="Spario AI Backend",
    version="1.0.0",
    description="Read-only API for Spario AI Shopping Assistant.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/")
def health_check():
    return {
        "success": True,
        "status": "ok",
        "service": "spario-ai-backend",
    }


@app.exception_handler(RequestValidationError)
def validation_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "answer": ERROR_ANSWER,
        },
    )


@app.post(
    "/api/ask-spario",
    response_model=AskSparioResponse,
    response_model_exclude_none=True,
)
def ask_spario(payload: AskSparioRequest):
    try:
        question = (payload.question or "").strip()

        if not question:
            return AskSparioResponse(success=False, answer=ERROR_ANSWER)

        assistant_payload = answer_question_payload(question)
        return AskSparioResponse(
            success=True,
            answer=assistant_payload["answer"],
            products=assistant_payload.get("products", []),
        )
    except Exception:
        return AskSparioResponse(success=False, answer=ERROR_ANSWER)


def main():
    import uvicorn

    uvicorn.run("api.ask_spario:app", host=HOST, port=int(PORT))


if __name__ == "__main__":
    main()
