from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st


DATA_PATH = Path("data/oportunidades.json")
DATE_COLUMNS = ["inscricao_inicio", "inscricao_fim"]


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    df = pd.DataFrame(payload["items"])

    for column in DATE_COLUMNS:
        df[f"{column}_dt"] = pd.to_datetime(df[column], format="%d/%m/%Y", errors="coerce")

    df["dias_para_encerrar"] = pd.to_numeric(df["dias_para_encerrar"], errors="coerce")
    df["permite_estagio_probatorio"] = df["permite_estagio_probatorio"].fillna(False).astype(bool)

    text_columns = [
        "orgao",
        "edital_numero",
        "oportunidade_titulo",
        "programa_gestao",
        "local_atuacao",
        "movimentacao_detalhe",
        "vinculo_detalhe",
        "atividades_executadas",
        "conhecimentos_tecnicos_desejaveis",
        "soft_skills_desejaveis",
        "formacao_academica_detalhe",
        "experiencias_necessarias",
        "detalhe_texto_integral",
    ]
    for column in text_columns:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").map(normalize_text)

    df["busca_texto"] = df[text_columns].agg(" ".join, axis=1).str.casefold()
    df["is_ti"] = df["busca_texto"].str.contains(
        "ti|tecnologia|dados|segurança da informação|infraestrutura|lgpd|sistema|gsisp",
        regex=True,
        na=False,
    )
    df["is_brasilia"] = df["local_atuacao"].str.contains("brasília|brasilia", case=False, na=False)
    df["prazo_categoria"] = df["dias_para_encerrar"].apply(classify_deadline)
    for column in ["edital_pdf_path", "edital_pdf_url", "edital_pdf_status"]:
        if column not in df.columns:
            df[column] = ""
        df[column] = df[column].fillna("").map(normalize_text)
    return df


def classify_deadline(days: float | int | None) -> str:
    if pd.isna(days):
        return "Prazo não informado"
    if days <= 3:
        return "Urgente"
    if days <= 7:
        return "Próximos 7 dias"
    if days <= 15:
        return "Próximos 15 dias"
    return "Mais adiante"


def compute_keyword_score(df: pd.DataFrame, raw_terms: str) -> pd.Series:
    terms = [normalize_text(term).casefold() for term in raw_terms.split(",") if normalize_text(term)]
    if not terms:
        return pd.Series([0] * len(df), index=df.index, dtype="int64")
    return df["busca_texto"].apply(lambda text: sum(1 for term in terms if term in text))


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filtros")
    busca = st.sidebar.text_input(
        "Busca livre",
        placeholder="Ex.: dados, jurídico, Brasília, GSISP, comunicação",
    )
    palavras_prioritarias = st.sidebar.text_input(
        "Palavras-chave do meu perfil",
        placeholder="Ex.: dados, contratos, TI, LGPD",
        help="Separar por vírgula. O painel usa essas palavras para priorizar resultados.",
    )

    orgaos = sorted(value for value in df["orgao"].dropna().unique() if value)
    programas = sorted(value for value in df["programa_gestao"].dropna().unique() if value)
    locais = sorted(value for value in df["local_atuacao"].dropna().unique() if value)
    vinculacoes = sorted(value for value in df["vinculo_detalhe"].dropna().unique() if value)

    orgaos_sel = st.sidebar.multiselect("Órgão", options=orgaos)
    programas_sel = st.sidebar.multiselect("Programa de gestão", options=programas)
    locais_sel = st.sidebar.multiselect("Local de atuação", options=locais)
    vinculos_sel = st.sidebar.multiselect("Vínculo", options=vinculacoes)

    prazo_max = st.sidebar.slider("Encerra em até (dias)", min_value=0, max_value=90, value=90)
    somente_ti = st.sidebar.checkbox("Apenas vagas com perfil TI/dados")
    somente_brasilia = st.sidebar.checkbox("Apenas Brasília/DF")
    somente_estagio = st.sidebar.checkbox("Permite estágio probatório")
    somente_com_email = st.sidebar.checkbox("Somente com e-mail de contato")

    filtered = df.copy()
    filtered["aderencia_score"] = compute_keyword_score(filtered, palavras_prioritarias)

    if busca:
        filtered = filtered[filtered["busca_texto"].str.contains(busca.casefold(), na=False)]
    if orgaos_sel:
        filtered = filtered[filtered["orgao"].isin(orgaos_sel)]
    if programas_sel:
        filtered = filtered[filtered["programa_gestao"].isin(programas_sel)]
    if locais_sel:
        filtered = filtered[filtered["local_atuacao"].isin(locais_sel)]
    if vinculos_sel:
        filtered = filtered[filtered["vinculo_detalhe"].isin(vinculos_sel)]
    filtered = filtered[
        filtered["dias_para_encerrar"].isna() | (filtered["dias_para_encerrar"] <= prazo_max)
    ]
    if somente_ti:
        filtered = filtered[filtered["is_ti"]]
    if somente_brasilia:
        filtered = filtered[filtered["is_brasilia"]]
    if somente_estagio:
        filtered = filtered[filtered["permite_estagio_probatorio"]]
    if somente_com_email:
        filtered = filtered[filtered["email_contato"].fillna("") != ""]

    filtered = filtered.sort_values(
        by=["aderencia_score", "dias_para_encerrar", "orgao", "oportunidade_titulo"],
        ascending=[False, True, True, True],
        na_position="last",
    )
    return filtered


