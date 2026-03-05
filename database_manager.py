from models import Tender

def process_and_save_bids(scraped_bids_list, db_session):
    """
    Process a list of scraped bids and save them to the database if they don't exist.
    """
    new_bids_added = 0
    for bid_data in scraped_bids_list:
        # The Filter Rule: Check if gem_bid_number exists in DB
        existing_bid = db_session.query(Tender).filter_by(gem_bid_number=bid_data['gem_bid_number']).first()
        
        if not existing_bid:
            # If bid number does not exist, add to DB
            new_tender = Tender(
                gem_bid_number=bid_data['gem_bid_number'],
                department_name=bid_data.get('department_name'),
                category=bid_data.get('category'),
                item_categories=bid_data.get('item_categories'),
                quantity=bid_data.get('quantity'),
                estimated_value=bid_data.get('estimated_value'),
                emd_amount=bid_data.get('emd_amount'),
                bid_end_date=bid_data.get('bid_end_date'),
                mii_applicable=bid_data.get('mii_applicable', False),
                mse_preference=bid_data.get('mse_preference', False),
                is_notified=False # Nayi bid insert karte waqt is_notified strictly False
            )
            db_session.add(new_tender)
            new_bids_added += 1
        else:
            # If bid exists, update fields that might have been modified in the schema
            updated = False
            
            new_qty = bid_data.get('quantity')
            if new_qty is not None and getattr(existing_bid, 'quantity', 1) in (1, None) and new_qty != 1:
                existing_bid.quantity = new_qty
                updated = True
                
            new_cat = bid_data.get('category')
            if new_cat and getattr(existing_bid, 'category', 'General') == 'General' and new_cat != 'General':
                existing_bid.category = new_cat
                updated = True

            if updated:
                new_bids_added += 1 # We technically didn't add a new bid, but we trigger a commit
            
    # Commit all new entries to the database
    if new_bids_added > 0:
        db_session.commit()
    
    return new_bids_added
def check_bid_exists(bid_number: str, db_session) -> bool:  
    """  
    Checks if a bid strictly exists in the SQLite database by gem_bid_number to trigger a short-circuit early exit in scraping.  
    """  
    bid = db_session.query(Tender).filter_by(gem_bid_number=bid_number).first()  
    return bid is not None 
