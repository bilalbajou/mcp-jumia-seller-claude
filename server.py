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

# 1. Un cache token en mémoire (_token_cache)
class TokenCache:
    def __init__(self, refresh_token: Optional[str]):
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = refresh_token
        self.expires_at: float = 0

    def __repr__(self) -> str:
        return "<TokenCache>"

_token_cache = TokenCache(JUMIA_REFRESH_TOKEN)

# 4. Fonction de gestion des erreurs avec messages clairs
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
        400: "Bad Request (400): La requête est invalide ou mal formatée.",
        401: "Unauthorized (401): Échec d'authentification. Vérifiez les credentials.",
        403: "Forbidden (403): Vous n'avez pas les droits pour cette action.",
        404: "Not Found (404): La ressource demandée n'existe pas.",
        422: "Unprocessable Entity (422): Erreur de validation des données envoyées.",
        429: "Too Many Requests (429): Limite d'appels API atteinte (Rate Limiting).",
        500: "Internal Server Error (500): Erreur interne du serveur Jumia.",
        501: "Not Implemented (501): Fonctionnalité non implémentée par l'API."
    }

    error_msg = error_mappings.get(status, f"Erreur HTTP {status}")
    raise Exception(f"{error_msg} Détails: {message}")

# 2. Fonction async pour obtenir et gérer l'accès au token
async def get_access_token() -> str:
    global _token_cache
    
    current_refresh_token = _token_cache.refresh_token
    if not JUMIA_CLIENT_ID or not current_refresh_token:
        raise Exception("JUMIA_CLIENT_ID et JUMIA_REFRESH_TOKEN sont requis dans le fichier .env")
        
    now = time.time()
    
    # Retourne le token en cache s'il est encore valide (marge de 60s)
    if _token_cache.access_token and _token_cache.expires_at > now + 60:
        return _token_cache.access_token
        
    async with httpx.AsyncClient() as client:
        # Appel POST /token pour le renouveler
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
        # expires_in est le délai d'expiration fourni par Jumia (généralement en secondes)
        _token_cache.expires_at = now + token_data.get("expires_in", 3600)
        
        # Sauvegarde du nouveau refresh_token retourné
        if "refresh_token" in token_data:
            _token_cache.refresh_token = token_data["refresh_token"]
            
        return _token_cache.access_token

# Fonction interne pour centraliser l'appel API
async def _api_request(method: str, endpoint: str, **kwargs) -> Any:
    token = await get_access_token()
    headers = kwargs.pop("headers", {})
    # Ajout automatique du header Authorization
    headers["Authorization"] = f"Bearer {token}"
    
    url = f"{JUMIA_BASE_URL}{endpoint}"
    
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, **kwargs)
        _handle_http_error(response)
        
        try:
            return response.json()
        except Exception:
            return response.text

