"""
Ultra-optimized router for maximum performance scraping.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from schemas import ErrorResponse, SearchResponse
from scrapers.inserate_ultra_optimized import ultra_optimized_scrape_inserate
from utils.content_filter import content_filter_from_params

router = APIRouter()


@router.get(
    "/inserate",
    response_model=SearchResponse,
    response_model_exclude_unset=True,
    responses={
        500: {"model": ErrorResponse, "description": "Scrape failed"},
        503: {"model": ErrorResponse, "description": "Browser manager not initialized"},
    },
)
async def get_inserate_ultra_optimized(
    request: Request,
    query: str = Query(None, description="Search query string"),
    location: str = Query(None, description="Location filter"),
    radius: int = Query(None, description="Search radius in kilometers"),
    min_price: int = Query(None, description="Minimum price filter"),
    max_price: int = Query(None, description="Maximum price filter"),
    category_id: int | None = Query(
        None, ge=1, description="Kleinanzeigen category ID"
    ),
    category_slug: str | None = Query(None, description="Optional category path slug"),
    page: int = Query(1, ge=1, description="First page to fetch"),
    page_count: int | None = Query(
        None,
        ge=1,
        le=50,
        description="Pages to fetch; omitted = automatic pagination (up to 50 pages)",
    ),
    min_publish_date: datetime | None = Query(
        None,
        description="Stop fetching once listings published before this datetime (inclusive, format: YYYY-MM-DDTHH:MM:SS)",
    ),
    include_terms: str | None = Query(
        None, description="Comma-separated terms; at least one must match"
    ),
    exclude_terms: str | None = Query(
        None, description="Comma-separated terms that must not match"
    ),
    use_regex: bool = Query(False),
    match_all_include: bool = Query(False),
    case_sensitive: bool = Query(False),
    filter_fields: str = Query("title,description"),
):
    """
    Fetch listings based on search criteria.

    Retrieves listings from Kleinanzeigen with support for various filters
    including location, price range, and search terms. Results are returned
    with performance metrics and success indicators.
    """
    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    if "description_full" in [field.strip() for field in filter_fields.split(",")]:
        raise HTTPException(
            status_code=400,
            detail="description_full is not available on /inserate; use /inserate-detailed.",
        )
    content_filter = content_filter_from_params(
        include_terms=include_terms,
        exclude_terms=exclude_terms,
        use_regex=use_regex,
        match_all_include=match_all_include,
        case_sensitive=case_sensitive,
        filter_fields=filter_fields,
    )

    try:
        # Execute ultra-optimized scraping
        result = await ultra_optimized_scrape_inserate(
            browser_manager=browser_manager,
            query=query,
            location=location,
            radius=radius,
            min_price=min_price,
            max_price=max_price,
            category_id=category_id,
            category_slug=category_slug,
            page=page,
            page_count=page_count,
            min_publish_date=min_publish_date,
        )

        # Clean up response - remove excessive metrics for production
        if "task_metrics" in result:
            del result["task_metrics"]
        if "optimization_features" in result:
            del result["optimization_features"]

        # Simplify performance metrics
        if "performance_metrics" in result:
            metrics = result["performance_metrics"]
            # Keep only essential metrics
            essential_metrics = {
                "pages_requested": metrics.get("pages_requested", 0),
                "pages_successful": metrics.get("pages_successful", 0),
                "success_rate": metrics.get("success_rate", 0),
                "average_page_time": metrics.get("average_page_time", 0),
            }
            result["performance_metrics"] = essential_metrics

        if content_filter.active:
            original_results = result.get("results", [])
            filtered_results = content_filter.apply(original_results)
            result["results"] = filtered_results
            result["unique_results"] = len(filtered_results)
            result["content_filter_meta"] = {
                **content_filter.summary(),
                "results_before_filter": len(original_results),
                "results_after_filter": len(filtered_results),
                "filtered_out": len(original_results) - len(filtered_results),
            }

        return result

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
