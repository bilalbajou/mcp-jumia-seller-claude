# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Model Context Protocol (MCP) server** that bridges Claude to the Jumia Vendor API. The entire server lives in a single file: `server.py`. It exposes Jumia seller operations (catalog, products, stock, feeds, Fulfilment by Jumia/Consignment) as MCP tools that Claude can call directly.

## Setup & Running

```bash
# Install dependencies
pip install mcp[cli] httpx pydantic python-dotenv

# Run the server directly (stdio transport, used by Claude Desktop/Code)
python server.py
```

Required environment variables in `.env`:
```
JUMIA_CLIENT_ID=your_client_id
JUMIA_REFRESH_TOKEN=your_refresh_token
```

## Claude Desktop / Claude Code Integration

Register the server in `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "jumia-seller": {
      "command": "python",
      "args": ["d:/own project/mcp-jumia-seller/server.py"],
      "env": {
        "JUMIA_CLIENT_ID": "YOUR_JUMIA_CLIENT_ID",
        "JUMIA_REFRESH_TOKEN": "YOUR_JUMIA_REFRESH_TOKEN"
      }
    }
  }
}
```

## Architecture

**Single-file MCP server** using `FastMCP` from the `mcp` package.

### Authentication flow
- `get_access_token()` — exchanges the long-lived `JUMIA_REFRESH_TOKEN` for a short-lived access token via `POST /token`. Tokens are cached in the `TokenCache` object (secured with custom `__repr__` to prevent accidental logging) and auto-refreshed with a 60-second buffer before expiry. If the API returns a new refresh token, the cache is updated automatically.
- All HTTP calls go through `_api_request()` → `api_get/post/put/patch()` helpers, which inject the `Authorization: Bearer <token>` header automatically.

### Tool categories
| Group | Tools |
|---|---|
| Shops | `jumia_get_shops`, `jumia_get_all_master_shops` |
| Catalog | `jumia_get_brands`, `jumia_get_categories`, `jumia_get_attributes`, `jumia_get_products`, `jumia_get_stock` |
| Feeds (writes) | `jumia_create_products`, `jumia_update_products`, `jumia_update_stock`, `jumia_update_price`, `jumia_update_product_status` |
| Feed tracking | `jumia_get_feed_status` |
| Consignment/FBJ | `jumia_create_consignment_order`, `jumia_update_consignment_order`, `jumia_get_consignment_stock` |
| Orders | `jumia_get_orders`, `jumia_get_order_items`, `jumia_get_shipment_providers`, `jumia_pack_orders`, `jumia_ready_to_ship`, `jumia_cancel_orders`, `jumia_print_labels` |

Write operations (feeds, consignment, orders) return an identifier (feed ID, purchase order) or throw an error. Feed processing uses `jumia_get_feed_status(feed_id)` to poll asynchronously. Write lists (products, orders) have hard limits enforced in code (max 1000/2000 per request).

### Key conventions
- All tools are `async` and return `json.dumps(..., ensure_ascii=False)`.
- `_handle_http_error()` raises descriptive French-language exceptions for HTTP 4xx/5xx responses.
- Pagination uses cursor-based `nextToken` / `isLastPage` pattern (not page numbers) for product/stock endpoints; catalog endpoints use integer `page`.
- `business_client_code` identifies the country-specific Jumia platform (e.g., `"jumia-ma"` for Morocco).
