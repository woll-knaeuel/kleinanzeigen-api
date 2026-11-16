from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from schemas import ErrorResponse, SearchResponse
from utils.content_filter import content_filter_from_params

router = APIRouter()


class InserateByUrlRequest(BaseModel):
    url: str
    max_pages: int = 1
    min_publish_date: datetime | None = None
    include_terms: str | None = None
    exclude_terms: str | None = None
    use_regex: bool = False
    match_all_include: bool = False
    case_sensitive: bool = False
    filter_fields: str = "title,description"


@router.post(
    "/inserate-by-url",
    response_model=SearchResponse,
    response_model_exclude_unset=True,
    responses={
        500: {"model": ErrorResponse, "description": "Scrape failed"},
        503: {"model": ErrorResponse, "description": "Browser manager not initialized"},
    },
)
async def inserate_by_url(request: Request, body: InserateByUrlRequest):
    """
    Scrape Kleinanzeigen listings using a full URL with all filters pre-configured.

    Pass any Kleinanzeigen search/category URL — all filters encoded in the URL
    (category, brand, year, fuel type, transmission, etc.) are preserved as-is.
    Page numbers are injected automatically for multi-page fetching.
    """
    browser_manager = request.app.state.browser_manager
    if not browser_manager:
        raise HTTPException(status_code=503, detail="Service unavailable")

    if "description_full" in [field.strip() for field in body.filter_fields.split(",")]:
        raise HTTPException(
            status_code=400,
            detail="description_full is not available on /inserate-by-url.",
        )
    content_filter = content_filter_from_params(
        include_terms=body.include_terms,
        exclude_terms=body.exclude_terms,
        use_regex=body.use_regex,
        match_all_include=body.match_all_include,
        case_sensitive=body.case_sensitive,
        filter_fields=body.filter_fields,
    )

    from scrapers.inserate_by_url import scrape_by_url

    try:
        result = await scrape_by_url(
            browser_manager=browser_manager,
            base_url=body.url,
            max_pages=body.max_pages,
            min_publish_date=body.min_publish_date,
        )
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
