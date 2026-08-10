# Ramal CRM

CRM comercial mobile-first para Ramal: prospectos, catálogo, cotizaciones, pedidos y prospección web.

## Stack

- Python 3.12
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Jinja2 (interfaz web responsive)
- Google Places API (prospección geográfica)
- Tavily API (enriquecimiento web, preparado)

## Funciones incluidas en este MVP

- Dashboard móvil.
- Prospectos con estado comercial.
- Catálogo de 33 productos Ramal importado desde la lista de precios entregada.
- Precios históricos en cotizaciones.
- Cotización única `COT-AAAA-00000`.
- Vigencia automática de 5 días corridos.
- Neto / IVA / total a partir del precio final IVA incluido.
- Vista imprimible para guardar cotización como PDF.
- Búsqueda de prospectos con Google Places.
- Detección de duplicados por Google Place ID.
- Servicio preparado para enriquecimiento web con Tavily.
- Tablas listas para contactos, actividades, pedidos y fuentes web.

## Ejecutar localmente

1. Crear PostgreSQL y una base `ramal_crm`.
2. Copiar `.env.example` a `.env` y ajustar `DATABASE_URL`.
3. Crear entorno e instalar:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Migrar y cargar catálogo:

```bash
alembic upgrade head
python -m app.seed
```

5. Ejecutar:

```bash
uvicorn app.main:app --reload
```

Abrir `http://localhost:8000`. Documentación API en `/docs`.

## Railway + GitHub

1. Subir este repositorio a GitHub.
2. En Railway, crear un proyecto desde el repositorio.
3. Agregar un servicio PostgreSQL al mismo proyecto.
4. En el servicio web, definir `DATABASE_URL` apuntando al PostgreSQL de Railway. Si Railway entrega una URL `postgresql://...`, psycopg/SQLAlchemy la acepta; si se necesitara, puede usarse `postgresql+psycopg://...`.
5. Agregar opcionalmente:
   - `GOOGLE_PLACES_API_KEY`
   - `TAVILY_API_KEY`
   - `SECRET_KEY`
6. Railway construirá el `Dockerfile`. Al iniciar, el contenedor ejecuta migraciones, carga el catálogo de forma idempotente y levanta Uvicorn usando `$PORT`.
7. Generar un dominio público en Railway.

## Búsqueda web

### Google Places

La pantalla `/web-search` usa Places API (New), método Text Search. Ejemplos:

- `restaurantes Vitacura`
- `hoteles Providencia Santiago`
- `casinos de empresas Quilicura`

Guarda `google_place_id`, nombre, dirección, coordenadas, teléfono y web cuando Google los entrega.

### Tavily

El servicio `app/services/tavily_enrichment.py` está preparado para buscar correo/Instagram y guardar fuentes. La siguiente iteración debe agregar el botón “Enriquecer” a cada resultado y persistir las fuentes encontradas.

## Próximas iteraciones recomendadas

1. Contactos y actividades desde la ficha.
2. Cotizaciones con múltiples líneas en la UI.
3. PDF con logo Ramal y envío por email/WhatsApp.
4. Pedidos y conversión cotización → pedido.
5. Mapa y sugerencia de visitas por cercanía / rubro.
6. Login y roles por vendedor.
7. Seguimientos automáticos y avisos de vencimiento.
