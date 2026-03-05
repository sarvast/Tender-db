import os
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import pandas as pd
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional

from models import SessionLocal, Tender
from database_manager import process_and_save_bids
from excel_exporter import sync_latest_bids_to_excel

app = FastAPI(title="GeM Tender Auto-Tracker")

# Set up templates
templates = Jinja2Templates(directory="templates")

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
    # Fetch all tenders, newest first
    tenders = db.query(Tender).order_by(Tender.bid_end_date.desc()).all()
    
    # Process item_categories if it's stored as JSON list
    for t in tenders:
        if isinstance(t.item_categories, list):
            t.items_str = ", ".join(t.item_categories)
        else:
            t.items_str = t.item_categories if t.item_categories else "N/A"
            
    # Default to sort by end_date asc, quantity desc
    tenders = db.query(Tender).order_by(Tender.bid_end_date.asc(), Tender.quantity.desc()).all()
    total = len(tenders) # Define total based on the new query
        
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "tenders": tenders,
        "total_tenders": total,
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

@app.get("/api/tenders/latest")
async def get_latest_tenders(db: Session = Depends(get_db)):
    """
    API endpoint for the dashboard frontend to poll for new tenders dynamically.
    """
    tenders = db.query(Tender).order_by(Tender.bid_end_date.desc()).all()
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
            "document_url": getattr(t, 'document_url', None),
            "is_notified": t.is_notified
        })
    return {"count": len(result), "tenders": result}

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
