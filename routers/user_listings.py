from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/user/{user_id}/inserate")
async def get_user_listings(user_id: str, request: Request):
    """Return all public listings for a Kleinanzeigen user ID."""
    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="user_id must contain only digits")

    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    from scrapers.user_listings import scrape_user_listings

    try:
        return await scrape_user_listings(browser_manager, user_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch user listings")
