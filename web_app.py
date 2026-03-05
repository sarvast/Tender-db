import os
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import pandas as pd
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import List, Optional
import asyncio

from models import SessionLocal, Tender
from database_manager import process_and_save_bids
from excel_exporter import sync_latest_bids_to_excel
from telegram_notifier import send_telegram_alert

app = FastAPI(title="GeM Tender Auto-Tracker")

# In-memory store for scraper heartbeat (resets on server restart, that's fine)
_scraper_heartbeat = {"last_seen": None, "alert_sent": False}

# Set up templates
templates = Jinja2Templates(directory="templates")

async def monitor_scraper_health():
    """Background task to check if the scraper has silently died."""
    while True:
        try:
            await asyncio.sleep(3600) # Check once an hour
            
            last = _scraper_heartbeat.get("last_seen")
            if not last:
                continue
                
            delta = datetime.now() - datetime.fromisoformat(last)
            hours_ago = delta.total_seconds() / 3600
            
            if hours_ago > 12 and not _scraper_heartbeat.get("alert_sent"):
                alert_msg = f"⚠️ *CRITICAL ALERT*\n\nThe Local GeM Scraper has not sent a heartbeat in over {int(hours_ago)} hours.\nIt may have crashed or the host PC is off."
                send_telegram_alert(alert_msg)
                _scraper_heartbeat["alert_sent"] = True
                
            elif hours_ago <= 12 and _scraper_heartbeat.get("alert_sent"):
                # Reset if it comes back alive
                _scraper_heartbeat["alert_sent"] = False
                send_telegram_alert("✅ Scraper connection recovered.")
                
        except Exception as e:
            print(f"Health monitor error: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor_scraper_health())

# Pydantic models for API ingestion
class TenderCreate(BaseModel):
    gem_bid_number: str
    department_name: Optional[str] = None
    category: Optional[str] = "General"
    item_categories: Optional[List[str]] = None
    quantity: Optional[int] = None
    estimated_value: Optional[float] = None
    emd_amount: Optional[float] = None
    bid_start_date: Optional[datetime] = None
    bid_end_date: Optional[datetime] = None
    mii_applicable: Optional[bool] = False
    mse_preference: Optional[bool] = False
    is_visited: Optional[bool] = False
    status: Optional[str] = "Open"
    document_url: Optional[str] = None

class TenderUploadRequest(BaseModel):
    bids: List[TenderCreate]

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Main dashboard view. Fetches all tenders from SQLite and renders the UI.
    """
    # Fetch all tenders sorted by end_date asc, quantity desc
    tenders = db.query(Tender).order_by(Tender.bid_end_date.asc(), Tender.quantity.desc()).all()
    
    # Process item_categories if it's stored as JSON list
    for t in tenders:
        if isinstance(t.item_categories, list):
            t.items_str = ", ".join(t.item_categories)
        else:
            t.items_str = t.item_categories if t.item_categories else "N/A"
        
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "tenders": tenders,
        "total_tenders": len(tenders),
        "last_updated": datetime.now().strftime("%d %b %Y, %H:%M"),
        "current_time": datetime.now()
    })

@app.post("/api/tenders/upload")
async def upload_tenders(request: TenderUploadRequest, db: Session = Depends(get_db)):
    """
    API Endpoint for the remote scraper to upload new bids.
    """
    if not request.bids:
        return {"status": "success", "message": "No bids provided", "inserted": 0}
        
    try:
        # Convert Pydantic models to dicts for our database_manager
        bids_data = [bid.dict() for bid in request.bids]
        new_inserts = process_and_save_bids(bids_data, db)
        
        # If new bids were added, we could potentially trigger a background sync to Excel here
        # But for now, returning the count is sufficient
        return {
            "status": "success", 
            "message": f"Processed {len(bids_data)} bids.", 
            "inserted": new_inserts
        }
    except Exception as e:
        print(f"API Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/heartbeat")
async def scraper_heartbeat():
    """Called by local scraper at start of each run to update its last-seen timestamp."""
    _scraper_heartbeat["last_seen"] = datetime.now().isoformat()
    return {"status": "ok", "recorded_at": _scraper_heartbeat["last_seen"]}

@app.get("/api/heartbeat")
async def get_heartbeat():
    """Returns when the scraper last connected. Used by the dashboard."""
    last = _scraper_heartbeat["last_seen"]
    if last:
        delta = datetime.now() - datetime.fromisoformat(last)
        minutes_ago = int(delta.total_seconds() / 60)
        status = "ok" if minutes_ago < 30 else "stale"
        return {"last_seen": last, "minutes_ago": minutes_ago, "status": status}
    return {"last_seen": None, "minutes_ago": None, "status": "never"}

@app.get("/api/tenders/latest")
async def get_latest_tenders(db: Session = Depends(get_db)):
    """
    API endpoint for the dashboard frontend to poll for new tenders dynamically.
    """
    tenders = db.query(Tender).order_by(Tender.created_at.desc(), Tender.id.desc()).all()
    # Format for JSON response
    result = []
    for t in tenders:
        items = t.item_categories if isinstance(t.item_categories, list) else [t.item_categories] if t.item_categories else []
        result.append({
            "id": t.id,
            "gem_bid_number": t.gem_bid_number,
            "department_name": t.department_name,
            "category": getattr(t, 'category', 'General') or 'General',
            "items_str": ", ".join(items) if items else "N/A",
            "quantity": getattr(t, 'quantity', 1) or 1,
            "bid_start_date": t.bid_start_date.isoformat() if getattr(t, 'bid_start_date', None) else None,
            "bid_end_date": t.bid_end_date.isoformat() if t.bid_end_date else None,
            "mii_applicable": t.mii_applicable,
            "mse_preference": t.mse_preference,
            "is_visited": getattr(t, 'is_visited', False),
            "status": getattr(t, 'status', 'Open') or 'Open',
            "document_url": getattr(t, 'document_url', None),
            "is_notified": t.is_notified
        })
    return {"count": len(result), "tenders": result}

@app.get("/api/analytics")
async def get_analytics(db: Session = Depends(get_db)):
    """
    API endpoint for the dashboard to fetch historical analytics and breakdown.
    """
    tenders = db.query(Tender).all()
    if not tenders:
        return {"total_bids": 0, "categories": {}, "status_breakdown": {}}
        
    df = pd.DataFrame([{
        "category": t.category or "General",
        "status": t.status or "Open",
        "value": t.emd_amount or 0
    } for t in tenders])
    
    # Aggregations
    cat_counts = df['category'].value_counts().to_dict()
    status_counts = df['status'].value_counts().to_dict()
    
    # Ensure default keys
    for key in ['Won', 'Lost', 'Submitted', 'Open']:
        if key not in status_counts:
            status_counts[key] = 0
            
    total_won_value = df[df['status'] == 'Won']['value'].sum()
            
    return {
        "total_bids": len(tenders),
        "categories": cat_counts,
        "status_breakdown": status_counts,
        "total_won_emd_value": float(total_won_value)
    }

class VisitedUpdate(BaseModel):
    is_visited: bool

@app.post("/api/tenders/{tender_id}/visited")
def update_visited_status(tender_id: int, status: VisitedUpdate, db: Session = Depends(get_db)):
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
        
    tender.is_visited = status.is_visited
    db.commit()
    db.refresh(tender) # Refresh to get the latest state from the DB
    return {"message": "Status updated successfully", "id": tender.id, "is_visited": tender.is_visited}

class TrackingStatusUpdate(BaseModel):
    status: str

@app.post("/api/tenders/{tender_id}/status")
def update_tracking_status(tender_id: int, update: TrackingStatusUpdate, db: Session = Depends(get_db)):
    tender = db.query(Tender).filter(Tender.id == tender_id).first()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
        
    tender.status = update.status
    db.commit()
    return {"message": "Tracking status updated", "id": tender.id, "status": tender.status}

@app.get("/download-excel")
async def download_excel():
    """
    Endpoint that triggers the Excel generation script and returns the file download.
    """
    # Force a sync run to ensure the excel file exists and is up to date
    try:
        sync_latest_bids_to_excel()
    except Exception as e:
        print(f"Error generating fresh excel on download request: {e}")
        
    excel_filename = "latest_poct_tenders.xlsx"
    
    # Check if file exists, if not generate an empty one as fallback
    if not os.path.exists(excel_filename):
        df = pd.DataFrame(columns=['gem_bid_number', 'department_name', 'No Data Found'])
        df.to_excel(excel_filename, index=False)
        
    return FileResponse(
        path=excel_filename, 
        filename=excel_filename,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
