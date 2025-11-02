import os, uuid, datetime, logging
from typing import Optional, List
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

# Always load .env in the same folder as main.py
ENV_PATH = Path(__file__).with_name('.env')
load_dotenv(dotenv_path=ENV_PATH)

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    # do NOT print the value; just confirm presence
    logging.warning("API_KEY is not set. All requests will be 401.")

app = FastAPI(
    title="CareFlow Demo API",
    version="1.0.0",
    description="Calendar, Messaging and Insurance mock endpoints for IBM watsonx Orchestrate demo."
)

# CORS (allow your web embed and Orchestrate)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Security ---------------------------------------------------------------
def require_key(x_api_key: Optional[str] = Header(None)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid x-api-key")

# ---- Data stores (in-memory) -----------------------------------------------
SLOTS = [
    # demo slots for tomorrow
]
def seed_slots():
    SLOTS.clear()
    base_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    for hour in [9, 10, 11, 13, 14, 15]:
        SLOTS.append({
            "start": f"{base_date}T{hour:02d}:00:00",
            "end":   f"{base_date}T{hour:02d}:40:00",
            "provider": "Dr. Lee"
        })
        SLOTS.append({
            "start": f"{base_date}T{hour:02d}:00:00",
            "end":   f"{base_date}T{hour:02d}:20:00",
            "provider": "NP Garcia"
        })
seed_slots()

BOOKINGS = {}  # booking_id -> booking dict
MESSAGES = []  # log of sent messages

# ---- Schemas ---------------------------------------------------------------
class SlotQuery(BaseModel):
    date: Optional[str] = None
    provider: Optional[str] = None

class BookRequest(BaseModel):
    patient_ref: str
    start: str
    end: str
    provider: str
    visit_type: str

class RescheduleRequest(BaseModel):
    booking_id: str
    new_start: str
    new_end: str

class CancelRequest(BaseModel):
    booking_id: str
    reason: Optional[str] = None

class SendMessageRequest(BaseModel):
    channel: str  # sms | email
    to: str
    subject: Optional[str] = None
    template_name: Optional[str] = None
    variables: Optional[dict] = None

class InsuranceVerifyRequest(BaseModel):
    payer: str
    cpt_code: str
    visit_type: Optional[str] = "screening"

# ---- Routes: Calendar ------------------------------------------------------
@app.get("/slots")
def list_slots(date: Optional[str] = None, provider: Optional[str] = None, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    results = SLOTS
    if date:
        results = [s for s in results if s["start"].startswith(date)]
    if provider:
        results = [s for s in results if s["provider"].lower() == provider.lower()]
    return {"slots": results[:20]}

@app.post("/book", status_code=201)
def book(req: BookRequest, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    # Ensure slot exists & not already booked
    match = next((s for s in SLOTS if s["start"] == req.start and s["end"] == req.end and s["provider"] == req.provider), None)
    if not match:
        raise HTTPException(status_code=400, detail="Slot not available")
    # remove slot + create booking
    SLOTS.remove(match)
    booking_id = str(uuid.uuid4())[:8]
    BOOKINGS[booking_id] = req.model_dump()
    return {"booking_id": booking_id, "status": "created", "booking": BOOKINGS[booking_id]}

@app.post("/reschedule")
def reschedule(req: RescheduleRequest, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    if req.booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="Booking not found")
    # verify new slot exists
    match = next((s for s in SLOTS if s["start"] == req.new_start and s["end"] == req.new_end), None)
    if not match:
        raise HTTPException(status_code=400, detail="New slot not available")
    # free old slot (simplify) and occupy new slot
    old = BOOKINGS[req.booking_id]
    SLOTS.append({"start": old["start"], "end": old["end"], "provider": old["provider"]})
    SLOTS.remove(match)
    old["start"], old["end"] = req.new_start, req.new_end
    return {"booking_id": req.booking_id, "status": "rescheduled", "booking": old}

@app.post("/cancel")
def cancel(req: CancelRequest, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    if req.booking_id not in BOOKINGS:
        raise HTTPException(status_code=404, detail="Booking not found")
    old = BOOKINGS.pop(req.booking_id)
    # return slot to pool
    SLOTS.append({"start": old["start"], "end": old["end"], "provider": old["provider"]})
    return {"booking_id": req.booking_id, "status": "canceled", "reason": req.reason or "unspecified"}

# ---- Routes: Messaging -----------------------------------------------------
@app.post("/message/send", status_code=202)
def send_message(req: SendMessageRequest, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    record = {"id": str(uuid.uuid4())[:8], "channel": req.channel, "to": req.to,
              "subject": req.subject, "template": req.template_name, "vars": req.variables}
    MESSAGES.append(record)
    logging.info(f"[MESSAGE] {record}")
    # You could integrate Twilio/SendGrid here; for demo, we log and accept.
    return {"status": "queued", "message_id": record["id"]}

# ---- Routes: Insurance -----------------------------------------------------
@app.post("/insurance/verify")
def insurance_verify(req: InsuranceVerifyRequest, x_api_key: Optional[str] = Header(None)):
    require_key(x_api_key)
    # mock logic
    covered = True
    preauth_required = (req.visit_type != "screening")
    copay_est = 100.0 if req.visit_type == "screening" else 150.0
    steps = ["Submit indication & notes", "Get auth reference", "Validity 30 days"] if preauth_required else ["No pre-auth required"]
    return {
        "covered": covered,
        "copay_estimate": copay_est,
        "preauth_required": preauth_required,
        "steps": steps
    }

@app.get("/health")
def health():
    return{"ok" : True,  "api_key_present": bool(API_KEY)}