from mcp.server.fastmcp import FastMCP
import os
import time
import httpx
import json
from typing import Any, Dict, Optional, List
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

JUMIA_BASE_URL = "https://vendor-api.jumia.com"
JUMIA_CLIENT_ID = os.getenv("JUMIA_CLIENT_ID")
JUMIA_REFRESH_TOKEN = os.getenv("JUMIA_REFRESH_TOKEN")

# Initialize FastMCP server
mcp = FastMCP("jumia-claude-mcp")

# 1. In-memory token cache (_token_cache)
class TokenCache:
    def __init__(self, refresh_token: Optional[str]):
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = refresh_token
        self.expires_at: float = 0

    def __repr__(self) -> str:
        return "<TokenCache>"

_token_cache = TokenCache(JUMIA_REFRESH_TOKEN)

# 4. Error handling function with clear messages
def _handle_http_error(response: httpx.Response) -> None:
    if response.is_success:
        return
        
    status = response.status_code
    try:
        data = response.json()
        message = data.get("message", response.text)
    except Exception:
        message = response.text

    error_mappings = {
        400: "Bad Request (400): The request is invalid or malformed.",
        401: "Unauthorized (401): Authentication failed. Check your credentials.",
        403: "Forbidden (403): You do not have permission for this action.",
        404: "Not Found (404): The requested resource does not exist.",
        422: "Unprocessable Entity (422): Data validation error for the sent payload.",
        429: "Too Many Requests (429): API call limit reached (Rate Limiting).",
        500: "Internal Server Error (500): Internal error on the Jumia server.",
        501: "Not Implemented (501): Feature not implemented by the API."
    }

    error_msg = error_mappings.get(status, f"HTTP Error {status}")
    raise Exception(f"{error_msg} Details: {message}")

# 2. Async function to retrieve and manage token access
async def get_access_token() -> str:
    global _token_cache
    
    current_refresh_token = _token_cache.refresh_token
    if not JUMIA_CLIENT_ID or not current_refresh_token:
        raise Exception("JUMIA_CLIENT_ID and JUMIA_REFRESH_TOKEN are required in the .env file")
        
    now = time.time()
    
    # Return cached token if it's still valid (60s margin)
    if _token_cache.access_token and _token_cache.expires_at > now + 60:
        return _token_cache.access_token
        
    async with httpx.AsyncClient() as client:
        # POST /token call to refresh it
        response = await client.post(
            f"{JUMIA_BASE_URL}/token",
            data={
                "client_id": JUMIA_CLIENT_ID,
                "refresh_token": current_refresh_token,
                "grant_type": "refresh_token"
            }
        )
        
        _handle_http_error(response)
        
        token_data = response.json()
        
        _token_cache.access_token = token_data.get("access_token")
        # expires_in is the expiration time provided by Jumia (usually in seconds)
        _token_cache.expires_at = now + token_data.get("expires_in", 3600)
        
        # Save the new returned refresh_token
        if "refresh_token" in token_data:
            _token_cache.refresh_token = token_data["refresh_token"]
            
        return _token_cache.access_token

# Internal function to centralize API calls
async def _api_request(method: str, endpoint: str, **kwargs) -> Any:
    token = await get_access_token()
    headers = kwargs.pop("headers", {})
    # Automatically add the Authorization header
    headers["Authorization"] = f"Bearer {token}"
    
    url = f"{JUMIA_BASE_URL}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, **kwargs)
        _handle_http_error(response)
        
        try:
            return response.json()
        except Exception:
            return response.text

# 3. Utility functions
async def api_get(endpoint: str, **kwargs) -> Any:
    return await _api_request("GET", endpoint, **kwargs)

async def api_post(endpoint: str, **kwargs) -> Any:
    return await _api_request("POST", endpoint, **kwargs)

async def api_put(endpoint: str, **kwargs) -> Any:
    return await _api_request("PUT", endpoint, **kwargs)

async def api_patch(endpoint: str, **kwargs) -> Any:
    return await _api_request("PATCH", endpoint, **kwargs)

# === MCP Tools ===

