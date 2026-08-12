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
            "mayonnaise",
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

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\\s+",
        " ",
        value,
    ).strip()


def signal_found(
    signal: str,
    text: str,
) -> bool:

    signal_normalized = normalize(
        signal
    )

    text_normalized = normalize(
        text
    )

    if not signal_normalized:
        return False

    # Frases y palabras deben coincidir completas.
    # Evita, por ejemplo:
    # mayo -> mayor
    # papa -> papagayo
    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(signal_normalized)
        + r"(?![a-z0-9])"
    )

    return (
        re.search(
            pattern,
            text_normalized,
        )
        is not None
    )




def clean_domain(
    url: str | None,
) -> str:

    if not url:
        return ""

    value = (
        url.lower()
        .replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
    )

    if value.startswith("www."):
        value = value[4:]

    return value


def source_quality(
    url: str | None,
    title: str | None,
    official_website: str | None,
) -> dict:

    url_n = normalize(url or "")
    title_n = normalize(title or "")

    domain = clean_domain(url)
    official_domain = clean_domain(
        official_website
    )

    quality = 0.40
    label = "Fuente externa"


    # WEB OFICIAL
    if (
        official_domain
        and domain
        and (
            domain == official_domain
            or domain.endswith(
                "." + official_domain
            )
        )
    ):
        quality = 0.90
        label = "Sitio oficial"


    # CARTA / MENU
    menu_terms = [
        "menu",
        "carta",
        "food",
        "comida",
        "platos",
    ]

    if any(
        signal_found(term, url_n)
        or signal_found(term, title_n)
        for term in menu_terms
    ):

        quality = max(
            quality,
            0.95,
        )

        if label == "Sitio oficial":
            label = "Carta oficial"
        else:
            label = "Carta / menú"


    # PDF
    if ".pdf" in (url or "").lower():

        quality = max(
            quality,
            0.95,
        )

        label = "Carta PDF"


    # DELIVERY
    delivery_domains = [
        "pedidosya",
        "ubereats",
        "uber.com",
        "rappi",
        "justo",
        "mercat",
    ]

    if any(
        item in domain
        for item in delivery_domains
    ):

        quality = max(
            quality,
            0.80,
        )

        label = "Delivery"


    # REDES SOCIALES
    social_domains = [
        "instagram.com",
        "facebook.com",
        "tiktok.com",
    ]

    if any(
        item in domain
        for item in social_domains
    ):

        quality = max(
            quality,
            0.65,
        )

        label = "Red social"


    return {
        "quality": quality,
        "label": label,
        "domain": domain,
    }



def commercial_pitch(
    family: str,
) -> str:

    family_n = normalize(
        family
    )


    if any(
        item in family_n
        for item in [
            "pulled pork",
            "costilla",
            "pollo",
        ]
    ):

        return (
            "Producto estandarizado que puede "
            "reducir preparación, mano de obra "
            "y merma."
        )


    if any(
        item in family_n
        for item in [
            "tomate",
            "palta",
            "cebolla",
            "zanahoria",
            "repollo",
            "papa",
            "aji",
            "apio",
            "betarraga",
        ]
    ):

        return (
            "Ingrediente preprocesado que puede "
            "reducir mise en place, merma y "
            "variación de porciones."
        )


    if any(
        item in family_n
        for item in [
            "bbq",
            "mayonesa",
            "mostaza",
            "chimichurri",
        ]
    ):

        return (
            "Salsa estandarizada que facilita "
            "mantener sabor, rendimiento y costo "
            "por porción consistentes."
        )


    if "encurt" in family_n:

        return (
            "Producto listo para usar que reduce "
            "elaboración interna y facilita la "
            "estandarización."
        )


    return (
        "Producto Ramal compatible con una "
        "preparación identificada en la oferta "
        "del negocio."
    )


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
            signal_found(
                signal,
                piece,
            )
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
    official_website: str | None = None,
) -> list[dict]:

    families = build_product_families(
        products
    )

    matches = []


    for family in families:

        evidences = []

        unique_hits = set()


        for block in source_blocks:

            block_text = (
                block.get("text")
                or ""
            )

            block_hits = [
                signal
                for signal
                in family["signals"]

                if signal_found(
                    signal,
                    block_text,
                )
            ]


            if not block_hits:
                continue


            snippet = _snippet(
                block_text,
                block_hits,
            )


            # Si no podemos mostrar evidencia,
            # no usamos esta fuente para recomendar.
            if not snippet:
                continue


            quality_info = source_quality(
                block.get("url"),
                block.get("title"),
                official_website,
            )


            unique_hits.update(
                block_hits
            )


            evidences.append(
                {
                    "text":
                        snippet,

                    "url":
                        block.get("url"),

                    "title":
                        block.get("title"),

                    "source_type":
                        quality_info[
                            "label"
                        ],

                    "quality":
                        quality_info[
                            "quality"
                        ],
                }
            )


        if not evidences:
            continue


        evidences.sort(
            key=lambda e:
                e["quality"],
            reverse=True,
        )


        best_quality = evidences[0][
            "quality"
        ]


        # Una única mención débil ya no puede
        # convertirse en una oportunidad "alta".
        score = int(
            30
            + best_quality * 30
            + min(
                len(evidences) - 1,
                2,
            ) * 8
            + min(
                len(unique_hits) - 1,
                2,
            ) * 6
        )


        score = min(
            score,
            92,
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
                    sorted(
                        unique_hits
                    )[:5],

                "evidence":
                    evidences[:3],

                "best_source_type":
                    evidences[0][
                        "source_type"
                    ],

                "best_quality":
                    best_quality,

                "pitch":
                    commercial_pitch(
                        family["family"]
                    ),
            }
        )


    matches.sort(
        key=lambda x:
            x["score"],
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
        official_website=website,
    )

    if matches:

        best_match = matches[0]

        score = (
            best_match["score"]
            + min(
                len(matches) - 1,
                3,
            ) * 7
        )

        # Tener varias familias compatibles
        # aumenta la relevancia comercial.
        score = min(
            95,
            score,
        )

    else:

        score = 10


    if score >= 80:
        level = "Alta"

    elif score >= 60:
        level = "Media"

    elif score >= 40:
        level = "Baja"

    else:
        level = "Sin evidencia"


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
