"""DOM snapshot utilities with Playwright-first strategy and clickable inventory extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from web_scraping.fetch_page import fetch_html

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # optional dependency
    sync_playwright = None  # type: ignore[assignment]


STATE_SEQUENCE = [
    "initial_render",
    "after_scroll",
    "nav_open",
    "tabs_expanded",
    "accordion_open",
    "carousel_ready",
]


@dataclass
class DomSnapshot:
    source_url: str
    raw_html: str | None
    rendered_dom_html: str | None
    render_engine: str
    warning: str | None = None
    fetch_warning: str | None = None
    states_captured: list[str] | None = None
    state_html: dict[str, str] | None = None
    clickable_inventory: list[dict[str, Any]] | None = None


def _extract_clickables_with_playwright(page: Any, state: str) -> list[dict[str, Any]]:
    script = """
    (stateName) => {
      const nodes = Array.from(document.querySelectorAll('a, button, [role="button"], summary, input, [onclick], [tabindex]'));
      function visible(el) {
        const r = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return !!(r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none');
      }
      function clickable(el) {
        if (el.tagName === 'A' && el.getAttribute('href')) return true;
        if (el.tagName === 'BUTTON') return true;
        if (el.tagName === 'SUMMARY') return true;
        if (el.getAttribute('role') === 'button') return true;
        if (el.hasAttribute('onclick')) return true;
        if (el.tagName === 'INPUT') {
          const t = (el.getAttribute('type') || '').toLowerCase();
          return ['button','submit','radio','checkbox','image'].includes(t);
        }
        const ti = el.getAttribute('tabindex');
        return ti !== null && ti !== '-1';
      }
      function ancestors(el) {
        const out = [];
        let c = el.parentElement;
        let i = 0;
        while (c && i < 5) {
          out.push({
            tag: (c.tagName || '').toLowerCase(),
            id: c.id || null,
            classes: Array.from(c.classList || []).slice(0,4)
          });
          c = c.parentElement;
          i += 1;
        }
        return out;
      }
      function selectorCandidates(el) {
        const c = [];
        const tag = (el.tagName || '').toLowerCase();
        if (el.id) c.push(`#${CSS.escape(el.id)}`);
        for (const a of el.getAttributeNames()) {
          if (a.startsWith('data-')) {
            const v = el.getAttribute(a);
            if (v) c.push(`${tag}[${a}="${CSS.escape(v)}"]`);
          }
        }
        const aria = el.getAttribute('aria-label');
        if (aria) c.push(`${tag}[aria-label="${CSS.escape(aria)}"]`);
        const href = el.getAttribute('href');
        if (href && href !== '#') c.push(`${tag}[href="${CSS.escape(href)}"]`);
        const classes = Array.from(el.classList || []).filter(x => x.length > 2).slice(0,2);
        if (classes.length) c.push(`${tag}.${classes.map(x => CSS.escape(x)).join('.')}`);
        c.push(tag);
        return Array.from(new Set(c));
      }
      return nodes.map((el) => {
        const r = el.getBoundingClientRect();
        return {
          tag: (el.tagName || '').toLowerCase(),
          text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 200),
          aria_label: el.getAttribute('aria-label'),
          title: el.getAttribute('title'),
          href: el.getAttribute('href'),
          id: el.id || null,
          class_list: Array.from(el.classList || []),
          ancestors: ancestors(el),
          outer_html_excerpt: (el.outerHTML || '').replace(/\\s+/g, ' ').slice(0, 500),
          bounding_box: {x: r.x, y: r.y, width: r.width, height: r.height},
          state: stateName,
          is_visible: visible(el),
          is_clickable: clickable(el),
          selector_candidates: selectorCandidates(el),
        };
      });
    }
    """
    return page.evaluate(script, state)


def _capture_playwright_states(target_url: str) -> tuple[dict[str, str] | None, list[dict[str, Any]], str | None]:
    if sync_playwright is None:
        return None, [], "Playwright no disponible; se usará fallback a HTML crudo."

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(target_url, wait_until="domcontentloaded", timeout=25000)

            state_html: dict[str, str] = {}
            inventory: list[dict[str, Any]] = []

            # initial_render
            state_html["initial_render"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "initial_render"))

            # after_scroll
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(800)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(400)
            state_html["after_scroll"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "after_scroll"))

            # nav_open
            page.evaluate(
                """
                () => {
                  const navToggle = document.querySelector('button[aria-controls], button[aria-expanded], [data-bs-toggle="collapse"], .menu-toggle, .navbar-toggler');
                  if (navToggle) navToggle.click();
                }
                """
            )
            page.wait_for_timeout(500)
            state_html["nav_open"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "nav_open"))

            # tabs_expanded
            page.evaluate(
                """
                () => {
                  const tabs = Array.from(document.querySelectorAll('[role="tab"], .tab, .tabs button')).slice(0,3);
                  tabs.forEach((t) => { try { t.click(); } catch(_) {} });
                }
                """
            )
            page.wait_for_timeout(500)
            state_html["tabs_expanded"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "tabs_expanded"))

            # accordion_open
            page.evaluate(
                """
                () => {
                  const cands = Array.from(document.querySelectorAll('summary, [aria-expanded="false"], .accordion button')).slice(0,5);
                  cands.forEach((el) => { try { el.click(); } catch(_) {} });
                }
                """
            )
            page.wait_for_timeout(500)
            state_html["accordion_open"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "accordion_open"))

            # carousel_ready
            page.evaluate(
                """
                () => {
                  const cands = Array.from(document.querySelectorAll('.swiper-button-next, .carousel-control-next, [aria-label*="next" i], [aria-label*="siguiente" i]')).slice(0,2);
                  cands.forEach((el) => { try { el.click(); } catch(_) {} });
                }
                """
            )
            page.wait_for_timeout(400)
            state_html["carousel_ready"] = page.content()
            inventory.extend(_extract_clickables_with_playwright(page, "carousel_ready"))

            browser.close()
            return state_html, inventory, None
    except Exception as exc:  # pragma: no cover
        return None, [], f"Falló render con Playwright; se usará fallback a HTML crudo. Detalle: {exc}"


def _extract_clickables_from_html(html: str, state: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    inventory: list[dict[str, Any]] = []
    for element in soup.select("a, button, [role='button'], summary, input, [onclick], [tabindex]"):
        classes = element.get("class") or []
        selector_candidates: list[str] = []
        if element.get("id"):
            selector_candidates.append(f"#{element.get('id')}")
        for attr in element.attrs:
            if str(attr).startswith("data-"):
                value = element.get(attr)
                if isinstance(value, str) and value:
                    selector_candidates.append(f"{element.name}[{attr}=\"{value}\"]")
        if element.get("aria-label"):
            selector_candidates.append(f"{element.name}[aria-label=\"{element.get('aria-label')}\"]")
        if element.get("href"):
            selector_candidates.append(f"{element.name}[href=\"{element.get('href')}\"]")
        if classes:
            selector_candidates.append(f"{element.name}." + ".".join(classes[:2]))
        selector_candidates.append(element.name)

        inventory.append(
            {
                "tag": element.name,
                "text": " ".join(element.get_text(" ", strip=True).split())[:200],
                "aria_label": element.get("aria-label"),
                "title": element.get("title"),
                "href": element.get("href"),
                "id": element.get("id"),
                "class_list": classes,
                "ancestors": [],
                "outer_html_excerpt": str(element)[:500],
                "bounding_box": None,
                "state": state,
                "is_visible": True,
                "is_clickable": True,
                "selector_candidates": list(dict.fromkeys(selector_candidates)),
            }
        )
    return inventory


def build_dom_snapshot(target_url: str) -> DomSnapshot:
    """Return normalized snapshot and clickable inventory, preferring Playwright states."""
    if not target_url:
        return DomSnapshot(
            source_url=target_url,
            raw_html=None,
            rendered_dom_html=None,
            render_engine="none",
            warning="No hay target_url para adquirir DOM.",
            fetch_warning="No hay target_url para scraping.",
            states_captured=[],
            state_html={},
            clickable_inventory=[],
        )

    state_html, inventory, render_warning = _capture_playwright_states(target_url)
    if state_html:
        states_captured = [state for state in STATE_SEQUENCE if state in state_html]
        return DomSnapshot(
            source_url=target_url,
            raw_html=None,
            rendered_dom_html=state_html.get("initial_render") or next(iter(state_html.values())),
            render_engine="playwright_multi_state",
            warning=None,
            fetch_warning=None,
            states_captured=states_captured,
            state_html=state_html,
            clickable_inventory=inventory,
        )

    fetch_result = fetch_html(target_url)
    warning = render_warning or fetch_result.warning
    if fetch_result.html:
        fallback_inventory = _extract_clickables_from_html(fetch_result.html, "raw_html_fallback")
        return DomSnapshot(
            source_url=fetch_result.final_url or target_url,
            raw_html=fetch_result.html,
            rendered_dom_html=fetch_result.html,
            render_engine="raw_html_fallback",
            warning=warning,
            fetch_warning=fetch_result.warning,
            states_captured=["raw_html_fallback"],
            state_html={"raw_html_fallback": fetch_result.html},
            clickable_inventory=fallback_inventory,
        )

    return DomSnapshot(
        source_url=target_url,
        raw_html=None,
        rendered_dom_html=None,
        render_engine="none",
        warning=warning or "No fue posible adquirir DOM ni HTML crudo.",
        fetch_warning=fetch_result.warning,
        states_captured=[],
        state_html={},
        clickable_inventory=[],
    )
