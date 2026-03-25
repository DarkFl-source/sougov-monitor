from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.sync_api import BrowserContext, Page, TimeoutError, sync_playwright


BASE_URL = "https://sougov.sigepe.gov.br"
LIST_URL = f"{BASE_URL}/sougov/BuscarOportunidades"
DEFAULT_STATE_PATH = Path("output/playwright/sougov-auth.json")
DEFAULT_JSON_PATH = Path("data/oportunidades.json")
DEFAULT_CSV_PATH = Path("data/oportunidades.csv")
DEFAULT_EDITAIS_DIR = Path("data/editais")
DEFAULT_PROFILE_DIR = Path("output/playwright/chrome-profile")
CHROME_ARGS = ["--disable-blink-features=AutomationControlled"]
CHROME_IGNORE_DEFAULT_ARGS = ["--enable-automation"]


@dataclass
class Opportunity:
    edital_id: str | None
    oportunidade_id: str | None
    orgao: str
    edital_numero: str
    oportunidade_titulo: str
    programa_gestao: str | None
    inscricao_texto: str | None
    inscricao_inicio: str | None
    inscricao_fim: str | None
    dias_para_encerrar: int | None
    edital_url: str | None
    oportunidade_url: str
    email_contato: str | None = None
    exigencia_legal: str | None = None
    unidade_lotacao: str | None = None
    local_atuacao: str | None = None
    movimentacao_detalhe: str | None = None
    atividades_executadas: str | None = None
    jornada_semanal_detalhe: str | None = None
    incentivo_gratificacao: str | None = None
    quantidade_vagas_detalhe: str | None = None
    vinculo_detalhe: str | None = None
    permite_estagio_probatorio: bool | None = None
    residencia_detalhe: str | None = None
    orgao_lotacao_detalhe: str | None = None
    orgao_exercicio_detalhe: str | None = None
    documentacao_detalhe: str | None = None
    conhecimentos_tecnicos_obrigatorios: str | None = None
    conhecimentos_tecnicos_desejaveis: str | None = None
    soft_skills_obrigatorias: str | None = None
    soft_skills_desejaveis: str | None = None
    idiomas_detalhe: str | None = None
    formacao_academica_detalhe: str | None = None
    certificacoes_detalhe: str | None = None
    outros_cursos_detalhe: str | None = None
    experiencias_necessarias: str | None = None
    detalhe_texto_integral: str | None = None
    erro_coleta_detalhe: str | None = None
    edital_pdf_path: str | None = None
    edital_pdf_url: str | None = None
    edital_pdf_status: str | None = None


@dataclass
class ScraperSession:
    context: BrowserContext
    page: Page
    close: Callable[[], None]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Coleta oportunidades do SOUGOV e aplica filtros locais mais amigaveis."
    )
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--editais-dir", type=Path, default=DEFAULT_EDITAIS_DIR)
    parser.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    parser.add_argument(
        "--attach-cdp",
        help="Conecta a um Chrome aberto manualmente com --remote-debugging-port, ex.: http://127.0.0.1:9222",
    )
    parser.add_argument("--headless", action="store_true", help="Executa o navegador sem UI.")
    parser.add_argument(
        "--refresh-login",
        action="store_true",
        help="Ignora o estado salvo e pede um novo login manual.",
    )
    parser.add_argument(
        "--query",
        help="Filtra por texto em orgao, numero do edital ou titulo da oportunidade.",
    )
    parser.add_argument("--orgao", help="Filtra por parte do nome do orgao.")
    parser.add_argument("--programa", help="Filtra por programa de gestao.")
    parser.add_argument(
        "--encerrando-em-ate",
        type=int,
        help="Mantem apenas oportunidades que encerram em ate N dias.",
    )
    parser.add_argument(
        "--limite",
        type=int,
        help="Limita a quantidade de registros exibidos no terminal.",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        help="Coleta detalhes apenas dos primeiros N registros apos os filtros iniciais.",
    )
    return parser.parse_args()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\\\|?*]+', "_", value)
    sanitized = re.sub(r"\s+", "_", sanitized).strip("._")
    return sanitized or "arquivo"


