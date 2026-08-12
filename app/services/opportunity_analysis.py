from __future__ import annotations

import re
import unicodedata

import httpx

from app.config import settings


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


FAMILY_RULES = [

    {
        "key": "pulled_pork",
        "label": "Pulled Pork",
        "name_terms": [
            "pulled pork",
        ],
        "signals": [
            "pulled pork",
            "cerdo desmenuzado",
            "cerdo mechado",
            "mechada de cerdo",
            "sandwich de cerdo",
            "sándwich de cerdo",
        ],
    },

    {
        "key": "baby_back",
        "label": "Costillas Baby Back",
        "name_terms": [
            "baby back",
            "babyback",
        ],
        "signals": [
            "baby back",
            "babyback",
            "costillas bbq",
            "costilla bbq",
            "ribs",
        ],
    },

    {
        "key": "st_louis",
        "label": "Costillas St. Louis",
        "name_terms": [
            "st louis",
            "st. louis",
        ],
        "signals": [
            "st louis",
            "st. louis",
            "costillas",
            "ribs",
        ],
    },

    {
        "key": "pechuga",
        "label": "Pechuga de pollo",
        "name_terms": [
            "pechuga",
        ],
        "signals": [
            "pechuga",
            "pollo grill",
            "pollo grille",
            "pollo a la plancha",
            "sandwich de pollo",
            "sándwich de pollo",
            "chicken",
        ],
    },

    {
        "key": "tuto",
        "label": "Tuto de pollo",
        "name_terms": [
            "tuto",
            "trutro",
        ],
        "signals": [
            "tuto",
            "trutro",
            "pollo asado",
            "pollo al horno",
        ],
    },

    # Encurtidos antes de vegetales genéricos

    {
        "key": "encurtido_cebolla",
        "label": "Cebolla encurtida",
        "name_terms": [
            "cebolla encurtida",
            "encurtido de cebolla",
            "encurtido cebolla",
        ],
        "signals": [
            "cebolla encurtida",
            "cebolla pickle",
            "pickled onion",
            "pickled onions",
        ],
    },

    {
        "key": "encurtido_aji",
        "label": "Ají encurtido",
        "name_terms": [
            "aji encurtido",
            "ají encurtido",
            "encurtido de aji",
            "encurtido de ají",
        ],
        "signals": [
            "aji encurtido",
            "ají encurtido",
            "jalapeno encurtido",
            "jalapeño encurtido",
            "pickled jalapeno",
        ],
    },

    {
        "key": "encurtido_repollo",
        "label": "Repollo encurtido",
        "name_terms": [
            "repollo encurtido",
            "encurtido de repollo",
        ],
        "signals": [
            "repollo encurtido",
            "col encurtida",
            "pickled cabbage",
        ],
    },

    {
        "key": "tomate",
        "label": "Tomate",
        "name_terms": [
            "tomate",
        ],
        "signals": [
            "tomate",
            "tomatoes",
            "tomato",
        ],
    },

    {
        "key": "palta",
        "label": "Palta",
        "name_terms": [
            "palta",
        ],
        "signals": [
            "palta",
            "aguacate",
            "avocado",
        ],
    },

    {
        "key": "cebolla",
        "label": "Cebolla",
        "name_terms": [
            "cebolla",
        ],
        "signals": [
            "cebolla",
            "onion",
        ],
    },

    {
        "key": "zanahoria",
        "label": "Zanahoria",
        "name_terms": [
            "zanahoria",
        ],
        "signals": [
            "zanahoria",
            "carrot",
        ],
    },

    {
        "key": "apio",
        "label": "Apio",
        "name_terms": [
            "apio",
        ],
        "signals": [
            "apio",
            "celery",
        ],
    },

    {
        "key": "repollo",
        "label": "Repollo morado",
        "name_terms": [
            "repollo",
        ],
        "signals": [
            "repollo morado",
            "repollo",
            "col morada",
            "purple cabbage",
        ],
    },

    {
        "key": "aji",
        "label": "Ají",
        "name_terms": [
            "aji",
            "ají",
        ],
        "signals": [
            "aji verde",
            "ají verde",
            "jalapeno",
            "jalapeño",
        ],
    },

    {
        "key": "papa",
        "label": "Papa",
        "name_terms": [
            "papa ",
            "papa",
        ],
        "signals": [
            "papas fritas",
            "papa frita",
            "papas",
            "potato",
            "fries",
        ],
    },

    {
        "key": "betarraga",
        "label": "Betarraga",
        "name_terms": [
            "betarraga",
        ],
        "signals": [
            "betarraga",
            "remolacha",
            "beetroot",
        ],
    },

    {
        "key": "chimichurri",
        "label": "Chimichurri",
        "name_terms": [
            "chimichurri",
        ],
        "signals": [
            "chimichurri",
        ],
    },

    {
        "key": "bbq",
        "label": "Salsa BBQ",
        "name_terms": [
            "bbq",
        ],
        "signals": [
            "bbq",
            "barbecue",
            "barbacoa",
        ],
    },

    {
        "key": "mostaza_miel",
        "label": "Mostaza miel",
        "name_terms": [
            "mostaza miel",
            "mostaza y miel",
        ],
        "signals": [
            "mostaza miel",
            "mostaza y miel",
            "honey mustard",
        ],
    },

    {
        "key": "mayonesa_ajo",
        "label": "Mayonesa ajo",
        "name_terms": [
            "mayonesa ajo",
            "mayonesa de ajo",
        ],
        "signals": [
            "mayonesa de ajo",
            "mayonesa ajo",
            "mayo ajo",
            "alioli",
            "aioli",
        ],
    },

    {
        "key": "mayonesa",
        "label": "Mayonesa",
        "name_terms": [
            "mayonesa",
        ],
        "signals": [
            "mayonesa",
            "mayo",
        ],
    },

]


