# Speclink

[![Coverage](https://codecov.io/gh/lacatu5/speclink/branch/main/graph/badge.svg)](https://codecov.io/gh/lacatu5/speclink)

**Speclink** mantiene la documentación y el código sincronizados mediante LLMs. Mapea automáticamente las secciones de documentación con el código relevante y las reescribe cuando detecta cambios.

## Arquitectura

```
speclink/
├── core/                    # Núcleo del pipeline
│   ├── models.py            # Modelos Pydantic (secciones, mapeos, config)
│   ├── config.py            # Configuración del proyecto
│   ├── paths.py             # Resolución de rutas
│   └── store.py             # Persistencia del mapa de trazabilidad
├── preprocessing/           # Parseo de entrada
│   ├── markdown.py          # Extracción de secciones desde Markdown
│   ├── code_extraction.py   # Extracción de símbolos con tree-sitter (Python, TS)
│   ├── diff.py              # Detección de cambios entre commits
│   └── incremental.py       # Actualización incremental del mapa
├── retrieval/               # Recuperación y clasificación
│   ├── classifier.py        # Clasificación LLM (sección, archivo) → TRUE/FALSE
│   ├── reranker.py          # Reranking de candidatos
│   └── batch.py             # Procesamiento por lotes
├── rewrite/                 # Reescritura de documentación
│   ├── analyzer.py          # Análisis de impacto de cambios
│   └── rewriter.py          # Reescritura con LLM
├── _prompts/                # Plantillas de prompt para LiteLLM
├── _templates/              # Plantillas de GitHub Actions
├── cli.py                   # Interfaz CLI (Typer)
└── wizard.py                # Asistente interactivo
```

### Pipeline

```
scope → analyze → sync
  │        │        │
  │        │        └── Reescribe secciones afectadas usando LLM
  │        └── Mapea secciones de docs a código con clasificador + reranker
  └── Selecciona archivos de documentación a monitorizar
```

## Características principales

- **Mapeo automático**: Analiza el repositorio para vincular secciones de documentación con los símbolos de código que describen.
- **Sincronización incremental**: Solo actualiza las secciones de documentación afectadas por cambios recientes en el código.
- **Integración con GitHub Actions**: Automatiza la sincronización en el pipeline CI/CD.
- **Basado en IA**: Utiliza LLMs (OpenAI, Anthropic, etc.) y rerankers para recuperación de contexto de alta precisión.

## Instalación

```bash
pip install speclink
```

## Inicio rápido

### 1. Inicializar Speclink
Ejecutar el asistente para seleccionar los archivos de documentación a monitorizar.
```bash
speclink scope
```
Esto crea:
- Un directorio de configuración `.speclink/`.
- Un workflow `.github/workflows/speclink-sync.yml` para la sincronización automática.

### 2. Configurar entorno
Crear un archivo `.env` o definir variables de entorno. Speclink utiliza **LiteLLM**, compatible con más de 100 proveedores (OpenAI, Anthropic, Mistral, Ollama, etc.).

```env
LLM_API_KEY=tu_clave
LLM_MODEL=openai/gpt-4o  # o anthropic/claude-3-5-sonnet, mistral/mistral-large, etc.
RERANK_API_KEY=tu_clave
RERANK_MODEL=cohere/rerank-v3.5
```

Para ver las instrucciones completas de configuración:
```bash
speclink guide
```

Consultar [proveedores soportados por LiteLLM](https://docs.litellm.ai/docs/providers) para la lista completa de identificadores de modelo.

### 3. Análisis inicial y commit
Generar el mapeo inicial y subirlo al repositorio para habilitar la automatización.
```bash
speclink analyze
git add .speclink/ .github/
git commit -m "chore: inicializar speclink"
git push
```

### 4. Sincronización continua (automatización)
Una vez configurado, la GitHub Action se ejecuta automáticamente en cada Pull Request:
1. **Detecta** cambios en el código.
2. **Re-analiza** el repositorio para actualizar el mapa de trazabilidad (incremental).
3. **Sincroniza** las secciones de documentación afectadas.
4. **Commitea** los cambios directamente en la rama.

## Funcionamiento
1. **Scope**: Se definen qué archivos `.md` son la fuente de verdad.
2. **Analyze**: Speclink parsea el código con `tree-sitter` y utiliza un reranker para identificar qué archivos/funciones están relacionados con cada sección de documentación.
3. **Sync**: Cuando el código cambia, Speclink identifica las secciones afectadas, proporciona el nuevo contexto al LLM y reescribe la documentación.

## Desarrollo

Requiere Python 3.12+.

```bash
git clone https://github.com/lacatu5/speclink.git
cd speclink
uv sync --group dev
```

### Tests

```bash
uv run pytest
```

## Evaluación

Los resultados de evaluación con 12 modelos LLM, 5 rerankers y análisis de ablation están en [speclink-benchmark](https://github.com/lacatu5/speclink-benchmark).

## Licencia
MIT