def parse_period(period_text: str | None) -> tuple[str | None, str | None]:
    if not period_text:
        return None, None
    normalized = normalize_space(period_text)
    match = re.search(
        r"(?:Inscrição:\s*)?De\s+(\d{2}/\d{2}/\d{4})\s+at[eé]\s+o\s+dia\s+(\d{2}/\d{2}/\d{4})",
        normalized,
        re.I,
    )
    if not match:
        return None, None
    return match.group(1), match.group(2)


def parse_ids_from_url(url: str | None) -> tuple[str | None, str | None]:
    if not url:
        return None, None
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    edital_id = params.get("IdEditalInput", [None])[0]
    oportunidade_id = params.get("IdOportunidadeInput", [None])[0]
    return edital_id, oportunidade_id


def page_requires_login(page: Page) -> bool:
    try:
        page.wait_for_function(
            """
            () => {
              const current = window.location.href.toLowerCase();
              if (current.includes('sso.acesso.gov.br')) return true;
              return document.querySelectorAll('div.item-edital').length > 0;
            }
            """,
            timeout=30000,
        )
    except TimeoutError:
        pass

    current = page.url.lower()
    if "sso.acesso.gov.br" in current:
        return True
    return page.locator("div.item-edital").count() == 0


def harden_context(context: BrowserContext) -> BrowserContext:
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined,
        });
        """
    )
    return context


def create_page_for_context(context: BrowserContext) -> tuple[Page, bool]:
    existing_pages = context.pages
    if existing_pages:
        return existing_pages[0], False
    return context.new_page(), True


def login_if_needed(page: Page, state_file: Path, force_refresh: bool) -> None:
    page.goto(LIST_URL, wait_until="domcontentloaded")

    if force_refresh or page_requires_login(page):
        print("Sessao ausente ou expirada. Conclua o login na janela do navegador e pressione Enter aqui.")
        try:
            input()
        except EOFError as exc:
            raise RuntimeError(
                "Sessao expirada e o script esta sem terminal interativo para aguardar novo login. "
                "Rode sem --headless ou use --refresh-login em uma execucao interativa."
            ) from exc
        page.goto(LIST_URL, wait_until="domcontentloaded")

    if page_requires_login(page):
        raise RuntimeError("Nao foi possivel acessar a lista de oportunidades apos o login.")

    ensure_parent(state_file)
    page.context.storage_state(path=str(state_file))


def expand_all_cards(page: Page) -> None:
    page.evaluate(
        """
        () => {
          const buttons = Array.from(document.querySelectorAll("[role='button'][aria-label*='Expandir']"));
          for (const button of buttons) {
            button.click();
          }
        }
        """
    )
    page.wait_for_timeout(1500)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except TimeoutError:
        pass


def collect_opportunities(page: Page) -> list[Opportunity]:
    raw_items = page.evaluate(
        """
        () => {
          const toText = (node) => (node?.textContent || '').replace(/\\s+/g, ' ').trim();
          const items = Array.from(document.querySelectorAll('div.item-edital'));
          return items.flatMap((item) => {
            const titleNode = item.querySelector('.container-title .title-left');
            const orgao = toText(titleNode?.querySelector('.nome-orgao'));
            const editalNumero = toText(titleNode?.querySelector('.numero-edital'));
            const diasTexto = toText(item.querySelector('.dias-encerramento .badge-azul-claro'));
            const editalHref = item.querySelector('.ver-edital a[href*="EditalDetalhe"]')?.getAttribute('href') || null;

            const cards = Array.from(item.querySelectorAll('.item-oportunidade'));
            if (cards.length) {
              return cards.map((card) => ({
                orgao: toText(card.querySelector('[id$="NomeOrgao"]')),
                edital_numero: toText(card.querySelector('[id$="Edital"]')) || editalNumero,
                oportunidade_titulo: toText(card.querySelector('.nome-oportunidade')),
                programa_gestao: toText(card.querySelector('.outro-dado-oportunidade span:last-child')) || null,
                inscricao_texto: toText(card.querySelector('[id*="PeriodoInscricao"]')) || null,
                dias_texto: diasTexto,
                edital_href: editalHref,
                oportunidade_href: card.querySelector('a[href*="OportunidadeDetalhe"]')?.getAttribute('href') || null,
              }));
            }

            const collapsedTitles = Array.from(item.querySelectorAll('.listitem, .list-group .list-item, li, [aria-label*="Nome da oportunidade"]'))
              .map((node) => toText(node))
              .filter(Boolean);

            return collapsedTitles.map((title) => ({
              orgao,
              edital_numero: editalNumero,
              oportunidade_titulo: title.replace(/^Nome da oportunidade \\d+ de \\d+:\\s*/i, ''),
              programa_gestao: null,
              inscricao_texto: null,
              dias_texto: diasTexto,
              edital_href: editalHref,
              oportunidade_href: null,
            }));
          });
        }
        """
    )

    results: list[Opportunity] = []
    for item in raw_items:
        edital_url = urljoin(BASE_URL, item["edital_href"]) if item.get("edital_href") else None
        oportunidade_url = (
            urljoin(BASE_URL, item["oportunidade_href"]) if item.get("oportunidade_href") else ""
        )
        edital_id, oportunidade_id = parse_ids_from_url(oportunidade_url or edital_url)
        inicio, fim = parse_period(item.get("inscricao_texto"))
        dias_match = re.search(r"(\d+)", item.get("dias_texto") or "")
        results.append(
            Opportunity(
                edital_id=edital_id,
                oportunidade_id=oportunidade_id,
                orgao=normalize_space(item.get("orgao")),
                edital_numero=normalize_space(item.get("edital_numero")),
                oportunidade_titulo=normalize_space(item.get("oportunidade_titulo")),
                programa_gestao=normalize_space(item.get("programa_gestao")) or None,
                inscricao_texto=normalize_space(item.get("inscricao_texto")) or None,
                inscricao_inicio=inicio,
                inscricao_fim=fim,
                dias_para_encerrar=int(dias_match.group(1)) if dias_match else None,
                edital_url=edital_url,
                oportunidade_url=oportunidade_url,
            )
        )
    return results


def filter_items(items: Iterable[Opportunity], args: argparse.Namespace) -> list[Opportunity]:
    filtered = list(items)

    if args.query:
        query = args.query.casefold()
        filtered = [
            item
            for item in filtered
            if query in item.orgao.casefold()
            or query in item.edital_numero.casefold()
            or query in item.oportunidade_titulo.casefold()
        ]

    if args.orgao:
        needle = args.orgao.casefold()
        filtered = [item for item in filtered if needle in item.orgao.casefold()]

    if args.programa:
        needle = args.programa.casefold()
        filtered = [
            item for item in filtered if item.programa_gestao and needle in item.programa_gestao.casefold()
        ]

    if args.encerrando_em_ate is not None:
        filtered = [
            item
            for item in filtered
            if item.dias_para_encerrar is not None and item.dias_para_encerrar <= args.encerrando_em_ate
        ]

    filtered.sort(
        key=lambda item: (
            item.dias_para_encerrar is None,
            item.dias_para_encerrar if item.dias_para_encerrar is not None else 9999,
            item.orgao.casefold(),
            item.oportunidade_titulo.casefold(),
        )
    )
    return filtered


def extract_between(text: str, start: str, end_markers: Iterable[str]) -> str | None:
    start_index = text.find(start)
    if start_index == -1:
        return None
    start_index += len(start)
    end_positions = [text.find(marker, start_index) for marker in end_markers]
    end_positions = [position for position in end_positions if position != -1]
    end_index = min(end_positions) if end_positions else len(text)
    value = normalize_space(text[start_index:end_index])
    return value or None


def wait_for_edital_page(page: Page) -> None:
    try:
        page.wait_for_function(
            """
            () => {
              const text = document.body?.innerText || '';
              return text.includes('Detalhar Edital')
                || text.includes('Informações do Edital')
                || text.includes('Baixar o edital')
                || text.length > 800;
            }
            """,
            timeout=30000,
        )
    except TimeoutError:
        page.wait_for_timeout(3000)


def build_edital_pdf_path(base_dir: Path, item: Opportunity, source_name: str | None = None) -> Path:
    ensure_parent(base_dir / ".gitkeep")
    edital_token = item.edital_id or sanitize_filename(item.edital_numero or "sem_edital")
    title_token = sanitize_filename(item.edital_numero or item.orgao or "edital")
    source_token = sanitize_filename(source_name or "")
    filename = f"edital_{edital_token}_{title_token}"
    if source_token:
        filename += f"_{source_token}"
    filename += ".pdf"
    return base_dir / filename


def extract_pdf_link_from_modal(page: Page) -> str | None:
    pdf_link = page.evaluate(
        """
        () => {
          const selectors = [
            '.modal a[href$=".pdf"]',
            '.modal a[href*=".pdf?"]',
            '.modal iframe[src]',
            '.modal embed[src]',
            '.modal object[data]',
            '[role="dialog"] a[href$=".pdf"]',
            '[role="dialog"] a[href*=".pdf?"]',
            '[role="dialog"] iframe[src]',
            '[role="dialog"] embed[src]',
            '[role="dialog"] object[data]',
          ];
          for (const selector of selectors) {
            const node = document.querySelector(selector);
            if (!node) continue;
            const value = node.getAttribute('href') || node.getAttribute('src') || node.getAttribute('data');
            if (value) return value;
          }
          return null;
        }
        """
    )
    if not pdf_link:
        return None
    if str(pdf_link).startswith("blob:"):
        return str(pdf_link)
    return urljoin(BASE_URL, str(pdf_link))


def click_modal_download_button(page: Page) -> None:
    page.evaluate(
        """
        () => {
          const link = document.querySelector('#popupDownload a[role="button"]');
          if (!link) throw new Error('botao interno do modal nao encontrado');
          link.click();
        }
        """
    )


def save_response_pdf(response, target_path: Path) -> tuple[str | None, str]:
    ensure_parent(target_path)
    target_path.write_bytes(response.body())
    return str(target_path), response.url


def download_edital_pdf(context: BrowserContext, page: Page, item: Opportunity, base_dir: Path) -> dict[str, str | None]:
    if not item.edital_url:
        return {"edital_pdf_status": "edital_sem_link"}

    page.goto(item.edital_url, wait_until="domcontentloaded")
    wait_for_edital_page(page)

    if "sso.acesso.gov.br" in page.url.lower() or "/sougov/" == urlparse(page.url).path:
        return {"edital_pdf_status": "sessao_expirada_pdf"}

    button = page.locator(
        "a[title*='Baixar o edital'], a[title*='Baixar o Edital'], a[title*='Baixar'], a.link-btn-pair[title*='Baixar']"
    ).first
    if button.count() == 0:
        return {"edital_pdf_status": "botao_pdf_nao_encontrado"}

    captured_responses = []

    def on_response(response) -> None:
        try:
            content_type = (response.headers.get("content-type") or "").lower()
        except Exception:  # noqa: BLE001
            return
        if "pdf" in content_type or response.url.lower().endswith(".pdf"):
            captured_responses.append(response)

    page.on("response", on_response)

    try:
        button.scroll_into_view_if_needed(timeout=5000)
        try:
            with page.expect_download(timeout=12000) as download_info:
                button.click(timeout=5000)
            download = download_info.value
            suggested_name = download.suggested_filename or f"edital_{item.edital_id or 'arquivo'}.pdf"
            target_path = build_edital_pdf_path(base_dir, item, Path(suggested_name).stem)
            ensure_parent(target_path)
            download.save_as(str(target_path))
            return {
                "edital_pdf_path": str(target_path),
                "edital_pdf_url": item.edital_url,
                "edital_pdf_status": "download_event",
            }
        except TimeoutError:
            button.click(timeout=5000, force=True)
            page.wait_for_timeout(2500)

        try:
            with page.expect_download(timeout=12000) as download_info:
                click_modal_download_button(page)
            download = download_info.value
            suggested_name = download.suggested_filename or f"edital_{item.edital_id or 'arquivo'}.pdf"
            target_path = build_edital_pdf_path(base_dir, item, Path(suggested_name).stem)
            ensure_parent(target_path)
            download.save_as(str(target_path))
            return {
                "edital_pdf_path": str(target_path),
                "edital_pdf_url": item.edital_url,
                "edital_pdf_status": "modal_download_event",
            }
        except Exception:  # noqa: BLE001
            page.wait_for_timeout(1500)

        pdf_link = extract_pdf_link_from_modal(page)
        if pdf_link and not pdf_link.startswith("blob:"):
            response = context.request.get(pdf_link, timeout=30000)
            if response.ok and "pdf" in (response.headers.get("content-type") or "").lower():
                target_path = build_edital_pdf_path(base_dir, item)
                ensure_parent(target_path)
                target_path.write_bytes(response.body())
                return {
                    "edital_pdf_path": str(target_path),
                    "edital_pdf_url": pdf_link,
                    "edital_pdf_status": "modal_link",
                }

        if captured_responses:
            target_path = build_edital_pdf_path(base_dir, item)
            pdf_path, pdf_url = save_response_pdf(captured_responses[-1], target_path)
            return {
                "edital_pdf_path": pdf_path,
                "edital_pdf_url": pdf_url,
                "edital_pdf_status": "network_response",
            }

        return {
            "edital_pdf_url": pdf_link,
            "edital_pdf_status": "pdf_nao_identificado",
        }
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:  # noqa: BLE001
            pass


def scrape_detail(page: Page, opportunity_url: str) -> dict[str, object]:
    page.goto(opportunity_url, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            """
            () => {
              const text = document.body?.innerText || '';
              return text.includes('Detalhar Oportunidade')
                && (text.includes('Sobre a oportunidade')
                  || text.includes('Requisitos da Oportunidade')
                  || text.includes('Documentação')
                  || text.length > 1200);
            }
            """,
            timeout=30000,
        )
    except TimeoutError:
        page.wait_for_timeout(3000)

    detail_text = normalize_space(page.locator("body").inner_text())
    if not detail_text or len(detail_text) < 200:
        raise RuntimeError(f"Detalhe nao carregou corretamente para {opportunity_url}")
    email_match = re.search(r"Email de Contato:\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", detail_text, re.I)
    vinculo = extract_between(
        detail_text,
        "Vínculo",
        ("Permitido Estágio Probatório", "Residência", "Documentação"),
    )
    return {
        "email_contato": email_match.group(1) if email_match else None,
        "exigencia_legal": extract_between(detail_text, "Exigência Legal:", ("DADOS GERAIS",)),
        "unidade_lotacao": extract_between(detail_text, "Unidade de Lotação", ("Local de atuação",)),
        "local_atuacao": extract_between(detail_text, "Local de atuação", ("Movimentação",)),
        "movimentacao_detalhe": extract_between(detail_text, "Movimentação", ("Atividades Executadas",)),
        "atividades_executadas": extract_between(detail_text, "Atividades Executadas", ("Programa de Gestão",)),
        "jornada_semanal_detalhe": extract_between(detail_text, "Jornada Semanal", ("Incentivos Gratificação",)),
        "incentivo_gratificacao": extract_between(detail_text, "Incentivos Gratificação", ("Quantidade de Vagas",)),
        "quantidade_vagas_detalhe": extract_between(detail_text, "Quantidade de Vagas", ("Requisitos da Oportunidade",)),
        "vinculo_detalhe": vinculo,
        "permite_estagio_probatorio": "Permitido Estágio Probatório" in detail_text,
        "residencia_detalhe": extract_between(detail_text, "Residência", ("Órgão de Lotação",)),
        "orgao_lotacao_detalhe": extract_between(detail_text, "Órgão de Lotação", ("Órgão de Exercício",)),
        "orgao_exercicio_detalhe": extract_between(detail_text, "Órgão de Exercício", ("Documentação",)),
        "documentacao_detalhe": extract_between(detail_text, "Documentação", ("Conhecimentos Técnicos",)),
        "conhecimentos_tecnicos_obrigatorios": extract_between(
            detail_text,
            "Conhecimentos Técnicos Obrigatórios",
            ("Desejáveis", "Competências Soft Skills"),
        ),
        "conhecimentos_tecnicos_desejaveis": extract_between(
            detail_text,
            "Conhecimentos Técnicos Obrigatórios Não há obrigatórios Desejáveis",
            ("Competências Soft Skills",),
        )
        or extract_between(detail_text, "Conhecimentos Técnicos Desejáveis", ("Competências Soft Skills",)),
        "soft_skills_obrigatorias": extract_between(
            detail_text,
            "Competências Soft Skills Obrigatórios",
            ("Desejáveis", "Idiomas"),
        ),
        "soft_skills_desejaveis": extract_between(
            detail_text,
            "Competências Soft Skills Obrigatórios Não há obrigatórios Desejáveis",
            ("Idiomas",),
        )
        or extract_between(detail_text, "Competências Soft Skills Desejáveis", ("Idiomas",)),
        "idiomas_detalhe": extract_between(detail_text, "Idiomas", ("Acadêmica", "Formação Acadêmica", "Certificações")),
        "formacao_academica_detalhe": extract_between(detail_text, "Acadêmica", ("Certificações", "Outros Cursos")),
        "certificacoes_detalhe": extract_between(detail_text, "Certificações", ("Outros Cursos", "Experiências Necessárias")),
        "outros_cursos_detalhe": extract_between(detail_text, "Outros Cursos", ("Experiências Necessárias",)),
        "experiencias_necessarias": extract_between(detail_text, "Experiências Necessárias", ("Quero me Candidatar",)),
        "detalhe_texto_integral": detail_text,
    }


def enrich_with_details(context: BrowserContext, items: list[Opportunity]) -> list[Opportunity]:
    detail_page = context.new_page()
    try:
        total = len(items)
        for index, item in enumerate(items, start=1):
            if not item.oportunidade_url:
                continue
            print(f"[{index}/{total}] Coletando detalhes: {item.oportunidade_titulo}")
            try:
                detail_data = scrape_detail(detail_page, item.oportunidade_url)
            except Exception as exc:  # noqa: BLE001
                item.erro_coleta_detalhe = str(exc)
                print(f"  aviso: falha ao coletar detalhes desta vaga: {exc}")
                continue
            for key, value in detail_data.items():
                setattr(item, key, value)
    finally:
        detail_page.close()
    return items


def enrich_with_edital_pdfs(context: BrowserContext, items: list[Opportunity], editais_dir: Path) -> list[Opportunity]:
    edital_page = context.new_page()
    cache: dict[str, dict[str, str | None]] = {}
    try:
        unique_keys: list[tuple[str, Opportunity]] = []
        seen: set[str] = set()
        for item in items:
            if not item.edital_url:
                continue
            key = item.edital_id or item.edital_url
            if key in seen:
                continue
            seen.add(key)
            unique_keys.append((key, item))

        total = len(unique_keys)
        for index, (key, sample_item) in enumerate(unique_keys, start=1):
            pdf_path = build_edital_pdf_path(editais_dir, sample_item)
            if pdf_path.exists():
                cache[key] = {
                    "edital_pdf_path": str(pdf_path),
                    "edital_pdf_url": sample_item.edital_url,
                    "edital_pdf_status": "arquivo_existente",
                }
                continue

            print(f"[PDF {index}/{total}] Baixando edital: {sample_item.edital_numero}")
            try:
                cache[key] = download_edital_pdf(context, edital_page, sample_item, editais_dir)
            except Exception as exc:  # noqa: BLE001
                cache[key] = {
                    "edital_pdf_status": f"erro_pdf: {exc}",
                    "edital_pdf_url": sample_item.edital_url,
                }
                print(f"  aviso: falha ao baixar PDF do edital: {exc}")

        for item in items:
            key = item.edital_id or item.edital_url
            if key and key in cache:
                for field, value in cache[key].items():
                    setattr(item, field, value)
    finally:
        edital_page.close()
    return items


def save_json(items: list[Opportunity], path: Path) -> None:
    ensure_parent(path)
    payload = {
        "capturado_em": datetime.now().isoformat(timespec="seconds"),
        "fonte": LIST_URL,
        "total": len(items),
        "items": [asdict(item) for item in items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(items: list[Opportunity], path: Path) -> None:
    ensure_parent(path)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(items[0]).keys()) if items else list(asdict(Opportunity(None, None, "", "", "", None, None, None, None, None, None, "")).keys()))
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def print_summary(items: list[Opportunity], limit: int | None) -> None:
    print(f"Total de oportunidades encontradas: {len(items)}")
    shown = items[:limit] if limit else items
    for item in shown:
        prazo = f"{item.dias_para_encerrar} dias" if item.dias_para_encerrar is not None else "prazo n/d"
        programa = item.programa_gestao or "programa n/d"
        print(f"- {item.orgao} | {item.edital_numero} | {item.oportunidade_titulo} | {programa} | {prazo}")
    if limit and len(items) > limit:
        print(f"... {len(items) - limit} itens adicionais omitidos do terminal.")


def create_managed_session(playwright, state_file: Path, profile_dir: Path, headless: bool, force_refresh: bool) -> ScraperSession:
    if force_refresh:
        profile_dir.mkdir(parents=True, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            no_viewport=True,
            accept_downloads=True,
            args=CHROME_ARGS,
            ignore_default_args=CHROME_IGNORE_DEFAULT_ARGS,
        )
        context = harden_context(context)
        page, _ = create_page_for_context(context)
        return ScraperSession(context=context, page=page, close=context.close)

    browser = playwright.chromium.launch(
        channel="chrome",
        headless=headless,
        args=CHROME_ARGS,
        ignore_default_args=CHROME_IGNORE_DEFAULT_ARGS,
    )
    context_args = {"storage_state": str(state_file)} if state_file.exists() else {}
    context = browser.new_context(accept_downloads=True, **context_args)
    context = harden_context(context)
    page, _ = create_page_for_context(context)

    def close_managed() -> None:
        context.close()
        browser.close()

    return ScraperSession(context=context, page=page, close=close_managed)


def create_attached_session(playwright, cdp_url: str) -> ScraperSession:
    try:
        browser = playwright.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Nao foi possivel conectar ao Chrome em {cdp_url}. "
            "Abra o Chrome manualmente com --remote-debugging-port=9222 e mantenha-o aberto."
        ) from exc
    if not browser.contexts:
        raise RuntimeError(
            "Nenhum contexto foi encontrado no Chrome conectado. Abra o Chrome manual com --remote-debugging-port "
            "e mantenha ao menos uma aba aberta antes de anexar."
        )
    context = browser.contexts[0]
    page, page_created = create_page_for_context(context)

    def close_attached() -> None:
        try:
            if page_created and not page.is_closed():
                page.close()
        except Exception:  # noqa: BLE001
            pass
        browser.close()

    return ScraperSession(context=context, page=page, close=close_attached)


def main() -> int:
    args = parse_args()

    with sync_playwright() as playwright:
        if args.attach_cdp:
            session = create_attached_session(playwright, args.attach_cdp)
        else:
            session = create_managed_session(
                playwright,
                args.state_file,
                args.profile_dir,
                headless=args.headless,
                force_refresh=args.refresh_login,
            )
        try:
            login_if_needed(session.page, args.state_file, force_refresh=args.refresh_login)
            expand_all_cards(session.page)
            items = collect_opportunities(session.page)
            items = filter_items(items, args)
            if args.max_details is not None:
                items = items[: args.max_details]
            items = enrich_with_edital_pdfs(session.context, items, args.editais_dir)
            items = enrich_with_details(session.context, items)
        finally:
            session.close()

    filtered_items = items
    save_json(filtered_items, args.json_out)
    save_csv(filtered_items, args.csv_out)
    print_summary(filtered_items, args.limite)
    print(f"JSON salvo em: {args.json_out}")
    print(f"CSV salvo em: {args.csv_out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Execucao interrompida pelo usuario.", file=sys.stderr)
        raise SystemExit(130)
