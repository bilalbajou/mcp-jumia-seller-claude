# MCP Jumia Seller API

Ce serveur Model Context Protocol (MCP) permet de connecter l'assistant Claude directement à l'API Vendor de Jumia. Il donne accès aux catalogues, aux boutiques, à la gestion des produits (feeds), au programme Jumia Express (Consignment/Fulfilment by Jumia) et à la gestion complète des commandes (Orders).

## Installation

1. Assurez-vous d'avoir Python 3.10+ installé.
2. Ouvrez un terminal dans ce dossier et exécutez la commande suivante :
   ```bash
   pip install "mcp[cli]" httpx pydantic python-dotenv
   ```

## Configuration (Identifiants Jumia)

Pour communiquer avec l'API, vous devez générer des accès depuis votre Vendor Center Jumia :

1. Connectez-vous à votre [Jumia Vendor Center].
2. Allez dans **Settings** > **Integration Management** (ou API Configuration).
3. Créez une application/API Key pour obtenir votre **Client ID**.
4. Autorisez l'application pour générer un **Refresh Token** (celui-ci a une longue durée de vie et permet au serveur d'obtenir, de manière transparente, des Access Tokens jetables).

Une fois récupérés, créez un fichier `.env` dans ce dossier :
```
JUMIA_CLIENT_ID=your_client_id
JUMIA_REFRESH_TOKEN=your_refresh_token
```

## Connexion à Claude Code / Claude Desktop

### Option 1 — Commande CLI (recommandée)

```bash
claude mcp add jumia-seller 
  --env JUMIA_CLIENT_ID=your_client_id 
  --env JUMIA_REFRESH_TOKEN=your_refresh_token 
  python "d:/own project/mcp-jumia-seller/server.py"
```

> Si le fichier `.env` est déjà renseigné, omettez les flags `--env`.

### Option 2 — Fichier de configuration manuel

Ajoutez ce bloc dans `~/.claude/claude_desktop_config.json` :

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

*Supprimez le bloc `"env"` si vous utilisez le fichier `.env` du projet.*

### Vérification

```bash
claude mcp list        # doit afficher jumia-seller comme "connected"
```

Ou dans une session Claude Code, tapez `/mcp` pour voir les outils disponibles.

## Exemples de Prompts pour Claude

Une fois le serveur MCP lancé et reconnu, l'assistant Claude est capable d'orchestrer plusieurs appels d'API Jumia en arrière-plan pour accomplir des tâches complexes. Parlez-lui simplement en langage naturel !

1. **Gestion globale du compte :**
   > *"Affiche la liste de toutes les boutiques rattachées à mon compte Jumia et vérifie s'il y a des Master Shops."*

2. **Recherche de références (Catégories et Attributs) :**
   > *"Quelles sont les catégories disponibles pour les téléphones portables ? Trouve-moi l'ID de la catégorie 'Smartphones' et liste les attributs obligatoires requis pour y créer un produit."*

3. **Suivi des produits et de l'inventaire :**
   > *"Récupère les 20 derniers produits ajoutés à ma boutique 'jumia-ci' et génère un tableau croisant leurs SKUs vendeurs avec l'état de leur stock actuel."*

4. **Création et mise à jour de produits (Feeds) :**
   > *"Je veux baisser le prix de 10% pour les 3 SKUs suivants : [SKU1, SKU2, SKU3]. Utilise l'outil de mise à jour de prix, soumets le feed et surveille son statut jusqu'à ce qu'il soit validé."*
   > *"Désactive temporairement mon produit 'CASQUE-X1' sur la boutique en modifiant son statut (active = false)."*

5. **Expédier en mode Fulfilment (Jumia Express / FBJ) :**
   > *"Prépare une commande d'expédition (Consignment order) FBJ vers l'entrepôt Jumia pour la semaine prochaine avec 50 unités de la référence 'TSHIRT-BLK'. Ensuite, vérifie l'état actuel de mon stock actuellement 'quarantined' ou 'defective' pour ce même SKU."*

6. **Préparation complète des commandes (Orders) :**
   > *"Trouve toutes mes commandes en attente de la journée, vérifie leurs articles et marque-les comme prêtes à être expédiées. Enfin, imprime l'ensemble de leurs étiquettes d'expédition au format base64/PDF."*
   > *"Quels sont les transporteurs (shipment providers) disponibles pour expédier la commande X ? Emballe les produits (pack order) avec le premier transporteur de la liste."*
   > *"Annule le ou les articles de la commande ID '123456789' car une erreur a été remontée."*
