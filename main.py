import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import (
    authenticate_user,
    create_group,
    get_all_users,
    get_group,
    get_group_messages,
    get_groups,
    get_user,
    init_db,
    save_message,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR = Path(os.environ.get("UPLOAD_PATH", str(BASE_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".md", ".csv", ".py", ".ipynb",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip"
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="M.Sc AI & DS Classroom Chat", lifespan=lifespan)

app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class ConnectionManager:
    def __init__(self):
        # Maps user_id -> list of active WebSocket connections (supports multiple tabs)
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.user_profiles: Dict[str, dict] = {}

    async def connect(self, websocket: WebSocket, user: dict):
        await websocket.accept()
        uid = user["user_id"]
        self.active_connections.setdefault(uid, []).append(websocket)
        self.user_profiles[uid] = user
        await self.broadcast_online_users()

    async def disconnect(self, websocket: WebSocket, user_id: str):
        conns = self.active_connections.get(user_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self.active_connections.pop(user_id, None)
            self.user_profiles.pop(user_id, None)
        await self.broadcast_online_users()

    async def send_personal(self, websocket: WebSocket, payload: dict):
        try:
            await websocket.send_json(payload)
        except Exception:
            pass

    async def broadcast(self, payload: dict):
        stale: List[tuple[str, WebSocket]] = []
        for uid, conns in list(self.active_connections.items()):
            for ws in list(conns):
                try:
                    await ws.send_json(payload)
                except Exception:
                    stale.append((uid, ws))
        for uid, ws in stale:
            conns = self.active_connections.get(uid, [])
            if ws in conns:
                conns.remove(ws)
            if not conns:
                self.active_connections.pop(uid, None)
                self.user_profiles.pop(uid, None)

    async def broadcast_online_users(self):
        online_ids = list(self.active_connections.keys())
        await self.broadcast({
            "type": "online_users",
            "online_ids": online_ids,
        })


manager = ConnectionManager()


def generate_bot_reply(prompt_text: str, sender_name: str) -> str:
    q = prompt_text.lower()
    if any(k in q for k in ["exam", "test", "cia", "assessment", "syllabus"]):
        return (
            f"Hi {sender_name}, please check **Official Notices & Circulars** for confirmed exam/CIA dates "
            "and syllabus updates posted by Dr. Ben M Jebin."
        )
    if any(k in q for k in ["assignment", "lab", "record", "submission", "project", "file", "notes"]):
        return (
            f"Hi {sender_name}, lecture notes and lab materials shared by the mentor appear directly in the "
            "chat thread with downloadable attachments."
        )
    if any(k in q for k in ["rule", "policy", "privacy", "phone", "number"]):
        return (
            "Privacy reminder: This M.Sc AI & DS portal uses institutional IDs and birth dates—no personal "
            "phone numbers are required or displayed."
        )
    return (
        f"Hi {sender_name}, I've logged your query in the class thread. For official circulars or approvals, "
        "please tag **Dr. Ben M Jebin** (`FAC_BEN_01`) or check the Notices group."
    )


def sanitize_filename(filename: str) -> str:
    base = Path(filename or "attachment").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return cleaned[:120] or "attachment"


@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    return templates.TemplateResponse(request, "chat.html")


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    secret: str = Form(...),
):
    user = authenticate_user(user_id, secret)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    if user["role"] != "MENTOR":
        raise HTTPException(status_code=403, detail="Only mentors can upload files.")

    safe_name = sanitize_filename(file.filename or "file")
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' is not allowed.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB limit.")

    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = UPLOAD_DIR / stored_name
    dest_path.write_bytes(content)

    return JSONResponse({
        "attachment_url": f"/uploads/{stored_name}",
        "attachment_name": safe_name,
    })


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    secret = websocket.query_params.get("secret", "")
    user = authenticate_user(user_id, secret)
    if not user:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "Authentication failed. Check your ID, birth date (DDMMYYYY), or 7-digit mentor code.",
        })
        await websocket.close(code=4001)
        return

    await manager.connect(websocket, user)

    groups = get_groups()
    initial_group_id = groups[0]["group_id"] if groups else 1
    history = get_group_messages(initial_group_id)

    await manager.send_personal(websocket, {
        "type": "init",
        "user": user,
        "users": get_all_users(),
        "groups": groups,
        "online_ids": list(manager.active_connections.keys()),
        "active_group_id": initial_group_id,
        "messages": history,
    })

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                await manager.send_personal(websocket, {"type": "error", "message": "Invalid message format."})
                continue

            msg_type = data.get("type")

            if msg_type == "switch_group":
                try:
                    gid = int(data.get("group_id"))
                except (TypeError, ValueError):
                    await manager.send_personal(websocket, {"type": "error", "message": "Invalid group ID."})
                    continue

                grp = get_group(gid)
                if not grp:
                    await manager.send_personal(websocket, {"type": "error", "message": "Group not found."})
                    continue

                await manager.send_personal(websocket, {
                    "type": "group_history",
                    "group_id": gid,
                    "messages": get_group_messages(gid),
                })

            elif msg_type == "create_group":
                if user["role"] != "MENTOR":
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "message": "Only mentors can create new groups.",
                    })
                    continue

                group_name = (data.get("group_name") or "").strip()
                description = (data.get("description") or "").strip() or "Departmental discussion group"
                mentor_only = bool(data.get("mentor_only_post", False))

                if not group_name:
                    await manager.send_personal(websocket, {"type": "error", "message": "Group name is required."})
                    continue

                new_group = create_group(group_name, description, mentor_only, user["user_id"])
                await manager.broadcast({
                    "type": "group_created",
                    "group": new_group,
                    "groups": get_groups(),
                })

            elif msg_type == "chat_message":
                try:
                    gid = int(data.get("group_id"))
                except (TypeError, ValueError):
                    await manager.send_personal(websocket, {"type": "error", "message": "Invalid group selected."})
                    continue

                grp = get_group(gid)
                if not grp:
                    await manager.send_personal(websocket, {"type": "error", "message": "Selected group does not exist."})
                    continue

                if grp["mentor_only_post"] and user["role"] != "MENTOR":
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "message": "This group is read-only for students (Mentor announcements only).",
                    })
                    continue

                content = (data.get("content") or "").strip()
                attachment_url = data.get("attachment_url")
                attachment_name = data.get("attachment_name")

                if attachment_url and user["role"] != "MENTOR":
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "message": "Only mentors can attach files.",
                    })
                    continue

                if attachment_url and not str(attachment_url).startswith("/uploads/"):
                    await manager.send_personal(websocket, {
                        "type": "error",
                        "message": "Invalid attachment path.",
                    })
                    continue

                if not content and not attachment_url:
                    continue

                saved = save_message(
                    group_id=gid,
                    sender_id=user["user_id"],
                    sender_name=user["full_name"],
                    sender_role=user["role"],
                    content=content or f"Shared attachment: {attachment_name}",
                    attachment_url=attachment_url,
                    attachment_name=attachment_name,
                )

                await manager.broadcast({
                    "type": "new_message",
                    "message": saved,
                })

                # Optional @bot assistant in non-read-only groups
                if content and "@bot" in content.lower() and not grp["mentor_only_post"]:
                    bot_reply_text = generate_bot_reply(content, user["full_name"])
                    bot_saved = save_message(
                        group_id=gid,
                        sender_id="DEPT_BOT",
                        sender_name="AI & DS Assistant",
                        sender_role="BOT",
                        content=bot_reply_text,
                    )
                    await manager.broadcast({
                        "type": "new_message",
                        "message": bot_saved,
                    })

            elif msg_type == "refresh_users":
                fresh_user = get_user(user["user_id"]) or user
                await manager.send_personal(websocket, {
                    "type": "users_list",
                    "users": get_all_users(),
                    "user": fresh_user,
                })

    except WebSocketDisconnect:
        await manager.disconnect(websocket, user["user_id"])
    except Exception:
        await manager.disconnect(websocket, user["user_id"])