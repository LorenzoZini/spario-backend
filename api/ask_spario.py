import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ai.shopping_assistant import answer_question


ERROR_ANSWER = "Spario AI non è disponibile al momento."


class AskSparioRequest(BaseModel):
    question: str | None = None


class AskSparioResponse(BaseModel):
    success: bool
    answer: str


def get_cors_origins():
    raw_origins = os.getenv("CORS_ORIGINS", "*")

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


@app.post("/api/ask-spario", response_model=AskSparioResponse)
def ask_spario(payload: AskSparioRequest):
    try:
        question = (payload.question or "").strip()

        if not question:
            return AskSparioResponse(success=False, answer=ERROR_ANSWER)

        answer = answer_question(question)
        return AskSparioResponse(success=True, answer=answer)
    except Exception:
        return AskSparioResponse(success=False, answer=ERROR_ANSWER)


def main():
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run("api.ask_spario:app", host=host, port=port)


if __name__ == "__main__":
    main()
