import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import load_config, save_config, config_for_api
from monitor import check_token_status
from notifier import send_slack_notification

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
    cfg = load_config()
    if not cfg["anthropic_api_key"]:
        logger.error("ANTHROPIC_API_KEY is not set. Skipping check.")
        store["last_error"] = "ANTHROPIC_API_KEY が設定されていません"
        return

    try:
        status = await check_token_status(
            api_key=cfg["anthropic_api_key"],
            api_url=cfg["anthropic_api_url"],
            model=cfg["check_model"],
        )
        store["current"] = status
        store["last_error"] = None

        # Keep history bounded
        store["history"].append(status)
        max_h = cfg["max_history"]
        if len(store["history"]) > max_h:
            store["history"] = store["history"][-max_h:]

        # Slack notification: always send on scheduled check
        tokens_pct = status.get("tokens_pct", 100)
        is_alert = tokens_pct <= cfg["alert_threshold"]
        sent = await send_slack_notification(
            cfg["slack_webhook_url"], status, cfg["alert_threshold"]
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
    cfg = load_config()
    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=cfg["check_interval_minutes"]),
        id="token_check",
        name="Token Status Check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — checking every %d minutes",
        cfg["check_interval_minutes"],
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

# CORS — allow the GitHub Pages admin page to reach this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


# --- Dashboard -----------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# --- Status API ----------------------------------------------------------

@app.get("/api/status", response_class=JSONResponse)
async def api_status():
    cfg = load_config()
    return {
        "current": store["current"],
        "last_error": store["last_error"],
        "last_notification": store["last_notification"],
        "config": config_for_api(cfg),
    }


@app.get("/api/history", response_class=JSONResponse)
async def api_history():
    return {"history": store["history"]}


@app.post("/api/check-now", response_class=JSONResponse)
async def check_now():
    """Trigger an immediate check."""
    await scheduled_check()
    return {"ok": True, "current": store["current"], "error": store["last_error"]}


# --- Config API (used by the admin page) ---------------------------------

@app.get("/api/config", response_class=JSONResponse)
async def get_config():
    cfg = load_config()
    return {"config": config_for_api(cfg)}


class ConfigUpdate(BaseModel):
    anthropic_api_key: str | None = None
    anthropic_api_url: str | None = None
    check_model: str | None = None
    slack_webhook_url: str | None = None
    check_interval_minutes: int | None = None
    alert_threshold: int | None = None


@app.post("/api/config", response_class=JSONResponse)
async def update_config(body: ConfigUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    cfg = save_config(updates)

    # Reschedule if interval changed
    if "check_interval_minutes" in updates:
        scheduler.reschedule_job(
            "token_check",
            trigger=IntervalTrigger(minutes=cfg["check_interval_minutes"]),
        )
        logger.info(
            "Scheduler rescheduled — now checking every %d minutes",
            cfg["check_interval_minutes"],
        )

    return {"ok": True, "config": config_for_api(cfg)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    uvicorn.run("app:app", host=cfg["host"], port=cfg["port"], reload=True)