def format_date(value: object) -> str:
    if pd.isna(value) or value in (None, ""):
        return "-"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")
    return str(value)


def urgency_badge(days: object) -> str:
    if pd.isna(days):
        return "Prazo n/d"
    days_int = int(days)
    if days_int <= 3:
        return f"Encerra em {days_int} dia(s)"
    if days_int <= 7:
        return f"Fecha em {days_int} dia(s)"
    return f"{days_int} dias restantes"


def render_metrics(df: pd.DataFrame) -> None:
    total = len(df)
    urgentes = int((df["dias_para_encerrar"].fillna(999) <= 7).sum())
    brasilia = int(df["is_brasilia"].sum())
    ti = int(df["is_ti"].sum())
    cols = st.columns(4)
    cols[0].metric("Vagas filtradas", total)
    cols[1].metric("Fecham em até 7 dias", urgentes)
    cols[2].metric("Em Brasília/DF", brasilia)
    cols[3].metric("Com perfil TI/dados", ti)


def render_cards(df: pd.DataFrame) -> None:
    for _, row in df.iterrows():
        aderencia = int(row.get("aderencia_score", 0) or 0)
        badge = urgency_badge(row.get("dias_para_encerrar"))
        row_key = f"{row.get('edital_id', '')}-{row.get('oportunidade_id', '')}"
        subtitle_parts = [
            row["orgao"],
            row["edital_numero"],
            row["programa_gestao"] or "Programa n/d",
        ]
        if row["local_atuacao"]:
            subtitle_parts.append(row["local_atuacao"])

        with st.container(border=True):
            col_a, col_b = st.columns([4, 1])
            col_a.markdown(f"### {row['oportunidade_titulo']}")
            col_a.caption(" | ".join(part for part in subtitle_parts if part))
            col_b.metric("Aderência", aderencia)

            st.markdown(
                f"**Prazo:** {badge}  \n"
                f"**Inscrição:** {row['inscricao_inicio'] or '-'} até {row['inscricao_fim'] or '-'}  \n"
                f"**Contato:** {row['email_contato'] or '-'}"
            )

            resumo = row["atividades_executadas"] or row["detalhe_texto_integral"]
            if resumo:
                st.write(resumo[:500] + ("..." if len(resumo) > 500 else ""))

            with st.expander("Ver mais detalhes"):
                details = {
                    "Unidade de lotação": row["unidade_lotacao"],
                    "Movimentação": row["movimentacao_detalhe"],
                    "Vínculo": row["vinculo_detalhe"],
                    "Jornada semanal": row["jornada_semanal_detalhe"],
                    "Quantidade de vagas": row["quantidade_vagas_detalhe"],
                    "Conhecimentos desejáveis": row["conhecimentos_tecnicos_desejaveis"],
                    "Soft skills desejáveis": row["soft_skills_desejaveis"],
                    "Formação": row["formacao_academica_detalhe"],
                    "Experiências necessárias": row["experiencias_necessarias"],
                    "Documentação": row["documentacao_detalhe"],
                    "Exigência legal": row["exigencia_legal"],
                }
                for label, value in details.items():
                    if normalize_text(value):
                        st.markdown(f"**{label}:** {value}")

                link_cols = st.columns(3)
                if row["oportunidade_url"]:
                    link_cols[0].link_button("Abrir vaga", row["oportunidade_url"], use_container_width=True)
                if row["edital_url"]:
                    link_cols[1].link_button("Abrir edital", row["edital_url"], use_container_width=True)
                pdf_path_value = row.get("edital_pdf_path", "")
                if pdf_path_value:
                    pdf_path = Path(pdf_path_value)
                    if pdf_path.exists():
                        link_cols[2].download_button(
                            "Baixar PDF do edital",
                            data=pdf_path.read_bytes(),
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"pdf-{row_key}",
                        )
                    else:
                        link_cols[2].caption("PDF esperado, mas arquivo não foi encontrado.")
                elif row.get("edital_pdf_status"):
                    link_cols[2].caption(f"PDF: {row['edital_pdf_status']}")


