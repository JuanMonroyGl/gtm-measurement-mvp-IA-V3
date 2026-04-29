"""DOM snapshot utilities with strict rendered-vs-fallback provenance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from web_scraping.fetch_page import fetch_html

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, sync_playwright
except ImportError:  # optional dependency at runtime, but explicitly reported.
    PlaywrightError = Exception  # type: ignore[assignment]
    Page = Any  # type: ignore[misc,assignment]
    sync_playwright = None  # type: ignore[assignment]


NODE_ID_ATTR = "data-gtm-mvp-node-id"
NATIVE_CLICKABLE_SELECTOR = 'a, button, [role="button"], summary, input, [onclick], [tabindex]'
CLICKABLE_LIKE_CLASS_SELECTOR = ", ".join(
    [
        ".tituloAcordeonInfo",
        ".titulo-acordeon-info",
        ".acordeon-header",
        ".acordeon-title",
        ".accordion-header",
        ".accordion-title",
        ".accordion-button",
        ".bc-accordion-header",
        ".filter__option",
        ".filter__option-desktop",
        ".tab-title",
        ".tab-label",
    ]
)
CLICKABLE_SELECTOR = f"{NATIVE_CLICKABLE_SELECTOR}, {CLICKABLE_LIKE_CLASS_SELECTOR}"
STATE_SEQUENCE = [
    "initial_render",
    "after_scroll",
    "nav_open",
    "tabs_expanded",
    "accordion_open",
    "carousel_ready",
]
OPTIONAL_STATE_DEFINITIONS = [
    {
        "name": "nav_open",
        "selector": 'button[aria-controls], button[aria-expanded], [data-bs-toggle="collapse"], .menu-toggle, .navbar-toggler',
        "limit": 1,
        "action": "click",
    },
    {
        "name": "tabs_expanded",
        "selector": '[role="tab"], .tab, .tabs button, .tab-title, .tab-label',
        "limit": 3,
        "action": "click",
    },
    {
        "name": "accordion_open",
        "selector": (
            'summary, [aria-expanded="false"], .accordion button, .accordion-header, '
            '.accordion-title, .accordion-button, .bc-accordion-header, .tituloAcordeonInfo, '
            '.titulo-acordeon-info, .acordeon-header, .acordeon-title'
        ),
        "limit": 5,
        "action": "click",
    },
    {
        "name": "carousel_ready",
        "selector": '.swiper-button-next, .carousel-control-next, [aria-label*="next" i], [aria-label*="siguiente" i]',
        "limit": 2,
        "action": "click",
    },
]


@dataclass
class DomSnapshot:
    target_url: str
    source_url: str
    final_url: str | None
    raw_html: str | None
    rendered_dom_html: str | None
    render_engine: str
    warning: str | None = None
    fetch_warning: str | None = None
    states_captured: list[str] | None = None
    state_html: dict[str, str] | None = None
    clickable_inventory: list[dict[str, Any]] | None = None
    state_metadata: list[dict[str, Any]] | None = None
    dom_dir: str | None = None
    manifest_path: str | None = None
    html_artifacts: dict[str, dict[str, Any]] | None = None


def _captured_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _html_file_name(state: str, source: str) -> str:
    if source == "raw_html":
        return "raw_html.html"
    return f"rendered_{state}.html"


def _relative_dom_path(case_id: str, file_name: str) -> str:
    return (Path("outputs") / case_id / "dom" / file_name).as_posix()


def _metadata_by_state(state_metadata: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {str(item.get("state")): item for item in state_metadata or [] if item.get("state")}


def _manifest_warnings(snapshot: DomSnapshot, raw_fetch_warning: str | None = None) -> list[str]:
    warnings = []
    if snapshot.warning:
        warnings.append(snapshot.warning)
    if snapshot.fetch_warning:
        warnings.append(snapshot.fetch_warning)
    if raw_fetch_warning and raw_fetch_warning not in warnings:
        warnings.append(raw_fetch_warning)
    for state in snapshot.state_metadata or []:
        if state.get("warning"):
            warnings.append(str(state["warning"]))
    return list(dict.fromkeys(warnings))


def _persist_dom_artifacts(
    *,
    snapshot: DomSnapshot,
    output_dir: Path | None,
    case_id: str | None,
    raw_fetch_warning: str | None = None,
) -> DomSnapshot:
    if output_dir is None or not case_id:
        return snapshot

    dom_dir = output_dir / "dom"
    dom_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, dict[str, Any]] = {}
    html_lengths: dict[str, int] = {}

    if snapshot.raw_html is not None:
        file_name = _html_file_name("raw_html", "raw_html")
        path = dom_dir / file_name
        path.write_text(snapshot.raw_html, encoding="utf-8")
        html_lengths["raw_html"] = len(snapshot.raw_html)
        artifacts["raw_html"] = {
            "state": "raw_html",
            "file": file_name,
            "path": str(path),
            "relative_path": _relative_dom_path(case_id, file_name),
            "source": "raw_html",
            "attempted": True,
            "verified": True,
            "warnings": [] if not raw_fetch_warning else [raw_fetch_warning],
            "html_length": len(snapshot.raw_html),
        }

    metadata_by_state = _metadata_by_state(snapshot.state_metadata)
    states: list[dict[str, Any]] = []
    for state in snapshot.states_captured or []:
        metadata = metadata_by_state.get(state, {})
        source = str(metadata.get("source") or "observed_rendered_dom")
        html = snapshot.raw_html if state == "raw_html_fallback" else (snapshot.state_html or {}).get(state)
        if html is None:
            continue

        file_name = "raw_html.html" if state == "raw_html_fallback" else _html_file_name(state, source)
        path = dom_dir / file_name
        if state != "raw_html_fallback":
            path.write_text(html, encoding="utf-8")

        html_lengths[state] = len(html)
        state_entry = {
            "state": state,
            "file": file_name,
            "path": str(path),
            "relative_path": _relative_dom_path(case_id, file_name),
            "source": source,
            "attempted": bool(metadata.get("attempted", True)),
            "verified": bool(metadata.get("verified", state == "initial_render")),
            "warnings": [metadata["warning"]] if metadata.get("warning") else [],
            "html_length": len(html),
        }
        states.append(state_entry)
        artifacts[state] = state_entry

    notes: list[str] = []
    captured = set(snapshot.states_captured or [])
    for metadata in snapshot.state_metadata or []:
        state = str(metadata.get("state") or "")
        if not state or state in captured:
            continue
        if metadata.get("attempted"):
            notes.append(f"Estado {state} intentado pero no verificado; no se guardo HTML renderizado.")
        else:
            notes.append(f"Estado {state} no aplico; no se guardo HTML renderizado.")
    if not snapshot.raw_html:
        notes.append("No se guardo raw_html.html porque no hubo HTML crudo disponible en el flujo.")

    warnings = _manifest_warnings(snapshot, raw_fetch_warning=raw_fetch_warning)
    if snapshot.render_engine == "raw_html_fallback":
        manifest_source = "raw_html_fallback"
    elif snapshot.render_engine == "none":
        manifest_source = "none"
    else:
        manifest_source = "observed_rendered_dom"

    manifest = {
        "case_id": case_id,
        "target_url": snapshot.target_url,
        "final_url": snapshot.final_url,
        "render_engine": snapshot.render_engine,
        "states_captured": snapshot.states_captured or [],
        "states": states,
        "state_metadata": snapshot.state_metadata or [],
        "raw_html": artifacts.get("raw_html"),
        "html_artifacts": artifacts,
        "source": manifest_source,
        "attempted": bool(snapshot.target_url),
        "verified": any(bool(item.get("verified")) for item in states),
        "warnings": warnings,
        "html_length": html_lengths,
        "captured_at": _captured_at(),
        "fallback_used": snapshot.render_engine == "raw_html_fallback",
        "notes": notes,
    }
    manifest_path = dom_dir / "dom_snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    snapshot.dom_dir = str(dom_dir)
    snapshot.manifest_path = str(manifest_path)
    snapshot.html_artifacts = artifacts
    return snapshot


def _state_change_observed(
    before_signature: dict[str, Any],
    after_signature: dict[str, Any],
    before_html: str,
    after_html: str,
) -> bool:
    if before_html != after_html:
        return True
    keys = (
        "html_length",
        "clickable_count",
        "visible_clickable_count",
        "aria_expanded_true",
        "open_details",
        "scroll_height",
    )
    return any(before_signature.get(key) != after_signature.get(key) for key in keys)


def _annotate_clickable_nodes(page: Page) -> None:
    page.evaluate(
        f"""
        () => {{
          Array.from(document.querySelectorAll('{CLICKABLE_SELECTOR}')).forEach((el, index) => {{
            if (!el.hasAttribute('{NODE_ID_ATTR}')) {{
              el.setAttribute('{NODE_ID_ATTR}', `gtm-mvp-${{index + 1}}`);
            }}
          }});
        }}
        """
    )


def _capture_page_signature(page: Page) -> dict[str, Any]:
    return page.evaluate(
        f"""
        () => {{
          const nodes = Array.from(document.querySelectorAll('{CLICKABLE_SELECTOR}'));
          function visible(el) {{
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return !!(r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none');
          }}
          return {{
            html_length: document.documentElement.outerHTML.length,
            clickable_count: nodes.length,
            visible_clickable_count: nodes.filter(visible).length,
            aria_expanded_true: document.querySelectorAll('[aria-expanded="true"]').length,
            open_details: document.querySelectorAll('details[open]').length,
            scroll_height: document.body ? document.body.scrollHeight : 0,
          }};
        }}
        """
    )


def _extract_clickables_with_playwright(page: Page, state: str, source: str) -> list[dict[str, Any]]:
    _annotate_clickable_nodes(page)
    script = f"""
    (payload) => {{
      const stateName = payload.stateName;
      const stateSource = payload.stateSource;
      const nodes = Array.from(document.querySelectorAll('{CLICKABLE_SELECTOR}'));
      function visible(el) {{
        const r = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return !!(r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none');
      }}
      function clickable(el) {{
        if (el.tagName === 'A' && el.getAttribute('href')) return true;
        if (el.tagName === 'BUTTON') return true;
        if (el.tagName === 'SUMMARY') return true;
        if (el.getAttribute('role') === 'button') return true;
        if (el.hasAttribute('onclick')) return true;
        if (el.tagName === 'INPUT') {{
          const t = (el.getAttribute('type') || '').toLowerCase();
          return ['button', 'submit', 'radio', 'checkbox', 'image'].includes(t);
        }}
        const classText = Array.from(el.classList || []).join(' ');
        if (/(^|\\s)(tituloAcordeonInfo|titulo-acordeon-info|acordeon-header|acordeon-title|accordion-header|accordion-title|accordion-button|bc-accordion-header|filter__option|filter__option-desktop|tab-title|tab-label)(\\s|$)/i.test(classText)) return true;
        const ti = el.getAttribute('tabindex');
        return ti !== null && ti !== '-1';
      }}
      function ancestors(el) {{
        const out = [];
        let c = el.parentElement;
        let i = 0;
        while (c && i < 5) {{
          out.push({{
            tag: (c.tagName || '').toLowerCase(),
            id: c.id || null,
            classes: Array.from(c.classList || []).slice(0, 4),
          }});
          c = c.parentElement;
          i += 1;
        }}
        return out;
      }}
      function selectorCandidates(el) {{
        const candidates = [];
        const tag = (el.tagName || '').toLowerCase();
        if (el.id) candidates.push(`#${{CSS.escape(el.id)}}`);
        for (const attrName of el.getAttributeNames()) {{
          if (attrName === '{NODE_ID_ATTR}') continue;
          if (attrName.startsWith('data-')) {{
            const value = el.getAttribute(attrName);
            if (value) candidates.push(`${{tag}}[${{attrName}}="${{CSS.escape(value)}}"]`);
          }}
        }}
        for (const attrName of ['aria-label', 'aria-controls']) {{
          const value = el.getAttribute(attrName);
          if (value) candidates.push(`${{tag}}[${{attrName}}="${{CSS.escape(value)}}"]`);
        }}
        const href = el.getAttribute('href');
        if (href && href !== '#') candidates.push(`${{tag}}[href="${{CSS.escape(href)}}"]`);
        const classes = Array.from(el.classList || []).filter((value) => value && value.length > 2).slice(0, 2);
        if (classes.length) candidates.push(`${{tag}}.${{classes.map((value) => CSS.escape(value)).join('.')}}`);
        candidates.push(tag);
        return Array.from(new Set(candidates)).sort();
      }}
      function contextText(el) {{
        const parts = [];
        let current = el.parentElement;
        let depth = 0;
        while (current && depth < 3) {{
          const text = (current.innerText || current.textContent || '').replace(/\\s+/g, ' ').trim();
          if (text) parts.push(text.slice(0, 160));
          current = current.parentElement;
          depth += 1;
        }}
        return parts.join(' | ').slice(0, 320);
      }}
      return nodes.map((el) => {{
        const r = el.getBoundingClientRect();
        return {{
          node_id: el.getAttribute('{NODE_ID_ATTR}'),
          tag: (el.tagName || '').toLowerCase(),
          text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 200),
          context_text: contextText(el),
          aria_label: el.getAttribute('aria-label'),
          title: el.getAttribute('title'),
          href: el.getAttribute('href'),
          id: el.id || null,
          class_list: Array.from(el.classList || []),
          ancestors: ancestors(el),
          outer_html_excerpt: (el.outerHTML || '').replace(/\\s+/g, ' ').slice(0, 500),
          bounding_box: {{ x: r.x, y: r.y, width: r.width, height: r.height }},
          state: stateName,
          source: stateSource,
          is_visible: visible(el),
          is_clickable: clickable(el),
          selector_candidates: selectorCandidates(el),
        }};
      }});
    }}
    """
    return page.evaluate(script, {"stateName": state, "stateSource": source})


def _prepare_page(browser: Any, target_url: str) -> Page:
    page = browser.new_page(viewport={"width": 1440, "height": 2200})
    page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except PlaywrightError:
        pass
    _annotate_clickable_nodes(page)
    return page


def _capture_rendered_state(page: Page, state: str) -> tuple[str, list[dict[str, Any]]]:
    _annotate_clickable_nodes(page)
    html = page.content()
    inventory = _extract_clickables_with_playwright(page, state, "observed_rendered_dom")
    return html, inventory


def _attempt_scroll_state(page: Page) -> dict[str, Any]:
    before_html = page.content()
    before_signature = _capture_page_signature(page)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    _annotate_clickable_nodes(page)
    after_html = page.content()
    after_signature = _capture_page_signature(page)
    return {
        "state": "after_scroll",
        "source": "observed_rendered_dom",
        "attempted": True,
        "action": "scroll_bottom_then_top",
        "verified": _state_change_observed(before_signature, after_signature, before_html, after_html),
        "before_signature": before_signature,
        "after_signature": after_signature,
        "change_signal": {
            "dom_changed": before_html != after_html,
            "signature_changed": before_signature != after_signature,
        },
    }


def _attempt_optional_state(page: Page, definition: dict[str, Any]) -> dict[str, Any]:
    before_html = page.content()
    before_signature = _capture_page_signature(page)
    locator = page.locator(definition["selector"])
    count = locator.count()

    metadata = {
        "state": definition["name"],
        "source": "observed_rendered_dom",
        "attempted": False,
        "action": definition["action"],
        "selector": definition["selector"],
        "candidate_count": count,
        "target_text": None,
        "verified": False,
        "before_signature": before_signature,
        "after_signature": before_signature,
        "change_signal": {
            "dom_changed": False,
            "signature_changed": False,
        },
    }

    if count == 0:
        return metadata

    limit = min(int(definition.get("limit") or 1), count)
    for idx in range(limit):
        try:
            target = locator.nth(idx)
            text = (target.inner_text(timeout=1000) or "").strip()
            metadata["target_text"] = text[:160] if text else None
            metadata["attempted"] = True
            target.scroll_into_view_if_needed(timeout=1000)
            target.click(timeout=2000, force=True)
            page.wait_for_timeout(500)
        except PlaywrightError:
            continue

        _annotate_clickable_nodes(page)
        after_html = page.content()
        after_signature = _capture_page_signature(page)
        changed = _state_change_observed(before_signature, after_signature, before_html, after_html)
        metadata["after_signature"] = after_signature
        metadata["change_signal"] = {
            "dom_changed": before_html != after_html,
            "signature_changed": before_signature != after_signature,
        }
        metadata["verified"] = changed
        if changed:
            return metadata

    return metadata


def _capture_playwright_states(
    target_url: str,
) -> tuple[dict[str, str] | None, list[dict[str, Any]], list[dict[str, Any]], str | None, str | None]:
    if sync_playwright is None:
        return None, [], [], None, "Playwright no disponible; el pipeline degradará a raw_html_fallback."

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            state_html: dict[str, str] = {}
            inventory: list[dict[str, Any]] = []
            state_metadata: list[dict[str, Any]] = []

            base_page = _prepare_page(browser, target_url)
            final_url = base_page.url
            initial_html, initial_inventory = _capture_rendered_state(base_page, "initial_render")
            state_html["initial_render"] = initial_html
            inventory.extend(initial_inventory)
            state_metadata.append(
                {
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "attempted": True,
                    "action": "page_load",
                    "verified": True,
                    "before_signature": None,
                    "after_signature": _capture_page_signature(base_page),
                    "change_signal": {"dom_changed": True, "signature_changed": True},
                }
            )

            scroll_metadata = _attempt_scroll_state(base_page)
            state_metadata.append(scroll_metadata)
            if scroll_metadata["verified"]:
                html, items = _capture_rendered_state(base_page, "after_scroll")
                state_html["after_scroll"] = html
                inventory.extend(items)
            base_page.close()

            for definition in OPTIONAL_STATE_DEFINITIONS:
                page = _prepare_page(browser, target_url)
                metadata = _attempt_optional_state(page, definition)
                state_metadata.append(metadata)
                if metadata["verified"]:
                    html, items = _capture_rendered_state(page, definition["name"])
                    state_html[definition["name"]] = html
                    inventory.extend(items)
                page.close()

            browser.close()
            return state_html, inventory, state_metadata, final_url, None
    except Exception as exc:  # pragma: no cover
        return None, [], [], None, f"Falló render con Playwright; el pipeline degradará a raw_html_fallback. Detalle: {exc}"


def _extract_clickables_from_html(html: str, state: str, source: str) -> tuple[str, list[dict[str, Any]]]:
    soup = BeautifulSoup(html, "lxml")
    inventory: list[dict[str, Any]] = []

    for index, element in enumerate(soup.select(CLICKABLE_SELECTOR), start=1):
        element[NODE_ID_ATTR] = f"gtm-mvp-fallback-{index}"
        classes = element.get("class") or []
        selector_candidates: list[str] = []
        if element.get("id"):
            selector_candidates.append(f"#{element.get('id')}")
        for attr_name in element.attrs:
            if str(attr_name) == NODE_ID_ATTR:
                continue
            if str(attr_name).startswith("data-"):
                value = element.get(attr_name)
                if isinstance(value, str) and value:
                    selector_candidates.append(f'{element.name}[{attr_name}="{value}"]')
        for attr_name in ("aria-label", "aria-controls"):
            value = element.get(attr_name)
            if isinstance(value, str) and value:
                selector_candidates.append(f'{element.name}[{attr_name}="{value}"]')
        if element.get("href"):
            selector_candidates.append(f'{element.name}[href="{element.get("href")}"]')
        if classes:
            selector_candidates.append(f"{element.name}." + ".".join(classes[:2]))
        selector_candidates.append(element.name)

        parent = element.parent if getattr(element, "parent", None) else None
        context_text = ""
        if parent and getattr(parent, "get_text", None):
            context_text = " ".join(parent.get_text(" ", strip=True).split())[:320]

        inventory.append(
            {
                "node_id": element.get(NODE_ID_ATTR),
                "tag": element.name,
                "text": " ".join(element.get_text(" ", strip=True).split())[:200],
                "context_text": context_text,
                "aria_label": element.get("aria-label"),
                "title": element.get("title"),
                "href": element.get("href"),
                "id": element.get("id"),
                "class_list": classes,
                "ancestors": [],
                "outer_html_excerpt": str(element)[:500],
                "bounding_box": None,
                "state": state,
                "source": source,
                "is_visible": False,
                "is_clickable": True,
                "selector_candidates": sorted(set(selector_candidates)),
            }
        )

    return str(soup), inventory


def build_dom_snapshot(
    target_url: str,
    output_dir: Path | str | None = None,
    case_id: str | None = None,
) -> DomSnapshot:
    """Return normalized snapshot, provenance, and verified state evidence."""
    output_path = Path(output_dir) if output_dir is not None else None
    if not target_url:
        snapshot = DomSnapshot(
            target_url=target_url,
            source_url=target_url,
            final_url=None,
            raw_html=None,
            rendered_dom_html=None,
            render_engine="none",
            warning="No hay target_url para adquirir DOM.",
            fetch_warning="No hay target_url para scraping.",
            states_captured=[],
            state_html={},
            clickable_inventory=[],
            state_metadata=[],
        )
        return _persist_dom_artifacts(snapshot=snapshot, output_dir=output_path, case_id=case_id)

    state_html, inventory, state_metadata, final_url, render_warning = _capture_playwright_states(target_url)
    if state_html:
        raw_fetch_result = fetch_html(target_url)
        raw_fetch_warning = raw_fetch_result.warning if not raw_fetch_result.html else None
        states_captured = [state for state in STATE_SEQUENCE if state in state_html]
        snapshot = DomSnapshot(
            target_url=target_url,
            source_url=final_url or raw_fetch_result.final_url or target_url,
            final_url=final_url or raw_fetch_result.final_url,
            raw_html=raw_fetch_result.html,
            rendered_dom_html=state_html.get("initial_render") or next(iter(state_html.values())),
            render_engine="playwright_multi_state",
            warning=render_warning,
            fetch_warning=None,
            states_captured=states_captured,
            state_html=state_html,
            clickable_inventory=inventory,
            state_metadata=state_metadata,
        )
        return _persist_dom_artifacts(
            snapshot=snapshot,
            output_dir=output_path,
            case_id=case_id,
            raw_fetch_warning=raw_fetch_warning,
        )

    fetch_result = fetch_html(target_url)
    warning = render_warning or fetch_result.warning
    if fetch_result.html:
        annotated_html, fallback_inventory = _extract_clickables_from_html(
            fetch_result.html,
            "raw_html_fallback",
            "raw_html_fallback",
        )
        state_metadata = [
            {
                "state": "raw_html_fallback",
                "source": "raw_html_fallback",
                "attempted": True,
                "action": "fetch_html",
                "verified": False,
                "before_signature": None,
                "after_signature": {"html_length": len(fetch_result.html)},
                "change_signal": {"dom_changed": False, "signature_changed": False},
                "warning": "Solo se obtuvo HTML crudo; no hay confirmación de DOM renderizado.",
            }
        ]
        snapshot = DomSnapshot(
            target_url=target_url,
            source_url=fetch_result.final_url or target_url,
            final_url=fetch_result.final_url,
            raw_html=fetch_result.html,
            rendered_dom_html=annotated_html,
            render_engine="raw_html_fallback",
            warning=warning,
            fetch_warning=fetch_result.warning,
            states_captured=["raw_html_fallback"],
            state_html={"raw_html_fallback": annotated_html},
            clickable_inventory=fallback_inventory,
            state_metadata=state_metadata,
        )
        return _persist_dom_artifacts(snapshot=snapshot, output_dir=output_path, case_id=case_id)

    snapshot = DomSnapshot(
        target_url=target_url,
        source_url=target_url,
        final_url=None,
        raw_html=None,
        rendered_dom_html=None,
        render_engine="none",
        warning=warning or "No fue posible adquirir DOM ni HTML crudo.",
        fetch_warning=fetch_result.warning,
        states_captured=[],
        state_html={},
        clickable_inventory=[],
        state_metadata=state_metadata,
    )
    return _persist_dom_artifacts(snapshot=snapshot, output_dir=output_path, case_id=case_id)