GENERIC_STOPWORDS = {
    "cubo",
    "rondell",
    "pluma",
    "rallada",
    "rallado",
    "picada",
    "picado",
    "entero",
    "entera",
    "deshuesada",
    "tradicional",
    "cruda",
    "molida",
    "media",
    "luna",
}


def normalize(value: str) -> str:

    value = value or ""

    value = unicodedata.normalize(
        "NFKD",
        value.lower(),
    )

    value = "".join(
        c
        for c in value
        if not unicodedata.combining(c)
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _rule_for_product(
    product_name: str,
) -> dict:

    normalized_name = normalize(
        product_name
    )

    for rule in FAMILY_RULES:

        if any(
            normalize(term)
            in normalized_name

            for term
            in rule["name_terms"]
        ):
            return rule

    tokens = [
        token
        for token
        in re.findall(
            r"[a-zA-ZáéíóúñÁÉÍÓÚÑ]+",
            product_name,
        )
        if (
            len(token) >= 4
            and normalize(token)
            not in GENERIC_STOPWORDS
        )
    ]

    return {
        "key":
            "product_"
            + re.sub(
                r"[^a-z0-9]+",
                "_",
                normalized_name,
            ).strip("_"),

        "label":
            product_name,

        "name_terms":
            [product_name],

        "signals":
            tokens[:4]
            or [product_name],
    }


def build_product_families(
    products: list[dict],
) -> list[dict]:

    families: dict[str, dict] = {}

    for product in products:

        rule = _rule_for_product(
            product["name"]
        )

        if rule["key"] not in families:

            families[rule["key"]] = {
                "key":
                    rule["key"],

                "family":
                    rule["label"],

                "signals":
                    rule["signals"],

                "products":
                    [],
            }

        families[
            rule["key"]
        ]["products"].append(
            product["name"]
        )

    return list(
        families.values()
    )


def _snippet(
    text: str,
    signals: list[str],
) -> str | None:

    clean = re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()

    if not clean:
        return None

    pieces = re.split(
        r"(?<=[.!?])\s+|\s{2,}",
        clean,
    )

    for piece in pieces:

        normalized_piece = normalize(
            piece
        )

        if any(
            normalize(signal)
            in normalized_piece

            for signal
            in signals
        ):

            if len(piece) > 300:
                piece = piece[:297] + "..."

            return piece

    return None


def match_product_families(
    source_blocks: list[dict],
    products: list[dict],
) -> list[dict]:

    families = build_product_families(
        products
    )

    all_text = "\n".join(
        block.get("text", "")
        for block in source_blocks
    )

    normalized_all = normalize(
        all_text
    )

    matches = []

    for family in families:

        hits = []

        for signal in family["signals"]:

            if (
                normalize(signal)
                in normalized_all
            ):
                hits.append(signal)

        if not hits:
            continue

        evidence = []

        for block in source_blocks:

            snippet = _snippet(
                block.get("text", ""),
                hits,
            )

            if snippet:

                evidence.append(
                    {
                        "text":
                            snippet,

                        "url":
                            block.get("url"),

                        "title":
                            block.get("title"),
                    }
                )

            if len(evidence) >= 2:
                break

        score = min(
            95,
            55
            + max(
                0,
                len(set(hits)) - 1
            ) * 10
            + min(
                len(evidence),
                2,
            ) * 5,
        )

        matches.append(
            {
                "family":
                    family["family"],

                "products":
                    family["products"],

                "score":
                    score,

                "hits":
                    hits[:5],

                "evidence":
                    evidence,
            }
        )

    matches.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return matches[:8]


async def analyze_restaurant_opportunity(
    company_name: str,
    website: str | None,
    products: list[dict],
) -> dict:

    if not settings.tavily_api_key:

        raise RuntimeError(
            "Falta TAVILY_API_KEY"
        )

    query = (
        f'"{company_name}" '
        f'carta menú menu platos '
        f'restaurante Chile Instagram'
    )

    if website:
        query += f" {website}"

    headers = {
        "Authorization":
            f"Bearer "
            f"{settings.tavily_api_key}",

        "Content-Type":
            "application/json",
    }

    payload = {
        "query":
            query,

        "search_depth":
            "basic",

        "max_results":
            5,

        "include_answer":
            False,

        "include_raw_content":
            True,
    }

    async with httpx.AsyncClient(
        timeout=30
    ) as client:

        response = await client.post(
            TAVILY_SEARCH_URL,
            headers=headers,
            json=payload,
        )

        response.raise_for_status()

        results = response.json().get(
            "results",
            [],
        )

    blocks = []

    sources = []

    for result in results:

        title = (
            result.get("title")
            or ""
        )

        url = (
            result.get("url")
            or ""
        )

        content = (
            result.get("content")
            or ""
        )

        raw_content = (
            result.get("raw_content")
            or ""
        )

        # Evitar cargar páginas gigantes
        raw_content = raw_content[:12000]

        combined = "\n".join(
            [
                title,
                content,
                raw_content,
            ]
        )

        blocks.append(
            {
                "title": title,
                "url": url,
                "text": combined,
            }
        )

        if url:

            sources.append(
                {
                    "title":
                        title or url,

                    "url":
                        url,
                }
            )

    matches = match_product_families(
        blocks,
        products,
    )

    if matches:

        top_score = matches[0][
            "score"
        ]

        score = min(
            100,
            int(
                50
                + min(
                    len(matches),
                    4,
                ) * 8
                + max(
                    0,
                    top_score - 55,
                )
                * 0.6
                + (
                    4
                    if website
                    else 0
                )
            ),
        )

    else:

        score = (
            19
            if website
            else 15
        )

    if score >= 80:
        level = "Alta"

    elif score >= 60:
        level = "Media"

    else:
        level = "Baja"

    evidence_text = ""

    evidence_url = ""

    if matches:

        first_evidence = (
            matches[0]
            .get("evidence")
            or []
        )

        if first_evidence:

            evidence_text = (
                first_evidence[0]
                .get("text")
                or ""
            )

            evidence_url = (
                first_evidence[0]
                .get("url")
                or ""
            )

    suggested_products = []

    for match in matches:

        suggested_products.extend(
            match["products"]
        )

    suggested_products = list(
        dict.fromkeys(
            suggested_products
        )
    )

    return {
        "score":
            score,

        "level":
            level,

        "matches":
            matches,

        "sources":
            sources[:5],

        "suggested_products_text":
            ", ".join(
                suggested_products
            ),

        "evidence_text":
            evidence_text,

        "evidence_url":
            evidence_url,
    }