# 3. Fonctions utilitaires
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
    Récupère la liste des boutiques Jumia (shops) associées au compte.
    Aucun paramètre n'est requis.
    Retourne les détails des boutiques tels que l'ID, le nom, l'email et les Business Clients.
    [readOnlyHint: true]
    """
    result = await api_get("/shops")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_all_master_shops() -> str:
    """
    Récupère toutes les boutiques d'une boutique principale (master shop),
    incluant les boutiques réparties sur plusieurs pays.
    Aucun paramètre n'est requis.
    [readOnlyHint: true]
    """
    result = await api_get("/shops-of-master-shop")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_brands(
    page: int = Field(default=1, description="Numéro de la page")
) -> str:
    """
    Récupère la liste des marques Jumia.
    Retourne : current_page, total_pages, brands[]
    [readOnlyHint: true]
    """
    params = {"page": page}
    result = await api_get("/catalog/brands", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_categories(
    page: int = Field(default=1, description="Numéro de la page"),
    attribute_set_name: Optional[str] = Field(default=None, description="Filtrer par nom de set d'attributs")
) -> str:
    """
    Récupère la liste des catégories Jumia.
    Retourne : current_page, total_pages, categories[]
    [readOnlyHint: true]
    """
    params = {"page": page}
    if attribute_set_name:
        params["attribute_set_name"] = attribute_set_name
    result = await api_get("/catalog/categories", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_attributes(
    attribute_set_id: str = Field(..., description="UUID de l'attribute set (requis)")
) -> str:
    """
    Récupère la liste des attributs pour un attribute set donné.
    Retourne la liste des attributs avec code, type, mandatory, options...
    [readOnlyHint: true]
    """
    result = await api_get(f"/catalog/attribute-sets/{attribute_set_id}")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_products(
    token: Optional[str] = Field(default=None, description="Token pour la pagination (nextToken)"),
    size: int = Field(default=10, ge=1, le=100, description="Taille de la page (1-100)"),
    seller_sku: Optional[str] = Field(default=None, description="Filtrer par SKU vendeur"),
    shop_id: Optional[str] = Field(default=None, description="Filtrer par identifiant Shop"),
    category_code: Optional[str] = Field(default=None, description="Filtrer par Category Code"),
    created_at_from: Optional[str] = Field(default=None, description="Date de création (début)"),
    created_at_to: Optional[str] = Field(default=None, description="Date de création (fin)")
) -> str:
    """
    Récupère la liste des produits du catalogue Jumia.
    Retourne : products[], nextToken, isLastPage
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
    size: int = Field(default=10, ge=1, le=100, description="Taille de la page (1-100)"),
    token: Optional[str] = Field(default=None, description="Token de pagination"),
    product_sids: Optional[List[str]] = Field(default=None, description="Liste de Product SIDs")
) -> str:
    """
    Récupère le stock des produits du catalogue Jumia.
    Retourne : products[], nextToken, isLastPage
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"size": size}
    if token is not None: params["token"] = token
    if product_sids is not None: params["product_sids"] = product_sids
        
    result = await api_get("/catalog/stock", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_feed_status(
    feed_id: str = Field(..., description="UUID du feed (requis)")
) -> str:
    """
    Récupère le statut d'un feed.
    Retourne : status, feedType, total, completed, failed, feedItems[]
    [readOnlyHint: true]
    """
    result = await api_get(f"/feeds/{feed_id}")
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_create_products(
    shop_id: str = Field(..., description="UUID de la boutique"),
    products: List[Dict[str, Any]] = Field(..., description="Liste des produits à créer (max 1000)")
) -> str:
    """
    Crée de nouveaux produits via un feed.
    Retourne l'ID du feed (+ un message de suggestion pour surveiller avec jumia_get_feed_status).
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 1000 éléments.")
    body = {"shop_id": shop_id, "products": products}
    result = await api_post("/feeds/products/create", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_products(
    products: List[Dict[str, Any]] = Field(..., description="Liste des produits à mettre à jour (avec id=productSid)"),
    shop_id: Optional[str] = Field(default=None, description="UUID de la boutique (optionnel)")
) -> str:
    """
    Met à jour des produits existants via un feed.
    Retourne l'ID du feed. Vous pouvez surveiller son statut avec jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 1000 éléments.")
    body = {"products": products}
    if shop_id:
        body["shop_id"] = shop_id
    result = await api_post("/feeds/products/update", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_stock(
    products: List[Dict[str, Any]] = Field(..., description="Liste des stocks à mettre à jour ({sellerSku, id, stock})")
) -> str:
    """
    Met à jour le stock des produits via un feed.
    Retourne l'ID du feed. Vous pouvez surveiller son statut avec jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 1000 éléments.")
    body = {"products": products}
    result = await api_post("/feeds/products/stock", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_price(
    products: List[Dict[str, Any]] = Field(..., description="Liste des prix à mettre à jour ({price.currency, price.value, price.salePrice, etc.})")
) -> str:
    """
    Met à jour les prix des produits via un feed.
    Retourne l'ID du feed. Vous pouvez surveiller son statut avec jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 1000 éléments.")
    body = {"products": products}
    result = await api_post("/feeds/products/price", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_update_product_status(
    products: List[Dict[str, Any]] = Field(..., description="Liste des statuts à mettre à jour ({sellerSku, id, createdAt, businessClients})")
) -> str:
    """
    Met à jour le statut des produits via un feed.
    Retourne l'ID du feed. Vous pouvez surveiller son statut avec jumia_get_feed_status.
    [readOnlyHint: false]
    """
    if len(products) > 1000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 1000 éléments.")
    body = {"products": products}
    result = await api_post("/feeds/products/status", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_create_consignment_order(
    shop_id: str = Field(..., description="UUID de la boutique"),
    business_client_code: str = Field(..., description='Code de la plateforme, ex: "jumia-ma"'),
    shipping_date: str = Field(..., description="Date d'expédition prévue"),
    products: List[Dict[str, Any]] = Field(..., description="Liste des produits à expédier (max 2000)"),
    comment: Optional[str] = Field(default=None, description="Commentaire optionnel")
) -> str:
    """
    Crée une nouvelle commande de consignment (Fulfilment by Jumia).
    Retourne le purchaseOrderNumber.
    [readOnlyHint: false]
    """
    if len(products) > 2000:
        raise ValueError("La liste 'products' ne peut pas contenir plus de 2000 éléments.")
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
    purchase_order_number: str = Field(..., description="Le numéro de Commande (Purchase Order Number)"),
    is_shipped: bool = Field(..., description="Indique si la commande a été expédiée"),
    tracking_number: Optional[str] = Field(default=None, description="Numéro de suivi (requis si is_shipped=true)"),
    actual_departure_date: Optional[str] = Field(default=None, description="Date de départ réelle"),
    estimated_arrival_date: Optional[str] = Field(default=None, description="Date d'arrivée estimée"),
    delivery_agent_phone: Optional[str] = Field(default=None, description="Téléphone de l'agent de livraison"),
    three_pl_name: Optional[str] = Field(default=None, description="Nom du transporteur 3PL")
) -> str:
    """
    Met à jour une commande de consignment (Fulfilment by Jumia) existante.
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
    business_client_code: str = Field(..., description='Code de la plateforme, ex: "jumia-ma"'),
    sku: str = Field(..., description="SKU du produit (Seller SKU)")
) -> str:
    """
    Récupère l'état du stock de consignment (envoyé via Fulfilment).
    Retourne : received, quarantined, defective, canceled, returned, failed.
    [readOnlyHint: true]
    """
    params = {
        "business_client_code": business_client_code,
        "sku": sku
    }
    result = await api_get("/consignment-stock", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

# === Nouveau Bloc Orders (Commandes) ===

@mcp.tool()
async def jumia_get_orders(
    status: Optional[str] = Field(default=None, description="Filtrer par statut"),
    country: Optional[str] = Field(default=None, description="Code pays (ex: MA)"),
    shop_id: Optional[str] = Field(default=None, description="UUID de la boutique"),
    created_after: Optional[str] = Field(default=None, description="Date de création début"),
    created_before: Optional[str] = Field(default=None, description="Date de création fin"),
    updated_after: Optional[str] = Field(default=None, description="Date de mise à jour début"),
    updated_before: Optional[str] = Field(default=None, description="Date de mise à jour fin"),
    size: int = Field(default=10, le=300, description="Taille de la liste (max 300)"),
    sort: Optional[str] = Field(default=None, description="Tri, ASC ou DESC"),
    token: Optional[str] = Field(default=None, description="Token de pagination")
) -> str:
    """
    Récupère les commandes (GET /orders).
    Important : sans filtre date (created_after/before ou updated_after/before), 
    seules les commandes du jour sont retournées.
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
    order_ids: List[str] = Field(..., description="Liste des IDs de commandes"),
    status: Optional[str] = Field(default=None, description="Statut des articles"),
    shop_id: Optional[str] = Field(default=None, description="UUID de la boutique")
) -> str:
    """
    Récupère les articles d'une liste de commandes (GET /orders/items).
    [readOnlyHint: true]
    """
    params: Dict[str, Any] = {"order_ids": order_ids}
    if status is not None: params["status"] = status
    if shop_id is not None: params["shop_id"] = shop_id
    result = await api_get("/orders/items", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_get_shipment_providers(
    order_item_ids: List[str] = Field(..., description="Liste des IDs d'articles (order items)")
) -> str:
    """
    Récupère les transporteurs disponibles (GET /orders/shipment-providers).
    [readOnlyHint: true]
    """
    params = {"order_item_ids": order_item_ids}
    result = await api_get("/orders/shipment-providers", params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_pack_orders(
    packages: List[Dict[str, Any]] = Field(..., description="Liste de packages ({orderItems, shipmentProviderId, trackingCode})")
) -> str:
    """
    Prépare et emballe des commandes (POST /v2/orders/pack).
    Retourne entre autres success.packages[] et error.packages[].
    [readOnlyHint: false]
    """
    body = {"packages": packages}
    result = await api_post("/v2/orders/pack", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_ready_to_ship(
    orderItemIds: List[str] = Field(..., description="Liste d'UUIDs d'articles")
) -> str:
    """
    Marque les articles comme 'Ready To Ship' (POST /orders/ready-to-ship).
    [readOnlyHint: false]
    """
    body = {"orderItemIds": orderItemIds}
    result = await api_post("/orders/ready-to-ship", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_cancel_orders(
    orderItemIds: List[str] = Field(..., description="Liste d'UUIDs d'articles à annuler")
) -> str:
    """
    Annule des articles de commande (PUT /orders/cancel).
    [readOnlyHint: false]
    """
    body = {"orderItemIds": orderItemIds}
    result = await api_put("/orders/cancel", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

@mcp.tool()
async def jumia_print_labels(
    orderItemIds: List[str] = Field(..., description="Liste d'UUIDs d'articles (max 200)")
) -> str:
    """
    Affiche et retourne les étiquettes en base64 PDF (POST /orders/print-labels).
    [readOnlyHint: false]
    """
    if len(orderItemIds) > 200:
        raise ValueError("La liste 'orderItemIds' ne peut pas contenir plus de 200 éléments.")
    body = {"orderItemIds": orderItemIds}
    result = await api_post("/orders/print-labels", json=body)
    return json.dumps(result, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    # Run the server with stdio transport
    mcp.run(transport="stdio")
