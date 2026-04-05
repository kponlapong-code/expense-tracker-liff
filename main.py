"""
main.py - FastAPI entry point สำหรับ Expense Tracker + LINE Bot
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from database import init_db
from api import router as api_router
from line_handler import router as line_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    print("✅ Database initialized")
    yield


app = FastAPI(
    title="Expense Tracker + LINE Bot",
    description="บันทึกค่าใช้จ่ายผ่าน Web App และ LINE Bot",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(api_router)
app.include_router(line_router)

# Static files (Web App)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the Web App."""
    try:
        with open("static/index.html", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Expense Tracker API is running</h1><p>Visit /docs for API documentation</p>")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "message": "Expense Tracker is running"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
