"""Authenticated review API. Accounts are provisioned by an administrator."""

import asyncio
import json
import os
import sqlite3
from pymysql.err import IntegrityError as MySqlIntegrityError

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import queue
from .config import RULE_VERSION
from .review import validate_source
from .schemas import ReviewRequest
from .storage import Store

app = FastAPI(title="CodeSentinel API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_credentials=True, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Authorization", "Last-Event-ID"])
store = Store()

class Login(BaseModel):
    username: str
    password: str

class UserCreate(Login):
    is_admin: bool = False

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

class JobCreate(ReviewRequest):
    project_id: str

def current_user(request: Request):
    bearer = request.headers.get("authorization", "")
    token = bearer[7:] if bearer.startswith("Bearer ") else request.cookies.get("codesentinel_session", "")
    user = store.session_user(token) if token else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user

def project_access(user: dict, project_id: str):
    if not store.owns_project(user["id"], project_id):
        raise HTTPException(status_code=404, detail="项目不存在")

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/ready")
def ready():
    try:
        store._one("SELECT 1 AS ready")
        queue.client().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="数据库或队列暂不可用") from exc
    return {"status": "ready"}

@app.post("/api/login")
def login(payload: Login, response: Response):
    result = store.authenticate(payload.username, payload.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, user_id, is_admin = result
    response.set_cookie("codesentinel_session", token, httponly=True, samesite="strict",
                        secure=os.getenv("CODESENTINEL_SECURE_COOKIE") == "1",
                        max_age=12 * 3600, path="/")
    return {"id": user_id, "username": payload.username, "is_admin": is_admin}

@app.post("/api/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    token = request.cookies.get("codesentinel_session", "")
    if token:
        store.logout(token)
    store.audit(user["id"], "logout")
    response.delete_cookie("codesentinel_session", path="/")
    return {"ok": True}

@app.get("/api/me")
def me(user=Depends(current_user)):
    return {key: user[key] for key in ("id", "username", "is_admin")}

@app.post("/api/admin/users", status_code=201)
def create_user(payload: UserCreate, user=Depends(current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    try:
        user_id = store.create_user(payload.username, payload.password, payload.is_admin)
    except (sqlite3.IntegrityError, MySqlIntegrityError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    store.audit(user["id"], "admin_user_created", user_id)
    return {"id": user_id, "username": payload.username, "is_admin": payload.is_admin}

@app.get("/api/projects")
def list_projects(user=Depends(current_user)):
    return store.projects(user["id"])

@app.post("/api/projects", status_code=201)
def create_project(payload: ProjectCreate, user=Depends(current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="项目名称不能为空")
    return store.create_project(user["id"], name)

@app.post("/api/jobs", status_code=202)
def submit_job(payload: JobCreate, user=Depends(current_user)):
    project_access(user, payload.project_id)
    validate_source(payload)
    try:
        queue.client().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="任务队列暂不可用") from exc
    job_id = store.create_job(user["id"], payload.project_id, payload.filename,
                              payload.source, RULE_VERSION)
    try:
        queue.publish(job_id)
    except Exception:
        store.event(job_id, "queue_gap", "Redis 通知失败；任务保留在数据库，等待 Worker 恢复")
    return store.job(job_id, user["id"])

@app.get("/api/projects/{project_id}/jobs")
def list_jobs(project_id: str, user=Depends(current_user)):
    project_access(user, project_id)
    return store.jobs(user["id"], project_id)

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user=Depends(current_user)):
    job = store.job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/jobs/{job_id}/source")
def get_job_source(job_id: str, response: Response, user=Depends(current_user)):
    if not store.job(job_id, user["id"]):
        raise HTTPException(status_code=404, detail="任务不存在")
    saved = store.job_source(job_id)
    response.headers["Cache-Control"] = "no-store"
    return {"filename": saved["filename"], "source": saved["source"],
            "source_hash": saved["source_hash"]}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user=Depends(current_user)):
    job = store.job(job_id, user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not store.cancel_queued(job_id, user["id"]):
        raise HTTPException(status_code=409, detail="只能取消排队中的任务")
    return store.job(job_id, user["id"])

@app.get("/api/jobs/{job_id}/events")
def get_events(job_id: str, after: int = 0, user=Depends(current_user)):
    if not store.job(job_id, user["id"]):
        raise HTTPException(status_code=404, detail="任务不存在")
    return store.events(job_id, max(0, after))

@app.get("/api/jobs/{job_id}/stream")
async def stream_events(job_id: str, request: Request, after: int = 0,
                        user=Depends(current_user)):
    if not store.job(job_id, user["id"]):
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        cursor = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        cursor = max(after, 0)

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            for event in store.events(job_id, cursor):
                cursor = event["seq"]
                yield f'id: {cursor}\nevent: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n'
            job = store.job(job_id, user["id"])
            if job["status"] in ("completed", "failed", "cancelled"):
                yield f'event: done\ndata: {job["status"]}\n\n'
                break
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
