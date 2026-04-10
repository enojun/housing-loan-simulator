import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import Config, config
from monitor import check_token_status
from notifier import send_teams_notification

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
store: dict = {
    "current": None,
    "history": [],
    "last_error": None,
    "last_notification": None,
}

# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------

async def scheduled_check():
    """Periodic token status check."""
    cfg = Config()  # Re-read env vars each time
    if not cfg.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY is not set. Skipping check.")
        store["last_error"] = "ANTHROPIC_API_KEY が設定されていません"
        return

    try:
        status = await check_token_status(
            api_key=cfg.anthropic_api_key,
            api_url=cfg.anthropic_api_url,
            model=cfg.check_model,
        )
        store["current"] = status
        store["last_error"] = None

        # Keep history bounded
        store["history"].append(status)
        if len(store["history"]) > cfg.max_history:
            store["history"] = store["history"][-cfg.max_history :]

        # Teams notification: always send on scheduled check
        tokens_pct = status.get("tokens_pct", 100)
        is_alert = tokens_pct <= cfg.alert_threshold
        sent = await send_teams_notification(
            cfg.teams_webhook_url, status, cfg.alert_threshold
        )
        if sent:
            store["last_notification"] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "alert": is_alert,
            }

    except Exception as e:
        logger.exception("Token check failed: %s", e)
        store["last_error"] = str(e)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = Config()
    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=cfg.check_interval_minutes),
        id="token_check",
        name="Token Status Check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — checking every %d minutes", cfg.check_interval_minutes
    )
    # Run the first check immediately
    asyncio.create_task(scheduled_check())
    yield
    scheduler.shutdown()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Claude Code Token Monitor", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/api/status", response_class=JSONResponse)
async def api_status():
    cfg = Config()
    return {
        "current": store["current"],
        "last_error": store["last_error"],
        "last_notification": store["last_notification"],
        "config": {
            "check_interval_minutes": cfg.check_interval_minutes,
            "alert_threshold": cfg.alert_threshold,
            "api_key_set": bool(cfg.anthropic_api_key),
            "webhook_set": bool(cfg.teams_webhook_url),
        },
    }


@app.get("/api/history", response_class=JSONResponse)
async def api_history():
    return {"history": store["history"]}


@app.post("/api/check-now", response_class=JSONResponse)
async def check_now():
    """Trigger an immediate check."""
    await scheduled_check()
    return {"ok": True, "current": store["current"], "error": store["last_error"]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    cfg = Config()
    uvicorn.run("app:app", host=cfg.host, port=cfg.port, reload=True)