def render_table(df: pd.DataFrame) -> None:
    table_df = df[
        [
            "aderencia_score",
            "dias_para_encerrar",
            "orgao",
            "oportunidade_titulo",
            "programa_gestao",
            "local_atuacao",
            "inscricao_inicio",
            "inscricao_fim",
            "email_contato",
            "edital_pdf_status",
            "oportunidade_url",
        ]
    ].rename(
        columns={
            "aderencia_score": "Aderência",
            "dias_para_encerrar": "Dias p/ encerrar",
            "orgao": "Órgão",
            "oportunidade_titulo": "Oportunidade",
            "programa_gestao": "Programa",
            "local_atuacao": "Local",
            "inscricao_inicio": "Inscrição início",
            "inscricao_fim": "Inscrição fim",
            "email_contato": "E-mail",
            "edital_pdf_status": "Status PDF edital",
            "oportunidade_url": "Link",
        }
    )
    st.dataframe(table_df, use_container_width=True, hide_index=True)


def render_insights(df: pd.DataFrame) -> None:
    st.subheader("Recortes rápidos")

    by_orgao = (
        df.groupby("orgao", dropna=False)
        .size()
        .reset_index(name="quantidade")
        .sort_values("quantidade", ascending=False)
        .head(15)
    )
    by_programa = (
        df.groupby("programa_gestao", dropna=False)
        .size()
        .reset_index(name="quantidade")
        .sort_values("quantidade", ascending=False)
    )

    col_a, col_b = st.columns(2)
    col_a.markdown("**Top órgãos no recorte**")
    col_a.dataframe(by_orgao, use_container_width=True, hide_index=True)
    col_b.markdown("**Distribuição por programa**")
    col_b.dataframe(by_programa, use_container_width=True, hide_index=True)

    urgentes = df[df["dias_para_encerrar"].fillna(math.inf) <= 7][
        ["orgao", "oportunidade_titulo", "dias_para_encerrar", "email_contato"]
    ]
    st.markdown("**Oportunidades com prazo mais curto**")
    st.dataframe(urgentes.head(20), use_container_width=True, hide_index=True)


def download_filtered_csv(df: pd.DataFrame) -> None:
    csv_bytes = df.drop(columns=["busca_texto"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar CSV do recorte filtrado",
        data=csv_bytes,
        file_name="oportunidades-filtradas.csv",
        mime="text/csv",
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Monitor de Oportunidades SOUGOV",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("Monitor de Oportunidades SOUGOV")
    st.caption("Pesquisa local com filtros, priorização por palavras-chave e acesso rápido aos detalhes.")

    if not DATA_PATH.exists():
        st.error("Arquivo de dados não encontrado. Gere primeiro `data/oportunidades.json` com o scraper.")
        st.stop()

    df = load_data(str(DATA_PATH))
    filtered = apply_filters(df)

    st.sidebar.markdown("---")
    st.sidebar.write(f"Base carregada: **{len(df)}** oportunidades")
    st.sidebar.write(f"Recorte atual: **{len(filtered)}** oportunidades")

    render_metrics(filtered)
    download_filtered_csv(filtered)

    cards_tab, table_tab, insights_tab = st.tabs(["Cards", "Tabela", "Insights"])

    with cards_tab:
        limit = st.select_slider(
            "Quantidade de cards exibidos",
            options=[10, 20, 30, 50, 100, 200],
            value=20,
        )
        render_cards(filtered.head(limit))

    with table_tab:
        render_table(filtered)

    with insights_tab:
        render_insights(filtered)


if __name__ == "__main__":
    main()