@mcp.tool()
async def jumia_get_shops() -> str:
    """
    Retrieves the list of Jumia shops associated with the account.
    No parameters are required.
    Returns shop details such as ID, name, email, and Business Clients.
    [readOnlyHint: true]
    """
    result = await api_get("/shops")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_all_master_shops() -> str:
    """
    Retrieves all shops of a master shop,
    including shops spread across multiple countries.
    No parameters are required.
    [readOnlyHint: true]
    """
    result = await api_get("/shops-of-master-shop")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_brands(
    page: int = Field(default=1, description="Page number")
) -> str:
    """
    Retrieves the list of Jumia brands.
    Returns: current_page, total_pages, brands[]
    [readOnlyHint: true]
    """
    params = {"page": page}
    result = await api_get("/catalog/brands", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_categories(
    page: int = Field(default=1, description="Page number"),
    attribute_set_name: Optional[str] = Field(default=None, description="Filter by attribute set name")
) -> str:
    """
    Retrieves the list of Jumia categories.
    Returns: current_page, total_pages, categories[]
    [readOnlyHint: true]
    """
    params = {"page": page}
    if attribute_set_name:
        params["attribute_set_name"] = attribute_set_name
    result = await api_get("/catalog/categories", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_attributes(
    attribute_set_id: str = Field(..., description="UUID of the attribute set (required)")
) -> str:
    """
    Retrieves the list of attributes for a given attribute set.
    Returns the attribute list including code, type, mandatory, options...
    [readOnlyHint: true]
    """
    result = await api_get(f"/catalog/attribute-sets/{attribute_set_id}")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_products(
    token: Optional[str] = Field(default=None, description="Token for pagination (nextToken)"),
    size: int = Field(default=10, ge=1, le=100, description="Page size (1-100)"),
    seller_sku: Optional[str] = Field(default=None, description="Filter by seller SKU"),
    shop_id: Optional[str] = Field(default=None, description="Filter by Shop ID"),
    category_code: Optional[str] = Field(default=None, description="Filter by Category Code"),
    created_at_from: Optional[str] = Field(default=None, description="Creation date (start)"),
    created_at_to: Optional[str] = Field(default=None, description="Creation date (end)")
) -> str:
    """
    Retrieves the list of products from the Jumia catalog.
    Returns: products[], nextToken, isLastPage
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"size": size}
    if token is not None: params["token"] = token
    if seller_sku is not None: params["seller_sku"] = seller_sku
    if shop_id is not None: params["shop_id"] = shop_id
    if category_code is not None: params["category_code"] = category_code
    if created_at_from is not None: params["created_at_from"] = created_at_from
    if created_at_to is not None: params["created_at_to"] = created_at_to
    
    result = await api_get("/catalog/products", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_stock(
    size: int = Field(default=10, ge=1, le=100, description="Page size (1-100)"),
    token: Optional[str] = Field(default=None, description="Pagination token"),
    product_sids: Optional[List[str]] = Field(default=None, description="List of Product SIDs")
) -> str:
    """
    Retrieves the stock of products from the Jumia catalog.
    Returns: products[], nextToken, isLastPage
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"size": size}
    if token is not None: params["token"] = token
    if product_sids is not None: params["product_sids"] = product_sids
        
    result = await api_get("/catalog/stock", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_feed_status(
    feed_id: str = Field(..., description="UUID of the feed (required)")
) -> str:
    """
    Retrieves the status of a feed.
    Returns: status, feedType, total, completed, failed, feedItems[]
    [readOnlyHint: true]
    """
    result = await api_get(f"/feeds/{feed_id}")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_create_products(
    shop_id: str = Field(..., description="Shop UUID"),
    products: List[Dict[str, Any]] = Field(..., description="List of products to create (max 1000)")
) -> str:
    """
    Creates new products via a feed.
    Returns the feed ID (+ a suggestion message to monitor with jumia_get_feed_status).
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("The 'products' list cannot contain more than 1000 items.")
    body = {"shop_id": shop_id, "products": products}
    result = await api_post("/feeds/products/create", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_products(
    products: List[Dict[str, Any]] = Field(..., description="List of products to update (with id=productSid)"),
    shop_id: Optional[str] = Field(default=None, description="Shop UUID (optional)")
) -> str:
    """
    Updates existing products via a feed.
    Returns the feed ID. You can monitor its status with jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("The 'products' list cannot contain more than 1000 items.")
    body = {"products": products}
    if shop_id:
        body["shop_id"] = shop_id
    result = await api_post("/feeds/products/update", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_stock(
    products: List[Dict[str, Any]] = Field(..., description="List of stocks to update ({sellerSku, id, stock})")
) -> str:
    """
    Updates product stock via a feed.
    Returns the feed ID. You can monitor its status with jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("The 'products' list cannot contain more than 1000 items.")
    body = {"products": products}
    result = await api_post("/feeds/products/stock", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_price(
    products: List[Dict[str, Any]] = Field(..., description="List of prices to update ({price.currency, price.value, price.salePrice, etc.})")
) -> str:
    """
    Updates product prices via a feed.
    Returns the feed ID. You can monitor its status with jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("The 'products' list cannot contain more than 1000 items.")
    body = {"products": products}
    result = await api_post("/feeds/products/price", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_product_status(
    products: List[Dict[str, Any]] = Field(..., description="List of statuses to update ({sellerSku, id, createdAt, businessClients})")
) -> str:
    """
    Updates product status via a feed.
    Returns the feed ID. You can monitor its status with jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("The 'products' list cannot contain more than 1000 items.")
    body = {"products": products}
    result = await api_post("/feeds/products/status", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_create_consignment_order(
    shop_id: str = Field(..., description="Shop UUID"),
    business_client_code: str = Field(..., description='Platform code, e.g., "jumia-ma"'),
    shipping_date: str = Field(..., description="Expected shipping date"),
    products: List[Dict[str, Any]] = Field(..., description="List of products to ship (max 2000)"),
    comment: Optional[str] = Field(default=None, description="Optional comment")
) -> str:
    """
    Creates a new consignment order (Fulfilment by Jumia).
    Returns the purchaseOrderNumber.
    [readOnlyHint: false]
    """
    if len(products) > 2000:
        raise ValueError("The 'products' list cannot contain more than 2000 items.")
    body: Dict[str, Any] = {
        "shop_id": shop_id,
        "business_client_code": business_client_code,
        "shipping_date": shipping_date,
        "products": products
    }
    if comment:
        body["comment"] = comment
    result = await api_post("/consignment-order", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_consignment_order(
    purchase_order_number: str = Field(..., description="The Purchase Order Number"),
    is_shipped: bool = Field(..., description="Indicates whether the order has been shipped"),
    tracking_number: Optional[str] = Field(default=None, description="Tracking number (required if is_shipped=true)"),
    actual_departure_date: Optional[str] = Field(default=None, description="Actual departure date"),
    estimated_arrival_date: Optional[str] = Field(default=None, description="Estimated arrival date"),
    delivery_agent_phone: Optional[str] = Field(default=None, description="Delivery agent phone number"),
    three_pl_name: Optional[str] = Field(default=None, description="Name of the 3PL carrier")
) -> str:
    """
    Updates an existing consignment order (Fulfilment by Jumia).
    [readOnlyHint: false]
    """
    body: Dict[str, Any] = {"is_shipped": is_shipped}
    if tracking_number is not None: body["tracking_number"] = tracking_number
    if actual_departure_date is not None: body["actual_departure_date"] = actual_departure_date
    if estimated_arrival_date is not None: body["estimated_arrival_date"] = estimated_arrival_date
    if delivery_agent_phone is not None: body["delivery_agent_phone"] = delivery_agent_phone
    if three_pl_name is not None: body["three_pl_name"] = three_pl_name
        
    result = await api_patch(f"/consignment-order/{purchase_order_number}", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_consignment_stock(
    business_client_code: str = Field(..., description='Platform code, e.g., "jumia-ma"'),
    sku: str = Field(..., description="Product SKU (Seller SKU)")
) -> str:
    """
    Retrieves the status of consignment stock (sent via Fulfilment).
    Returns: received, quarantined, defective, canceled, returned, failed.
    [readOnlyHint: true]
    """
    params = {
        "business_client_code": business_client_code,
        "sku": sku
    }
    result = await api_get("/consignment-stock", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

# === New Orders Block ===

@mcp.tool()
async def jumia_get_orders(
    status: Optional[str] = Field(default=None, description="Filter by status"),
    country: Optional[str] = Field(default=None, description="Country code (e.g., MA)"),
    shop_id: Optional[str] = Field(default=None, description="Shop UUID"),
    created_after: Optional[str] = Field(default=None, description="Creation date start"),
    created_before: Optional[str] = Field(default=None, description="Creation date end"),
    updated_after: Optional[str] = Field(default=None, description="Update date start"),
    updated_before: Optional[str] = Field(default=None, description="Update date end"),
    size: int = Field(default=10, le=300, description="List size (max 300)"),
    sort: Optional[str] = Field(default=None, description="Sort, ASC or DESC"),
    token: Optional[str] = Field(default=None, description="Pagination token")
) -> str:
    """
    Retrieves orders (GET /orders).
    Important: without date filters (created_after/before or updated_after/before), 
    only today's orders are returned.
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"size": size}
    if status is not None: params["status"] = status
    if country is not None: params["country"] = country
    if shop_id is not None: params["shop_id"] = shop_id
    if created_after is not None: params["created_after"] = created_after
    if created_before is not None: params["created_before"] = created_before
    if updated_after is not None: params["updated_after"] = updated_after
    if updated_before is not None: params["updated_before"] = updated_before
    if sort is not None: params["sort"] = sort
    if token is not None: params["token"] = token
        
    result = await api_get("/orders", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_order_items(
    order_ids: List[str] = Field(..., description="List of order IDs"),
    status: Optional[str] = Field(default=None, description="Status of the items"),
    shop_id: Optional[str] = Field(default=None, description="Shop UUID")
) -> str:
    """
    Retrieves items for a list of orders (GET /orders/items).
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"order_ids": order_ids}
    if status is not None: params["status"] = status
    if shop_id is not None: params["shop_id"] = shop_id
    result = await api_get("/orders/items", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_shipment_providers(
    order_item_ids: List[str] = Field(..., description="List of article IDs (order items)")
) -> str:
    """
    Retrieves available carriers (GET /orders/shipment-providers).
    [readOnlyHint: true]
    """
    params = {"order_item_ids": order_item_ids}
    result = await api_get("/orders/shipment-providers", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_pack_orders(
    packages: List[Dict[str, Any]] = Field(..., description="List of packages ({orderItems, shipmentProviderId, trackingCode})")
) -> str:
    """
    Prepares and packs orders (POST /v2/orders/pack).
    Returns success.packages[] and error.packages[] among other data.
    [readOnlyHint: false]
    """
    body = {"packages": packages}
    result = await api_post("/v2/orders/pack", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_ready_to_ship(
    orderItemIds: List[str] = Field(..., description="List of article UUIDs")
) -> str:
    """
    Marks items as 'Ready To Ship' (POST /orders/ready-to-ship).
    [readOnlyHint: false]
    """
    body = {"orderItemIds": orderItemIds}
    result = await api_post("/orders/ready-to-ship", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_cancel_orders(
    orderItemIds: List[str] = Field(..., description="List of article UUIDs to cancel")
) -> str:
    """
    Cancels order items (PUT /orders/cancel).
    [readOnlyHint: false]
    """
    body = {"orderItemIds": orderItemIds}
    result = await api_put("/orders/cancel", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_print_labels(
    orderItemIds: List[str] = Field(..., description="List of article UUIDs (max 200)")
) -> str:
    """
    Displays and returns shipping labels in base64 PDF (POST /orders/print-labels).
    [readOnlyHint: false]
    """
    if len(orderItemIds) > 200:
        raise ValueError("The 'orderItemIds' list cannot contain more than 200 items.")
    body = {"orderItemIds": orderItemIds}
    result = await api_post("/orders/print-labels", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # Run the server with stdio transport
    mcp.run(transport="stdio")
