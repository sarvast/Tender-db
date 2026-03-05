import pandas as pd
from models import Tender, SessionLocal

def sync_latest_bids_to_excel():
    """
    Syncs latest bids (is_notified = False) from the DB to an Excel file.
    """
    db_session = SessionLocal()
    
    try:
        # Step 1 (Fetch): Database se bids fetch karo jinki notification pending hai
        latest_bids = db_session.query(Tender).filter_by(is_notified=False).all()
        
        if not latest_bids:
            print("No new bids to sync.")
            return
            
        # Extract data to load into Pandas
        bids_data = []
        for bid in latest_bids:
            bids_data.append({
                'id': bid.id,
                'gem_bid_number': bid.gem_bid_number,
                'category': getattr(bid, 'category', 'General') or 'General',
                'department_name': bid.department_name,
                'quantity': getattr(bid, 'quantity', 1) or 1,
                'bid_start_date': bid.bid_start_date.strftime('%Y-%m-%d %H:%M') if getattr(bid, 'bid_start_date', None) else '',
                # Convert array of strings into a single comma-separated string for Excel readability
                'item_categories': ", ".join(bid.item_categories) if bid.item_categories else "",
                'estimated_value': bid.estimated_value,
                'emd_amount': bid.emd_amount,
                'bid_end_date': bid.bid_end_date.strftime('%Y-%m-%d %H:%M:%S') if bid.bid_end_date else None,
                'mii_applicable': bid.mii_applicable,
                'mse_preference': bid.mse_preference,
                'created_at': bid.created_at.strftime('%Y-%m-%d %H:%M:%S') if bid.created_at else None
            })
            
        # Step 2 (Export): Data ko Pandas DataFrame mein load karo aur Excel banayo
        df = pd.DataFrame(bids_data)
        
        # Apply Sorting: Date closest first (Ascending), Quantity highest first (Descending)
        if 'bid_end_date' in df.columns:
             df['bid_end_date_dt'] = pd.to_datetime(df['bid_end_date'], errors='coerce')
             df = df.sort_values(by=['bid_end_date_dt', 'quantity'], ascending=[True, False]).drop(columns=['bid_end_date_dt'])
             
        excel_filename = "latest_poct_tenders.xlsx"
        df.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"Exported {len(bids_data)} new bids to {excel_filename}")
        
        # Step 3 (Update Flag): DataFrame wale bids ki is_notified = True set karo
        for bid in latest_bids:
            bid.is_notified = True
            
        # Step 4 (Commit): Transaction commit karo DB mein
        db_session.commit()
        print("Database updated: is_notified set to True for synced bids.")
        
    except Exception as e:
        db_session.rollback()
        print(f"Error during sync: {e}")
    finally:
        db_session.close()

if __name__ == "__main__":
    sync_latest_bids_to_excel()
