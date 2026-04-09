# gtm-measurement-mvp

MVP base para convertir un caso de plan de medición (imágenes + metadata) en artefactos iniciales para GTM.

## Requisitos
- Python 3.11+

## Ejecutar caso localmente
Desde la raíz del proyecto (`gtm-measurement-mvp/`):

```bash
python -m src.cli.run_case --case-id case_001 --repo-root .
```

## Output esperado (Fase 1)
Se crea `outputs/case_001/` con:
- `measurement_case.json`
- `tag_template.js` (stub)
- `trigger_selector.txt` (stub)
- `report.md` (estado y alertas)

> Nota: esta fase deja esqueleto y stubs; no incluye scraping complejo ni generación GTM final.
