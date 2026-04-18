# MCP Jumia Seller API

This Model Context Protocol (MCP) server connects the Claude assistant directly to the Jumia Vendor API. It provides access to catalogs, shops, product management (feeds), the Jumia Express program (Consignment/Fulfilment by Jumia), and comprehensive order management.

## Installation

1. Ensure you have Python 3.10+ installed.
2. Open a terminal in this directory and run the following command:
   ```bash
   pip install "mcp[cli]" httpx pydantic python-dotenv
   ```

## Configuration (Jumia Credentials)

To communicate with the API, you must generate credentials from your Jumia Vendor Center:

1. Log in to your [Jumia Vendor Center].
2. Go to **Settings** > **Integration Management** (or API Configuration).
3. Create an application/API Key to get your **Client ID**.
4. Authorize the application to generate a **Refresh Token** (this has a long lifespan and allows the server to seamlessly obtain disposable Access Tokens).

Once retrieved, create a `.env` file in this directory:
```
JUMIA_CLIENT_ID=your_client_id
JUMIA_REFRESH_TOKEN=your_refresh_token
```

## Connecting to Claude Code / Claude Desktop

### Option 1 — CLI Command (Recommended)

```bash
claude mcp add jumia-seller \
  --env JUMIA_CLIENT_ID=your_client_id \
  --env JUMIA_REFRESH_TOKEN=your_refresh_token \
  python "d:/own project/mcp-jumia-seller/server.py"
```

> If the `.env` file is already populated, omit the `--env` flags.

### Option 2 — Manual Configuration File

Add this block to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jumia-seller": {
      "command": "python",
      "args": [
        "d:/own project/mcp-jumia-seller/server.py"
      ],
      "env": {
        "JUMIA_CLIENT_ID": "YOUR_JUMIA_CLIENT_ID",
        "JUMIA_REFRESH_TOKEN": "YOUR_JUMIA_REFRESH_TOKEN"
      }
    }
  }
}
```

*Remove the `"env"` block if you are using the project's `.env` file.*

### Verification

```bash
claude mcp list        # should list jumia-seller as "connected"
```

Or within a Claude Code session, type `/mcp` to see the available tools.

## Important API Behaviours

- **Rate limit:** 200 requests/minute, 4 requests/second per mastershop. Exceeding this returns HTTP 429.
- **Feed creation vs. update:** `GET /feeds/{id}` does not return `productSid` for `PRODUCT_CREATION` feeds. Call `jumia_get_products` after creation to retrieve the SID needed for future updates.
- **Product update restrictions:** The following fields are silently ignored by `jumia_update_products`: Main Image, Main Category, Parent SKU, Global Sale Price, Initial Stock.
- **Order date scope:** `jumia_get_orders` returns only today's orders when no date filter (`created_after`/`created_before` or `updated_after`/`updated_before`) is provided.
- **Access token TTL:** 12 hours. The server caches it in memory and auto-refreshes it transparently using the Refresh Token.

## Prompt Examples for Claude

Once the MCP server is launched and recognized, the Claude assistant can orchestrate multiple Jumia API calls in the background to handle complex tasks. Just talk to it in natural language!

1. **Global Account Management:**
   > *"Display the list of all shops linked to my Jumia account and verify if there are any Master Shops."*

2. **Reference Search (Categories and Attributes):**
   > *"What categories are available for mobile phones? Find me the ID for the 'Smartphones' category and list the mandatory attributes required to create a product there."*

3. **Product and Inventory Tracking:**
   > *"Retrieve the last 20 products added to my 'jumia-ci' shop and generate a table cross-referencing their seller SKUs with their current stock status."*

4. **Product Creation and Updates (Feeds):**
   > *"I want to lower the price by 10% for the following 3 SKUs: [SKU1, SKU2, SKU3]. Use the price update tool, submit the feed, and monitor its status until it is validated."*
   > *"Temporarily disable my 'CASQUE-X1' product on the shop by modifying its status (active = false)."*

5. **Fulfilment Shipping (Jumia Express / FBJ):**
   > *"Prepare an FBJ consignment order to the Jumia warehouse for next week with 50 units of the 'TSHIRT-BLK' reference. Then, check the current status of my 'quarantined' or 'defective' stock for this same SKU."*

6. **Complete Order Preparation:**
   > *"Find all my pending orders for today, check their items, and mark them as ready to ship. Finally, print all of their shipping labels in base64/PDF format."*
   > *"What shipment providers are available to ship order X? Pack the order items using the first provided carrier from the list."*
   > *"Cancel the item(s) from order ID '123456789' because an error was reported."*
