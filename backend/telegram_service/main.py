import sys
import os
import json
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from typing import Optional

app = FastAPI(title="AI NVR Telegram Alert Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
# Keep the default chat ID as a fallback / default subscriber
DEFAULT_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

CHAT_IDS_FILE = "/clips/chat_ids.json"
subscribed_chats = set()

def load_chat_ids():
    global subscribed_chats
    if os.path.exists(CHAT_IDS_FILE):
        try:
            with open(CHAT_IDS_FILE, "r") as f:
                subscribed_chats = set(json.load(f))
        except Exception as e:
            print(f"[Telegram] Error loading chat_ids: {e}")
            subscribed_chats = set()
    
    if DEFAULT_CHAT_ID and DEFAULT_CHAT_ID not in subscribed_chats:
        subscribed_chats.add(DEFAULT_CHAT_ID)
        save_chat_ids()

def save_chat_ids():
    try:
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(list(subscribed_chats), f)
    except Exception as e:
        print(f"[Telegram] Error saving chat_ids: {e}")

async def poll_telegram_updates():
    last_update_id = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(f"{TELEGRAM_API_URL}/getUpdates?offset={last_update_id}&timeout=20")
                if res.status_code == 200:
                    data = res.json()
                    if data.get("ok"):
                        for update in data["result"]:
                            update_id = update["update_id"]
                            last_update_id = update_id + 1
                            
                            if "message" in update and "chat" in update["message"]:
                                chat_id = str(update["message"]["chat"]["id"])
                                text = update["message"].get("text", "")
                                
                                is_new = chat_id not in subscribed_chats
                                if is_new:
                                    subscribed_chats.add(chat_id)
                                    save_chat_ids()
                                    print(f"[Telegram] New subscriber added: {chat_id}")
                                    
                                if is_new or text.strip() == "/start":
                                    # Send a welcome message back to confirm subscription
                                    welcome_msg = "✅ Вы успешно подписались на уведомления от KAMO AI NVR! Я буду присылать вам видео при обнаружении людей и пересечении линий."
                                    try:
                                        await client.post(
                                            f"{TELEGRAM_API_URL}/sendMessage",
                                            data={"chat_id": chat_id, "text": welcome_msg}
                                        )
                                    except Exception as e:
                                        print(f"[Telegram] Failed to send welcome message: {e}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Telegram Polling Error] {e}", flush=True)
            
        await asyncio.sleep(2)

@app.on_event("startup")
async def startup_event():
    load_chat_ids()
    print(f"[Telegram] Loaded {len(subscribed_chats)} subscribers.")
    asyncio.create_task(poll_telegram_updates())

class AlertPayload(BaseModel):
    camera_name: str
    event_type: str
    timestamp: str
    snapshot_path: Optional[str] = None
    clip_path: Optional[str] = None
    metadata: Optional[dict] = None

async def send_telegram_alert(payload: AlertPayload):
    """
    Sends an alert message to Telegram in a clean format.
    If a video clip exists, sends it alongside the message to all subscribed chats.
    """
    if not subscribed_chats:
        print("[Telegram] No subscribed chats to send to.")
        return

    detected_class = payload.metadata.get("class", "unknown") if payload.metadata else "unknown"
    direction = payload.metadata.get("direction", "unknown") if payload.metadata else "unknown"

    message = (
        f"🚨 ALERT\n\n"
        f"Camera: {payload.camera_name}\n"
        f"Event: {payload.event_type}\n"
        f"Time: {payload.timestamp}\n"
        f"Details: {detected_class}, {direction}"
    )

    clip_local_path = None
    if payload.clip_path:
        filename = payload.clip_path.split("/")[-1]
        clip_local_path = f"/clips/{filename}"

    has_clip = clip_local_path and os.path.exists(clip_local_path)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Read file once into memory if available, because we're sending to multiple chats
        video_data = None
        if has_clip:
            try:
                with open(clip_local_path, "rb") as video_file:
                    video_data = video_file.read()
                file_size = len(video_data)
                print(f"[Telegram] Prepared video clip: {clip_local_path} ({file_size // 1024}KB) for {len(subscribed_chats)} chats")
            except Exception as e:
                print(f"[Telegram] Failed to read video clip: {e}")
                has_clip = False

        for chat_id in list(subscribed_chats):
            sent_successfully = False
            if has_clip and video_data:
                try:
                    res = await client.post(
                        f"{TELEGRAM_API_URL}/sendVideo",
                        data={
                            "chat_id": chat_id, 
                            "caption": message,
                            "supports_streaming": "true"
                        },
                        files={"video": (os.path.basename(clip_local_path), video_data, "video/mp4")}
                    )
                    if res.status_code == 200:
                        sent_successfully = True
                        print(f"[Telegram] ✅ Video clip sent to {chat_id}")
                    else:
                        print(f"[Telegram] ⚠ Video send failed to {chat_id}: {res.text}")
                except Exception as e:
                    print(f"[Telegram] ⚠ Failed to send video to {chat_id}: {e}")
            
            if not sent_successfully:
                try:
                    res = await client.post(
                        f"{TELEGRAM_API_URL}/sendMessage",
                        data={"chat_id": chat_id, "text": message}
                    )
                    if res.status_code == 200:
                        print(f"[Telegram] ✅ Text alert sent to {chat_id}")
                    else:
                        print(f"[Telegram] ⚠ Text alert failed to {chat_id}: {res.text}")
                except Exception as e:
                    print(f"[Telegram] ⚠ Failed to send text alert to {chat_id}: {e}")

    # Clean up the clip file after sending to everyone
    if has_clip:
        try:
            os.remove(clip_local_path)
            print(f"[Telegram] Cleaned up clip file: {clip_local_path}")
        except Exception:
            pass

@app.post("/alerts/trigger", status_code=202)
async def trigger_alert(payload: AlertPayload, background_tasks: BackgroundTasks):
    background_tasks.add_task(send_telegram_alert, payload)
    return {"message": "Alert queued for Telegram delivery"}
