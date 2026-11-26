r"""
MODÜL 6: Modern, Sade ve Adım Adım Yönlendirmeli Avukat Asistanı Arayüzü (app.py — ADIM 12)
-------------------------------------------------------------------------------------------
Çalıştırmak için:
    .\baslat.bat
veya:
    streamlit run app.py
"""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import streamlit as st

import legal_parser
import precedent_fetcher
import legal_rag_verifier
import petition_drafter
import legal_chat

importlib.reload(legal_parser)
importlib.reload(precedent_fetcher)
importlib.reload(legal_rag_verifier)
importlib.reload(petition_drafter)
importlib.reload(legal_chat)

from legal_parser import (
    LegalDocumentParser,
    ParsedLegalDocument,
    LegalClaimItem,
    PrecedentCitation,
    StatuteReference,
    ProceduralCheckItem,
    DEMO_PETITIONS,
)
from precedent_fetcher import (
    PrecedentFetcher,
    FetchedPrecedent,
    FetchedStatute,
    USER_ICTIHAT_PDF_DIR,
    safe_ref_token,
)
from legal_rag_verifier import (
    LegalRAGVerifier,
    LegalClaimVerificationResult,
    LegalEvidenceChunk,
    ExecutiveLegalSummary,
    PREFERRED_OLLAMA_MODELS,
)
from petition_drafter import (
    PetitionDrafter,
    PetitionDraftRequest,
    GeneratedPetitionPackage,
    PETITION_TYPES,
    LEGAL_DOMAINS,
    get_legal_verdict_info,
)
from legal_chat import (
    LegalChatAssistant,
    LegalChatResponse,
)


# ---------------------------------------------------------------------------
# Yönlendirmeli Akış (Guided Wizard) Durum Yönetimi
# ---------------------------------------------------------------------------

if "wizard_track" not in st.session_state:
    st.session_state["wizard_track"] = "HOME"
if "doc_wizard_step" not in st.session_state:
    st.session_state["doc_wizard_step"] = 1
if "ai_wizard_tool" not in st.session_state:
    st.session_state["ai_wizard_tool"] = "CHAT"

wizard_track = st.session_state["wizard_track"]
doc_step = st.session_state["doc_wizard_step"]
ai_tool = st.session_state["ai_wizard_tool"]

st.set_page_config(
    page_title="Avukat Asistanı — Dilekçe, İçtihat ve Strateji Platformu",
    page_icon=":material/gavel:",
    layout="wide",
    initial_sidebar_state="collapsed" if wizard_track == "HOME" else "expanded",
)

hide_sidebar_css = (
    """
    section[data-testid="stSidebar"],
    div[data-testid="collapsedControl"],
    button[kind="headerNoPadding"] {
        display: none !important;
    }
    .block-container {
        max-width: 1020px !important;
        padding-top: 3.6rem !important;
    }
    """
    if wizard_track == "HOME"
    else """
    .block-container {
        max-width: 1180px !important;
        padding-top: 2.8rem !important;
        padding-bottom: 3.5rem !important;
    }
    section[data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 300px !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.3rem !important;
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
    }
    section[data-testid="stSidebar"] .stButton > button {
        justify-content: flex-start !important;
        text-align: left !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        padding: 0.48rem 0.7rem !important;
        border-radius: 8px !important;
    }
    """
)

st.html(
    f"""
    <style>
    {hide_sidebar_css}

    /* Üst Rehber Başlık Kartı */
    .guide-banner {{
        background: linear-gradient(135deg, rgba(30, 58, 138, 0.42) 0%, rgba(15, 23, 42, 0.94) 100%);
        border: 1px solid rgba(59, 130, 246, 0.35);
        border-left: 4px solid #3B82F6;
        border-radius: 14px;
        padding: 1.1rem 1.4rem;
        margin-bottom: 1.2rem;
    }}
    .guide-step-badge {{
        display: inline-block;
        background: rgba(59, 130, 246, 0.22);
        color: #93C5FD;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.18rem 0.65rem;
        border-radius: 999px;
        margin-bottom: 0.35rem;
        letter-spacing: 0.04em;
    }}
    .guide-title {{
        font-size: 1.28rem;
        font-weight: 800;
        color: #F8FAFC;
        margin: 0 0 0.2rem 0;
    }}
    .guide-desc {{
        font-size: 0.91rem;
        color: #CBD5E1;
        margin: 0;
        line-height: 1.45;
    }}

    /* Karşılama Ekranı: Yalnızca HOME ekranındaki kart butonlarını uzun ve tıklanabilir kart yap */
    """
    + (
        """
    div[data-testid="stHorizontalBlock"] .stButton > button {
        background: linear-gradient(155deg, rgba(30, 41, 59, 0.82) 0%, rgba(15, 23, 42, 0.96) 100%) !important;
        border: 1.5px solid rgba(96, 165, 250, 0.36) !important;
        border-radius: 18px !important;
        padding: 1.9rem 1.85rem !important;
        min-height: 310px !important;
        height: 310px !important;
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: flex-start !important;
        text-align: left !important;
        transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1),
                    border-color 0.22s ease,
                    box-shadow 0.22s ease,
                    background 0.22s ease !important;
        cursor: pointer !important;
        box-shadow: 0 8px 24px -8px rgba(0, 0, 0, 0.35) !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button:hover {
        transform: translateY(-6px) !important;
        border-color: #60A5FA !important;
        box-shadow: 0 18px 38px -8px rgba(37, 99, 235, 0.42) !important;
        background: linear-gradient(155deg, rgba(30, 58, 138, 0.48) 0%, rgba(15, 23, 42, 0.98) 100%) !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
        text-align: left !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button p {
        text-align: left !important;
        white-space: pre-line !important;
        line-height: 1.72 !important;
        font-size: 0.93rem !important;
        font-weight: 400 !important;
        color: #CBD5E1 !important;
        margin: 0 !important;
    }
    /* Streamlit tek <p> üretse bile <strong> başlığı ayrı bir üst blok ve çizgili başlık olur! */
    div[data-testid="stHorizontalBlock"] .stButton > button p strong {
        display: block !important;
        font-size: 1.24rem !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        border-bottom: 1px solid rgba(148, 163, 184, 0.24) !important;
        padding-bottom: 0.65rem !important;
        margin-bottom: 0.75rem !important;
        width: 100% !important;
    }
    """
        if wizard_track == "HOME"
        else ""
    )
    + (
        """
    /* ADIM 1: İnceleme Amacı Seçim Kartları (Her ikisi de aynı parlaklıkta, başlık ayrı blokta ve hover hareketli) */
    div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button {
        background: linear-gradient(155deg, rgba(30, 41, 59, 0.82) 0%, rgba(15, 23, 42, 0.96) 100%) !important;
        border: 1.5px solid rgba(96, 165, 250, 0.36) !important;
        border-radius: 16px !important;
        padding: 1.45rem 1.55rem !important;
        min-height: 175px !important;
        height: 175px !important;
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: flex-start !important;
        text-align: left !important;
        transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1),
                    border-color 0.22s ease,
                    box-shadow 0.22s ease,
                    background 0.22s ease !important;
        cursor: pointer !important;
        box-shadow: 0 8px 22px -6px rgba(0, 0, 0, 0.32) !important;
    }
    div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button:hover {
        transform: translateY(-5px) !important;
        border-color: #60A5FA !important;
        box-shadow: 0 16px 34px -8px rgba(37, 99, 235, 0.42) !important;
        background: linear-gradient(155deg, rgba(30, 58, 138, 0.48) 0%, rgba(15, 23, 42, 0.98) 100%) !important;
    }
    div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
        text-align: left !important;
    }
    div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button p {
        text-align: left !important;
        white-space: pre-line !important;
        line-height: 1.58 !important;
        font-size: 0.91rem !important;
        font-weight: 400 !important;
        color: #CBD5E1 !important;
        margin: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button p strong {
        display: block !important;
        font-size: 1.15rem !important;
        font-weight: 800 !important;
        color: #FFFFFF !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        border-bottom: 1px solid rgba(148, 163, 184, 0.24) !important;
        padding-bottom: 0.55rem !important;
        margin-bottom: 0.65rem !important;
        width: 100% !important;
    }
    """
        if (wizard_track == "DOC_FLOW" and doc_step == 1)
        else ""
    )
    + f"""
    /* Segmented Control Seçili Sekme Yazısını Parlak Beyaz Yap (Koyu Mavi Okunaksızlığını Gider) */
    div[data-baseweb="button-group"] button[aria-pressed="true"],
    div[data-baseweb="button-group"] button[aria-checked="true"] {{
        background-color: rgba(37, 99, 235, 0.35) !important;
        border-color: #3B82F6 !important;
        color: #FFFFFF !important;
    }}
    div[data-baseweb="button-group"] button p {{
        color: #F8FAFC !important;
        font-weight: 600 !important;
    }}

    /* Dosya Yükleme (Dropzone) ve Segmented Control Modernizasyonu */
    section[data-testid="stFileUploaderDropzone"] {{
        border: 2px dashed rgba(59, 130, 246, 0.48) !important;
        border-radius: 14px !important;
        background: rgba(30, 41, 59, 0.38) !important;
        padding: 1.35rem 1.2rem !important;
        transition: all 0.2s ease !important;
    }}
    section[data-testid="stFileUploaderDropzone"]:hover {{
        border-color: #60A5FA !important;
        background: rgba(30, 58, 138, 0.25) !important;
        transform: translateY(-2px) !important;
    }}

    /* ADIM 16: Tüm Sayfalardaki Çerçeveli Kartlar, Metrik Kutuları ve Expanderlar İçin Hover & Glassmorphism */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: linear-gradient(155deg, rgba(30, 41, 59, 0.58) 0%, rgba(15, 23, 42, 0.88) 100%) !important;
        border: 1px solid rgba(96, 165, 250, 0.24) !important;
        border-radius: 14px !important;
        transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease !important;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
        border-color: rgba(96, 165, 250, 0.55) !important;
        box-shadow: 0 10px 26px -8px rgba(37, 99, 235, 0.25) !important;
    }}

    /* Metrik Kutuları (Adım 2 ve Adım 3 Sayaçları) */
    div[data-testid="stMetric"] {{
        padding: 0.25rem 0.2rem !important;
    }}
    div[data-testid="stMetricValue"] {{
        font-weight: 800 !important;
        color: #F8FAFC !important;
    }}

    /* Örnek Hukuk Sorusu Kart Butonları ve İndirme/Geçiş Butonları Hover Efekti */
    .block-container .stButton > button,
    .block-container .stDownloadButton > button {{
        border-radius: 11px !important;
        font-weight: 600 !important;
        transition: transform 0.18s cubic-bezier(0.22, 1, 0.36, 1),
                    border-color 0.18s ease,
                    box-shadow 0.18s ease !important;
    }}
    .block-container .stButton > button:hover,
    .block-container .stDownloadButton > button:hover {{
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 22px -6px rgba(37, 99, 235, 0.35) !important;
    }}

    /* Emsal Karar Sonuç Kartı Başlığı */
    .precedent-card-header {{
        font-size: 1.08rem;
        font-weight: 800;
        color: #FFFFFF;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        border-bottom: 1px solid rgba(148, 163, 184, 0.18);
        padding-bottom: 0.45rem;
        margin-bottom: 0.55rem;
    }}

    /* Sol Menü Marka Kartı */
    .sidebar-brand-card {{
        background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 100%);
        border: 1px solid rgba(96, 165, 250, 0.35);
        border-radius: 10px;
        padding: 0.78rem 0.88rem;
        margin-bottom: 0.7rem;
    }}
    .sidebar-brand-title {{
        font-size: 1.02rem;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0;
    }}
    .sidebar-brand-sub {{
        font-size: 0.75rem;
        color: #93C5FD;
        margin: 0.14rem 0 0 0;
    }}
    </style>
    """
)


# ---------------------------------------------------------------------------
# Önbellekli Motor Nesneleri ve Oturum Klasörü
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Hukuk ve içtihat motoru hazırlanıyor...")
def get_verifier(ollama_model: str, use_llm: bool = True) -> LegalRAGVerifier:
    return LegalRAGVerifier(ollama_model=ollama_model, embedding_device="cpu", use_llm=use_llm)


def get_parser() -> LegalDocumentParser:
    return LegalDocumentParser()


def get_fetcher() -> PrecedentFetcher:
    return PrecedentFetcher(timeout=4)


def get_drafter() -> PetitionDrafter:
    return PetitionDrafter(fetcher=get_fetcher())


SESSIONS_DIR = Path("raporlar/oturumlar")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Oturum Kaydetme, Geri Yükleme ve Sekme Hafızası İzolasyonu
# ---------------------------------------------------------------------------

def _session_file_for_doc(filename: str) -> Path:
    stem = safe_ref_token(Path(filename).stem, fallback="dilekce")
    return SESSIONS_DIR / f"{stem}.analiz.json"


def merge_legal_verification_results(
    all_claims: List[LegalClaimItem],
    existing_results: List[LegalClaimVerificationResult],
    new_results: List[LegalClaimVerificationResult],
) -> List[LegalClaimVerificationResult]:
    by_id: Dict[str, LegalClaimVerificationResult] = {r.claim_id: r for r in existing_results}
    for nr in new_results:
        by_id[nr.claim_id] = nr

    ordered: List[LegalClaimVerificationResult] = []
    seen: set[str] = set()
    for cl in all_claims:
        if cl.claim_id in by_id:
            ordered.append(by_id[cl.claim_id])
            seen.add(cl.claim_id)
    for cid, res in by_id.items():
        if cid not in seen:
            ordered.append(res)
    return ordered


def serialize_legal_session_bytes(
    parsed_doc: ParsedLegalDocument,
    cited_map: Dict[str, FetchedPrecedent],
    claim_precs_map: Dict[str, List[FetchedPrecedent]],
    statutes_map: Dict[str, FetchedStatute],
    verification_results: List[LegalClaimVerificationResult],
    lawyer_mode: str = "MOD_B",
) -> bytes:
    payload = {
        "format_version": "1.0",
        "saved_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "filename": parsed_doc.filename,
        "lawyer_mode": lawyer_mode,
        "verified_count": len(verification_results),
        "total_claims": len(parsed_doc.claims),
        "parsed_doc": parsed_doc.to_dict(),
        "cited_map": {k: v.to_dict() for k, v in cited_map.items()},
        "claim_precs_map": {k: [p.to_dict() for p in plist] for k, plist in claim_precs_map.items()},
        "statutes_map": {k: v.to_dict() for k, v in statutes_map.items()},
        "verification_results": [r.to_dict() for r in verification_results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def save_legal_session_to_disk(
    parsed_doc: ParsedLegalDocument,
    cited_map: Dict[str, FetchedPrecedent],
    claim_precs_map: Dict[str, List[FetchedPrecedent]],
    statutes_map: Dict[str, FetchedStatute],
    verification_results: List[LegalClaimVerificationResult],
    lawyer_mode: str = "MOD_B",
) -> Optional[Path]:
    try:
        target = _session_file_for_doc(parsed_doc.filename)
        target.write_bytes(
            serialize_legal_session_bytes(
                parsed_doc=parsed_doc,
                cited_map=cited_map,
                claim_precs_map=claim_precs_map,
                statutes_map=statutes_map,
                verification_results=verification_results,
                lawyer_mode=lawyer_mode,
            )
        )
        return target
    except Exception:
        return None


def deserialize_legal_session_bytes(
    raw_bytes: bytes,
) -> Tuple[
    ParsedLegalDocument,
    Dict[str, FetchedPrecedent],
    Dict[str, List[FetchedPrecedent]],
    Dict[str, FetchedStatute],
    List[LegalClaimVerificationResult],
    str,
    str,
]:
    data = json.loads(raw_bytes.decode("utf-8"))
    saved_at = str(data.get("saved_at", "-"))
    lawyer_mode = str(data.get("lawyer_mode", "MOD_B"))
    p_raw = data["parsed_doc"]

    parsed_doc = ParsedLegalDocument(
        filename=p_raw.get("filename", "dilekce.docx"),
        total_chars=int(p_raw.get("total_chars", 0)),
        page_count=int(p_raw.get("page_count", 1)),
        document_type=p_raw.get("document_type", "Dava Dilekçesi"),
        legal_domain=p_raw.get("legal_domain", "İş Hukuku"),
        authority=p_raw.get("authority", ""),
        case_file_no=p_raw.get("case_file_no"),
        parties=dict(p_raw.get("parties", {})),
        full_text=p_raw.get("full_text", ""),
        sections=dict(p_raw.get("sections", {})),
        claims=[LegalClaimItem(**c) for c in p_raw.get("claims", [])],
        statute_refs=[StatuteReference(**s) for s in p_raw.get("statute_refs", [])],
        precedent_citations=[PrecedentCitation(**pc) for pc in p_raw.get("precedent_citations", [])],
        procedural_checks=[ProceduralCheckItem(**chk) for chk in p_raw.get("procedural_checks", [])],
        neticei_talep=p_raw.get("neticei_talep", ""),
    )

    def _build_fp(d_fp: Dict[str, Any]) -> FetchedPrecedent:
        cp = dict(d_fp)
        cp.pop("citation_label", None)
        return FetchedPrecedent(**cp)

    def _build_st(d_st: Dict[str, Any]) -> FetchedStatute:
        cp = dict(d_st)
        cp.pop("full_label", None)
        return FetchedStatute(**cp)

    cited_map = {k: _build_fp(v) for k, v in data.get("cited_map", {}).items()}
    claim_precs_map = {
        k: [_build_fp(item) for item in plist]
        for k, plist in data.get("claim_precs_map", {}).items()
    }
    statutes_map = {k: _build_st(v) for k, v in data.get("statutes_map", {}).items()}

    results: List[LegalClaimVerificationResult] = []
    for r_dict in data.get("verification_results", []):
        rc = dict(r_dict)
        rc["supporting_precedents"] = [_build_fp(p) for p in rc.get("supporting_precedents", [])]
        rc["contradicting_precedents"] = [_build_fp(p) for p in rc.get("contradicting_precedents", [])]
        rc["applicable_statutes"] = [_build_st(s) for s in rc.get("applicable_statutes", [])]
        rc["top_chunks"] = [LegalEvidenceChunk(**ch) for ch in rc.get("top_chunks", [])]
        results.append(LegalClaimVerificationResult(**rc))

    return parsed_doc, cited_map, claim_precs_map, statutes_map, results, lawyer_mode, saved_at


def _save_mode_state(
    mode_key: str,
    parsed_doc: Optional[ParsedLegalDocument],
    cited_map: Optional[Dict[str, FetchedPrecedent]] = None,
    claim_precs_map: Optional[Dict[str, List[FetchedPrecedent]]] = None,
    statutes_map: Optional[Dict[str, FetchedStatute]] = None,
    verification_results: Optional[List[LegalClaimVerificationResult]] = None,
    docx_bytes: Optional[bytes] = None,
    notice_msg: Optional[str] = None,
    selected_indices: Optional[set[int]] = None,
) -> None:
    st.session_state[f"doc_{mode_key}"] = parsed_doc
    if cited_map is not None:
        st.session_state[f"cited_{mode_key}"] = dict(cited_map)
    elif f"cited_{mode_key}" not in st.session_state:
        st.session_state[f"cited_{mode_key}"] = {}

    if claim_precs_map is not None:
        st.session_state[f"cprecs_{mode_key}"] = dict(claim_precs_map)
    elif f"cprecs_{mode_key}" not in st.session_state:
        st.session_state[f"cprecs_{mode_key}"] = {}

    if statutes_map is not None:
        st.session_state[f"smap_{mode_key}"] = dict(statutes_map)
    elif f"smap_{mode_key}" not in st.session_state:
        st.session_state[f"smap_{mode_key}"] = {}

    if verification_results is not None:
        st.session_state[f"res_{mode_key}"] = list(verification_results)
    elif f"res_{mode_key}" not in st.session_state:
        st.session_state[f"res_{mode_key}"] = []

    if docx_bytes is not None:
        st.session_state[f"docx_bytes_{mode_key}"] = docx_bytes

    if notice_msg is not None:
        st.session_state[f"notice_{mode_key}"] = notice_msg

    if selected_indices is not None:
        st.session_state[f"sel_{mode_key}"] = set(selected_indices)
    elif parsed_doc is not None and f"sel_{mode_key}" not in st.session_state:
        st.session_state[f"sel_{mode_key}"] = set(range(1, len(parsed_doc.claims) + 1))


ALL_FILTER_KEYS = ["LEHE", "CELISKI", "SAHTE", "USUL"]


def _result_category_code(r_obj: LegalClaimVerificationResult) -> str:
    return get_legal_verdict_info(r_obj.verdict)["code"]


def activate_loaded_session(
    parsed_doc: ParsedLegalDocument,
    cited_map: Dict[str, FetchedPrecedent],
    claim_precs_map: Dict[str, List[FetchedPrecedent]],
    statutes_map: Dict[str, FetchedStatute],
    verification_results: List[LegalClaimVerificationResult],
    notice_msg: str,
    target_mode: Optional[str] = None,
) -> None:
    mode_k = target_mode or st.session_state.get("active_entry_mode", "upload")
    sel_default = set(range(1, len(parsed_doc.claims) + 1))
    _save_mode_state(
        mode_key=mode_k,
        parsed_doc=parsed_doc,
        cited_map=cited_map,
        claim_precs_map=claim_precs_map,
        statutes_map=statutes_map,
        verification_results=verification_results,
        notice_msg=notice_msg,
        selected_indices=sel_default,
    )
    st.session_state["current_parsed_doc"] = parsed_doc
    st.session_state["selected_claim_indices"] = set(sel_default)
    st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
    for prefix in ("lf1", "lf4"):
        st.session_state[f"{prefix}_ALL"] = True
        for k in ALL_FILTER_KEYS:
            st.session_state[f"{prefix}_{k}"] = False


def sync_active_mode_globals() -> Tuple[
    str,
    Optional[ParsedLegalDocument],
    Dict[str, FetchedPrecedent],
    Dict[str, List[FetchedPrecedent]],
    Dict[str, FetchedStatute],
    List[LegalClaimVerificationResult],
    Optional[bytes],
    str,
]:
    cur_mk = st.session_state.get("active_entry_mode", "upload")
    p_doc: Optional[ParsedLegalDocument] = st.session_state.get(f"doc_{cur_mk}")
    c_map: Dict[str, FetchedPrecedent] = dict(st.session_state.get(f"cited_{cur_mk}", {}))
    cp_map: Dict[str, List[FetchedPrecedent]] = dict(st.session_state.get(f"cprecs_{cur_mk}", {}))
    s_map: Dict[str, FetchedStatute] = dict(st.session_state.get(f"smap_{cur_mk}", {}))
    v_res: List[LegalClaimVerificationResult] = list(st.session_state.get(f"res_{cur_mk}", []))
    d_bytes: Optional[bytes] = st.session_state.get(f"docx_bytes_{cur_mk}")
    notice: str = st.session_state.get(f"notice_{cur_mk}", "") or ""

    st.session_state["current_parsed_doc"] = p_doc
    st.session_state["current_cited_map"] = c_map
    st.session_state["current_cprecs_map"] = cp_map
    st.session_state["current_smap"] = s_map
    st.session_state["current_verification_results"] = v_res
    st.session_state["current_docx_bytes"] = d_bytes
    return cur_mk, p_doc, c_map, cp_map, s_map, v_res, d_bytes, notice


def run_legal_verification_pipeline(
    parsed_doc: ParsedLegalDocument,
    claims_to_check: List[LegalClaimItem],
    selected_model: str,
    use_llm: bool,
    try_live_api: bool,
    lawyer_mode: str,
    existing_results: Optional[List[LegalClaimVerificationResult]] = None,
) -> Tuple[
    List[LegalClaimVerificationResult],
    Dict[str, FetchedPrecedent],
    Dict[str, List[FetchedPrecedent]],
    Dict[str, FetchedStatute],
]:
    fetcher = get_fetcher()
    verifier = get_verifier(selected_model, use_llm=use_llm)

    prog = st.progress(0, text="1/3: Kanun maddeleri ve yüksek yargı kararları kontrol ediliyor...")

    selected_claim_ids = {c.claim_id for c in claims_to_check}
    cited_map, claim_precs_map, statutes_map = fetcher.fetch_all_for_document(
        parsed_doc=parsed_doc,
        selected_claim_ids=selected_claim_ids,
        try_live_api=try_live_api,
    )

    prog.progress(
        45,
        text="2/3: İddialar emsal yüksek yargı kararlarıyla karşılaştırılıyor...",
    )

    merged_results: List[LegalClaimVerificationResult] = list(existing_results or [])
    total_c = len(claims_to_check)

    for idx_c, claim in enumerate(claims_to_check, start=1):
        prog.progress(
            45 + int((idx_c / max(1, total_c)) * 55),
            text=f"3/3: İnceleniyor [{idx_c}/{total_c}]: Paragraf {claim.paragraph_index}...",
        )
        c_precs = claim_precs_map.get(claim.claim_id, [])
        v_res = verifier.verify_claim(
            claim=claim,
            legal_domain=parsed_doc.legal_domain,
            cited_precedents_map=cited_map,
            claim_precedents=c_precs,
            statutes_map=statutes_map,
            all_citations=parsed_doc.precedent_citations,
            mode=lawyer_mode,
        )
        merged_results = merge_legal_verification_results(parsed_doc.claims, merged_results, [v_res])
        save_legal_session_to_disk(
            parsed_doc=parsed_doc,
            cited_map=cited_map,
            claim_precs_map=claim_precs_map,
            statutes_map=statutes_map,
            verification_results=merged_results,
            lawyer_mode=lawyer_mode,
        )

    prog.progress(100, text="İnceleme tamamlandı.")
    return merged_results, cited_map, claim_precs_map, statutes_map


def go_home() -> None:
    st.session_state["wizard_track"] = "HOME"
    st.rerun()


def start_doc_flow(step: int = 1) -> None:
    st.session_state["wizard_track"] = "DOC_FLOW"
    st.session_state["doc_wizard_step"] = step
    st.rerun()


def start_ai_flow(tool: str = "CHAT") -> None:
    st.session_state["wizard_track"] = "AI_FLOW"
    st.session_state["ai_wizard_tool"] = tool
    st.rerun()


def render_guide_banner(step_badge: str, title: str, desc: str) -> None:
    st.html(
        f"""
        <div class="guide-banner">
            <span class="guide-step-badge">{step_badge}</span>
            <p class="guide-title">{title}</p>
            <p class="guide-desc">{desc}</p>
        </div>
        """
    )


# ===========================================================================
# SOL YAN MENÜ: BAŞLANGIÇTA GİZLİ; SEÇİLDİKTEN SONRA SADECE O AKIŞI GÖSTERİR
# ===========================================================================

cur_mk_init, active_doc_init, _, _, _, active_res_init, _, _ = sync_active_mode_globals()

probe_verifier = LegalRAGVerifier(use_llm=True)
active_ollama = probe_verifier.active_ollama_model
selected_model = active_ollama or PREFERRED_OLLAMA_MODELS[0]
use_llm_flag = bool(active_ollama)
try_live_api_flag = True

if wizard_track != "HOME":
    with st.sidebar:
        st.html(
            """
            <div class="sidebar-brand-card">
                <p class="sidebar-brand-title">⚖️ AVUKAT ASİSTANI</p>
                <p class="sidebar-brand-sub">Dilekçe, İçtihat ve Strateji</p>
            </div>
            """
        )

        if st.button(
            "🏠 Başlangıç Ekranına Dön",
            key="sb_go_home",
            width="stretch",
        ):
            go_home()

        st.divider()

        if wizard_track == "DOC_FLOW":
            has_doc = active_doc_init is not None
            has_res = len(active_res_init) > 0

            # Eğer henüz dosya yüklenmediyse (1. Adımdaysa) sol menüde tek başına "1. Dosya Yükle" butonu kalabalık yapmasın;
            # dosya yüklendikten sonra adımlar arası geçiş butonları açılsın.
            if has_doc:
                st.caption("📄 İNCELEME ADIMLARI")
                doc_steps_meta = [
                    (1, "1. Dosya & Amaç Seçimi", True),
                    (2, "2. Usul & İçtihat Kontrolü", has_doc),
                    (3, "3. İnceleme Sonuçları", has_res),
                    (4, "4. Resmi Dilekçe Yazdır", has_res),
                    (5, "5. Soru Sor & Rapor İndir", has_res),
                ]
                for s_num, s_label, is_unlocked in doc_steps_meta:
                    if not is_unlocked:
                        continue
                    is_cur = doc_step == s_num
                    prefix = "●" if is_cur else "✅"
                    if st.button(
                        f"{prefix} {s_label}",
                        key=f"sb_doc_step_{s_num}",
                        type="primary" if is_cur else "secondary",
                        width="stretch",
                    ):
                        start_doc_flow(step=s_num)
                st.divider()

        elif wizard_track == "AI_FLOW":
            st.caption("💬 HUKUK ASİSTANI")
            ai_tools_meta = [
                ("CHAT", "💬 Hukuk Asistanına Sor"),
                ("SEARCH", "🔎 Emsal Karar & Kanun Bul"),
                ("DRAFT", "📝 Sıfırdan Dilekçe Yazdır"),
            ]
            for t_code, t_label in ai_tools_meta:
                is_cur_t = ai_tool == t_code
                prefix = "●" if is_cur_t else "▸"
                if st.button(
                    f"{prefix} {t_label}",
                    key=f"sb_ai_tool_{t_code}",
                    type="primary" if is_cur_t else "secondary",
                    width="stretch",
                ):
                    start_ai_flow(tool=t_code)
            st.divider()

        with st.expander("⚙️ Ek Karar PDF & Ayarlar", expanded=False):
            uploaded_ictihat_pdfs = st.file_uploader(
                "Kendi Emsal Karar PDF'leriniz:",
                type=["pdf"],
                accept_multiple_files=True,
            )
            if uploaded_ictihat_pdfs:
                for up_pdf in uploaded_ictihat_pdfs:
                    target_path = USER_ICTIHAT_PDF_DIR / safe_ref_token(up_pdf.name, fallback="karar.pdf")
                    target_path.write_bytes(up_pdf.getvalue())
                st.success(f"{len(uploaded_ictihat_pdfs)} adet PDF eklendi.")

            selected_model = st.selectbox(
                "Yapay Zekâ Modeli:",
                options=PREFERRED_OLLAMA_MODELS,
                index=PREFERRED_OLLAMA_MODELS.index(active_ollama) if active_ollama in PREFERRED_OLLAMA_MODELS else 0,
            )
            use_llm_flag = st.checkbox(
                "Yapay Zekâ Yorum Desteği",
                value=bool(active_ollama),
            )
            try_live_api_flag = st.checkbox(
                "Resmi İçtihat Veritabanı Sorgusu",
                value=True,
            )


# ===========================================================================
# EKRAN 0: İLK KARŞILAMA EKRANI (ALTTA AYRI BUTON YOK; KARTLARIN KENDİSİ DOĞRUDAN TIKLANABİLİR VE UZUN)
# ===========================================================================

if wizard_track == "HOME":
    render_guide_banner(
        step_badge="⚖️ AVUKAT ASİSTANI",
        title="👋 Hoş Geldiniz! Bugün Nasıl Çalışmak İstersiniz?",
        desc="Başlamak için aşağıdaki iki çalışma kartından birinin üzerine tıklayın.",
    )

    st.html('<div class="home-cards-wrapper"></div>')
    col_w1, col_w2 = st.columns(2)

    with col_w1:
        card_1_md = (
            "**📄 Dilekçe ve Dava Dosyası İncele**"
            "Mevcut bir dilekçeyi, iddianameyi veya dava dosyasını yükleyerek hukuki denetim yapın ve cevap hazırlayın.\n"
            "✅ Hatalı veya gerçek dışı Yargıtay karar atıflarını tespit eder\n"
            "✅ Usul, dava şartı, zamanaşımı ve arabuluculuk kontrolü yapar\n"
            "✅ Emsal kararlarla güçlendirilmiş Cevap Dilekçesi (.docx) hazırlar"
        )
        if st.button(card_1_md, key="home_card_doc", width="stretch"):
            start_doc_flow(step=1)

    with col_w2:
        card_2_md = (
            "**💬 Hukuk Asistanına Sor & Dilekçe Yaz**"
            "Dosya yüklemeden doğrudan hukuki sorularınıza yanıt alın, emsal karar arayın veya sıfırdan dilekçe yazdırın.\n"
            "✅ Kanun maddesi ve Yargıtay karar numaralı hukuki soru-cevap\n"
            "✅ Uyuşmazlık konusuna uygun Yargıtay ve Danıştay kararı arama\n"
            "✅ Olay özetinizden mahkemeye hazır resmi Word (.docx) dilekçe"
        )
        if st.button(card_2_md, key="home_card_ai", width="stretch"):
            start_ai_flow(tool="CHAT")


# ===========================================================================
# AKIŞ 1: DİLEKÇE / DAVA DOSYASI İNCELEME SİHİRBAZI (ADIM 1 -> 2 -> 3 -> 4 -> 5)
# ===========================================================================

elif wizard_track == "DOC_FLOW":
    active_lawyer_mode = st.session_state.get("active_lawyer_mode", "MOD_B")
    saved_files = sorted(SESSIONS_DIR.glob("*.analiz.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    # -----------------------------------------------------------------------
    # SİHİRBAZ ADIM 1: AMACINI SEÇ VE DOSYANI YÜKLE (DOĞRUDAN TIKLANABİLİR 2 HOVER KART)
    # -----------------------------------------------------------------------
    if doc_step == 1:
        render_guide_banner(
            step_badge="⚖️ DİLEKÇE & DAVA DOSYASI İNCELEME",
            title="📤 İnceleme Amacınızı Seçin ve Dosyanızı Yükleyin",
            desc="Önce aşağıdaki iki karttan inceleme amacınıza tıklayın, ardından hemen altından dosyanızı seçin.",
        )

        # 1. İnceleme Amacı: Her iki kart da aynı parlaklıkta, başlık <strong> ile ayrı üst blokta
        mc1, mc2 = st.columns(2)
        is_mod_b = active_lawyer_mode == "MOD_B"
        is_mod_a = active_lawyer_mode == "MOD_A"

        with mc1:
            mod_b_md = (
                f"**🛡️ Karşı Tarafın Dilekçesi / İddianame {'  (✅ SEÇİLİ)' if is_mod_b else ''}**"
                "Karşı tarafın iddialarına itiraz etmek, hatalı Yargıtay karar atıflarını yakalamak ve güçlü bir Cevap / Savunma Dilekçesi hazırlamak istiyorum."
            )
            if st.button(
                mod_b_md,
                key="card_pick_mod_b",
                width="stretch",
            ):
                st.session_state["active_lawyer_mode"] = "MOD_B"
                st.rerun()

        with mc2:
            mod_a_md = (
                f"**✍️ Kendi Taslak Dilekçem {'  (✅ SEÇİLİ)' if is_mod_a else ''}**"
                "Kendi hazırladığım dilekçenin usul, dava şartı ve süre kontrollerini yapmak ve iddialarımı lehe Yargıtay kararlarıyla güçlendirmek istiyorum."
            )
            if st.button(
                mod_a_md,
                key="card_pick_mod_a",
                width="stretch",
            ):
                st.session_state["active_lawyer_mode"] = "MOD_A"
                st.rerun()

        st.space("small")

        # 2. Dosya Seçim Kartı
        with st.container(border=True):
            st.markdown("##### 📁 Dilekçe veya Dava Dosyanızı Seçin")
            cur_mk_default = st.session_state.get("active_entry_mode", "upload")
            opt_upload = "📄 Bilgisayarımdan Dosya Yükle (.docx / .pdf / .txt)"
            opt_saved = f"💾 Kayıtlı İncelemeler ({len(saved_files)})"
            opt_demo = "🧪 Hazır Örnek Dilekçe ile Dene"
            default_entry_opt = (
                opt_saved if cur_mk_default == "saved" else (opt_demo if cur_mk_default == "demo" else opt_upload)
            )

            entry_mode = st.segmented_control(
                "Dosya Giriş Yöntemi:",
                options=[opt_upload, opt_saved, opt_demo],
                default=default_entry_opt,
                label_visibility="collapsed",
            )

            if entry_mode and entry_mode.startswith("💾"):
                cur_mode_key = "saved"
            elif entry_mode and entry_mode.startswith("🧪"):
                cur_mode_key = "demo"
            else:
                cur_mode_key = "upload"

            prev_mode_key = st.session_state.get("active_entry_mode")
            if prev_mode_key != cur_mode_key:
                if prev_mode_key is not None and "selected_claim_indices" in st.session_state:
                    st.session_state[f"sel_{prev_mode_key}"] = set(st.session_state["selected_claim_indices"])
                if f"sel_{cur_mode_key}" in st.session_state:
                    st.session_state["selected_claim_indices"] = set(st.session_state[f"sel_{cur_mode_key}"])
                st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                st.session_state["active_entry_mode"] = cur_mode_key

            parser = get_parser()
            uploaded_file = None

            if cur_mode_key == "saved":
                col_s1, col_s2 = st.columns([1.4, 1.0], vertical_alignment="bottom")
                with col_s1:
                    if saved_files:
                        session_labels: Dict[str, Path] = {}
                        for sf in saved_files[:15]:
                            try:
                                meta = json.loads(sf.read_text(encoding="utf-8"))
                                lbl = (
                                    f"{meta.get('filename', sf.stem)} — "
                                    f"{meta.get('verified_count', 0)}/{meta.get('total_claims', '?')} Paragraf "
                                    f"({meta.get('saved_at', '')})"
                                )
                            except Exception:
                                lbl = sf.name
                            session_labels[lbl] = sf

                        sel_c, btn_c = st.columns([2.5, 1.3], vertical_alignment="bottom")
                        with sel_c:
                            chosen_saved_label = st.selectbox(
                                "Kaydedilen incelemeler:",
                                options=list(session_labels.keys()),
                            )
                        with btn_c:
                            if st.button(":material/folder_open: Kaydı Aç ➡️", type="primary", width="stretch"):
                                sf_path = session_labels[chosen_saved_label]
                                p_doc, c_map, cp_map, s_map, v_res, l_mode, s_at = deserialize_legal_session_bytes(
                                    sf_path.read_bytes()
                                )
                                st.session_state["active_lawyer_mode"] = l_mode
                                activate_loaded_session(
                                    parsed_doc=p_doc,
                                    cited_map=c_map,
                                    claim_precs_map=cp_map,
                                    statutes_map=s_map,
                                    verification_results=v_res,
                                    notice_msg="",
                                    target_mode="saved",
                                )
                                start_doc_flow(step=3 if v_res else 2)
                    else:
                        st.caption("Henüz kaydedilmiş bir inceleme bulunmuyor.")

                with col_s2:
                    uploaded_json = st.file_uploader(
                        "Veya `.analiz.json` dosyasını yükleyin:",
                        type=["json"],
                        key="legal_session_json_uploader",
                    )
                    if uploaded_json is not None:
                        sig = f"{uploaded_json.name}_{uploaded_json.size}"
                        if st.session_state.get("last_uploaded_legal_json_sig") != sig:
                            try:
                                p_doc, c_map, cp_map, s_map, v_res, l_mode, s_at = deserialize_legal_session_bytes(
                                    uploaded_json.getvalue()
                                )
                                st.session_state["last_uploaded_legal_json_sig"] = sig
                                st.session_state["active_lawyer_mode"] = l_mode
                                activate_loaded_session(
                                    parsed_doc=p_doc,
                                    cited_map=c_map,
                                    claim_precs_map=cp_map,
                                    statutes_map=s_map,
                                    verification_results=v_res,
                                    notice_msg="",
                                    target_mode="saved",
                                )
                                start_doc_flow(step=3 if v_res else 2)
                            except Exception as exc:
                                st.error(f"Dosya okunamadı: {exc}")
                    else:
                        st.session_state.pop("last_uploaded_legal_json_sig", None)

            elif cur_mode_key == "demo":
                demo_options = {v["title"]: k for k, v in DEMO_PETITIONS.items()}
                dc1, dc2 = st.columns([2.8, 1.3], vertical_alignment="bottom")
                with dc1:
                    chosen_demo_title = st.selectbox(
                        "Örnek dilekçe seçin:",
                        options=list(demo_options.keys()),
                    )
                with dc2:
                    if st.button(":material/play_arrow: Örneği Yükle ve Devam Et ➡️", type="primary", width="stretch"):
                        d_key = demo_options[chosen_demo_title]
                        d_info = DEMO_PETITIONS[d_key]
                        p_demo = parser.parse_text(d_info["text"], filename=d_info["filename"])
                        st.session_state["active_lawyer_mode"] = d_info.get("recommended_mode", "MOD_B")
                        _save_mode_state(
                            mode_key="demo",
                            parsed_doc=p_demo,
                            cited_map={},
                            claim_precs_map={},
                            statutes_map={},
                            verification_results=[],
                            notice_msg="",
                            selected_indices=set(range(1, len(p_demo.claims) + 1)),
                        )
                        st.session_state["selected_claim_indices"] = set(range(1, len(p_demo.claims) + 1))
                        st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                        start_doc_flow(step=2)

            else:
                uploaded_file = st.file_uploader(
                    "Word (.docx), PDF (.pdf) veya Metin (.txt) dosyanızı buraya bırakın:",
                    type=["docx", "pdf", "txt"],
                    key="legal_doc_file_uploader",
                )

        if cur_mode_key == "upload":
            if uploaded_file is not None:
                up_sig = f"{uploaded_file.name}_{uploaded_file.size}"
                if st.session_state.get("last_uploaded_legal_doc_sig") != up_sig:
                    st.session_state["last_uploaded_legal_doc_sig"] = up_sig
                    docx_b = uploaded_file.getvalue() if uploaded_file.name.lower().endswith(".docx") else None
                    if docx_b:
                        st.session_state["docx_bytes_upload"] = docx_b
                    else:
                        st.session_state.pop("docx_bytes_upload", None)

                    auto_file = _session_file_for_doc(uploaded_file.name)
                    if auto_file.exists():
                        try:
                            p_doc, c_map, cp_map, s_map, v_res, l_mode, s_at = deserialize_legal_session_bytes(
                                auto_file.read_bytes()
                            )
                            activate_loaded_session(
                                parsed_doc=p_doc,
                                cited_map=c_map,
                                claim_precs_map=cp_map,
                                statutes_map=s_map,
                                verification_results=v_res,
                                notice_msg="",
                                target_mode="upload",
                            )
                            start_doc_flow(step=3 if v_res else 2)
                        except Exception:
                            p_new = parser.parse_file(uploaded_file.getvalue(), filename=uploaded_file.name)
                            _save_mode_state(
                                mode_key="upload",
                                parsed_doc=p_new,
                                docx_bytes=docx_b,
                                selected_indices=set(range(1, len(p_new.claims) + 1)),
                            )
                            st.session_state["selected_claim_indices"] = set(range(1, len(p_new.claims) + 1))
                            st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                            start_doc_flow(step=2)
                    else:
                        p_new = parser.parse_file(uploaded_file.getvalue(), filename=uploaded_file.name)
                        _save_mode_state(
                            mode_key="upload",
                            parsed_doc=p_new,
                            docx_bytes=docx_b,
                            selected_indices=set(range(1, len(p_new.claims) + 1)),
                        )
                        st.session_state["selected_claim_indices"] = set(range(1, len(p_new.claims) + 1))
                        st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                        start_doc_flow(step=2)
            else:
                st.session_state.pop("last_uploaded_legal_doc_sig", None)

    # -----------------------------------------------------------------------
    # SİHİRBAZ ADIM 2: USUL KONTROLÜ & İDDİA BENTLERİNİ DENETLE
    # -----------------------------------------------------------------------
    elif doc_step == 2:
        cur_mk, parsed_doc, cur_cited, cur_cprecs, cur_smap, cur_res, _, _ = sync_active_mode_globals()

        if parsed_doc is None:
            start_doc_flow(step=1)
        else:
            render_guide_banner(
                step_badge="ADIM 2 — USUL VE İÇTİHAT KONTROLÜ",
                title=f"⚖️ `{parsed_doc.filename}` İncelemeye Hazır",
                desc="Sağdaki mavi butona tıklayarak dilekçedeki iddiaları ve karar numaralarını Yargıtay içtihatlarıyla karşılaştırın.",
            )

            m1, m2, m3, m4 = st.columns(4)
            with m1.container(border=True, height="stretch"):
                st.metric("Hukuk Alanı", parsed_doc.legal_domain)
                st.caption(f"Tür: **{parsed_doc.document_type}**")
            with m2.container(border=True, height="stretch"):
                st.metric("İddia / Savunma Paragrafı", len(parsed_doc.claims))
                st.caption(f"{parsed_doc.page_count} sayfa")
            with m3.container(border=True, height="stretch"):
                st.metric("Kanun Maddesi", len(parsed_doc.statute_refs))
                st_preview = ", ".join(dict.fromkeys(f"{s.law_code} m.{s.article}" for s in parsed_doc.statute_refs[:4]))
                st.caption(st_preview or "Tespit edilmedi")
            with m4.container(border=True, height="stretch"):
                st.metric("Yüksek Yargı Kararı", len(parsed_doc.precedent_citations))
                st.caption("Belirtilen emsal kararlar")

            with st.expander("🏛️ Mahkeme Bilgisi, Taraflar ve Usul Ön Kontrolü", expanded=True):
                parties_inline = " | ".join(f"**{k}:** {v}" for k, v in parsed_doc.parties.items()) or "Metin içinde"
                st.markdown(
                    f"🏛️ **Makam:** `{parsed_doc.authority}` &nbsp;|&nbsp; "
                    f"📁 **Dosya No:** `{parsed_doc.case_file_no or 'Yeni Başvuru'}` &nbsp;|&nbsp; "
                    f"👥 **Taraflar:** {parties_inline}"
                )
                for pc in parsed_doc.procedural_checks:
                    if pc.status == "ok":
                        st.success(f"**✅ {pc.check_title}:** {pc.detail}")
                    elif pc.status == "warning":
                        st.warning(f"**⚠️ {pc.check_title}:** {pc.detail} — *Öneri:* {pc.recommendation}")
                    else:
                        st.error(f"**🚨 {pc.check_title}:** {pc.detail} — *Öneri:* {pc.recommendation}")

            total_claims_n = len(parsed_doc.claims)
            if f"sel_{cur_mk}" not in st.session_state:
                st.session_state[f"sel_{cur_mk}"] = set(range(1, total_claims_n + 1))
            st.session_state["selected_claim_indices"] = set(st.session_state[f"sel_{cur_mk}"])

            def _apply_range_selection() -> None:
                s_val = int(st.session_state.get("range_start_num", 1))
                e_val = int(st.session_state.get("range_end_num", total_claims_n))
                low, high = min(s_val, e_val), max(s_val, e_val)
                new_sel = set(range(max(1, low), min(total_claims_n, high) + 1))
                st.session_state["selected_claim_indices"] = new_sel
                st.session_state[f"sel_{cur_mk}"] = set(new_sel)
                st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1

            rc1, rc2, rc3, rc4, rc5 = st.columns([0.9, 0.9, 1.0, 1.1, 2.1], vertical_alignment="bottom")
            with rc1:
                st.number_input(
                    "Başlangıç No:",
                    min_value=1,
                    max_value=max(1, total_claims_n),
                    value=1,
                    step=1,
                    key="range_start_num",
                    on_change=_apply_range_selection,
                )
            with rc2:
                st.number_input(
                    "Bitiş No:",
                    min_value=1,
                    max_value=max(1, total_claims_n),
                    value=max(1, total_claims_n),
                    step=1,
                    key="range_end_num",
                    on_change=_apply_range_selection,
                )
            with rc3:
                if st.button(":material/select_all: Tümünü Seç", width="stretch"):
                    all_set = set(range(1, total_claims_n + 1))
                    st.session_state["selected_claim_indices"] = all_set
                    st.session_state[f"sel_{cur_mk}"] = set(all_set)
                    st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                    st.rerun()
            with rc4:
                if st.button(":material/deselect: Seçilenleri Temizle", width="stretch"):
                    st.session_state["selected_claim_indices"] = set()
                    st.session_state[f"sel_{cur_mk}"] = set()
                    st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                    st.rerun()

            verified_by_id = {r.claim_id: r for r in cur_res}
            selected_set: set[int] = set(st.session_state.get("selected_claim_indices", set()))

            table_rows: List[Dict[str, Any]] = []
            for idx_cl, cl in enumerate(parsed_doc.claims, start=1):
                existing_r = verified_by_id.get(cl.claim_id)
                status_lbl = (
                    get_legal_verdict_info(existing_r.verdict)["short_label"]
                    if existing_r
                    else "⏳ İncelemeye Hazır"
                )
                refs_combined = ", ".join(cl.related_statutes + cl.related_precedents) or "-"
                table_rows.append(
                    {
                        "Seç": idx_cl in selected_set,
                        "No": idx_cl,
                        "Bölüm": cl.section_name,
                        "Tür": cl.claim_category,
                        "Durum": status_lbl,
                        "Kanun / Karar Atfı": refs_combined,
                        "Dilekçe Paragrafı": cl.claim_text,
                    }
                )

            df_claims = pd.DataFrame(table_rows)
            editor_key = f"claims_editor_{cur_mk}_{st.session_state.get('editor_ver', 0)}"
            edited_df = st.data_editor(
                df_claims,
                key=editor_key,
                hide_index=True,
                width="stretch",
                row_height=50,
                disabled=[
                    "No",
                    "Bölüm",
                    "Tür",
                    "Durum",
                    "Kanun / Karar Atfı",
                    "Dilekçe Paragrafı",
                ],
                column_config={
                    "Seç": st.column_config.CheckboxColumn("Seç", width="small"),
                    "No": st.column_config.NumberColumn("No", width="small"),
                    "Bölüm": st.column_config.TextColumn("Bölüm", width="medium"),
                    "Tür": st.column_config.TextColumn("Tür", width="small"),
                    "Durum": st.column_config.TextColumn("Durum", width="medium"),
                    "Kanun / Karar Atfı": st.column_config.TextColumn("Kanun / Karar Atfı", width="medium"),
                    "Dilekçe Paragrafı": st.column_config.TextColumn(
                        "Dilekçe Paragrafı",
                        width="large",
                    ),
                },
            )

            current_checked_indices = {
                int(row["No"]) for _, row in edited_df.iterrows() if bool(row["Seç"])
            }
            st.session_state["selected_claim_indices"] = current_checked_indices
            st.session_state[f"sel_{cur_mk}"] = set(current_checked_indices)

            with rc5:
                run_btn = st.button(
                    f":material/gavel: Seçilenleri İncele ve Sonuçlara Geç ({len(current_checked_indices)}) ➡️",
                    type="primary",
                    width="stretch",
                    disabled=len(current_checked_indices) == 0,
                )

            if run_btn and current_checked_indices:
                claims_to_run = [
                    cl
                    for i_cl, cl in enumerate(parsed_doc.claims, start=1)
                    if i_cl in current_checked_indices
                ]
                new_merged, new_cited, new_cprecs, new_smap = run_legal_verification_pipeline(
                    parsed_doc=parsed_doc,
                    claims_to_check=claims_to_run,
                    selected_model=selected_model,
                    use_llm=use_llm_flag,
                    try_live_api=try_live_api_flag,
                    lawyer_mode=active_lawyer_mode,
                    existing_results=cur_res,
                )
                _save_mode_state(
                    mode_key=cur_mk,
                    parsed_doc=parsed_doc,
                    cited_map=new_cited,
                    claim_precs_map=new_cprecs,
                    statutes_map=new_smap,
                    verification_results=new_merged,
                    notice_msg="",
                    selected_indices=current_checked_indices,
                )
                st.session_state["editor_ver"] = st.session_state.get("editor_ver", 0) + 1
                start_doc_flow(step=3)

    # -----------------------------------------------------------------------
    # SİHİRBAZ ADIM 3: İNCELEME SONUÇLARI
    # -----------------------------------------------------------------------
    elif doc_step == 3:
        cur_mk, parsed_doc, _, _, cur_smap, cur_res, _, _ = sync_active_mode_globals()

        if parsed_doc is None or not cur_res:
            start_doc_flow(step=2 if parsed_doc else 1)
        else:
            render_guide_banner(
                step_badge="ADIM 3 — İNCELEME SONUÇLARI",
                title=f"📊 `{parsed_doc.filename}` Hukuki İnceleme Raporu",
                desc="Her paragraf için bulunan Yargıtay kararlarını ve önerilen dilekçe metinlerini aşağıda inceleyebilir, sayfa sonundaki butonla Resmi Dilekçe Yazımına geçebilirsiniz.",
            )

            verifier_obj = get_verifier(selected_model, use_llm=use_llm_flag)
            exec_summary: ExecutiveLegalSummary = verifier_obj.generate_executive_legal_summary(
                parsed_doc=parsed_doc,
                verification_results=cur_res,
                statutes_map=cur_smap,
                mode=active_lawyer_mode,
            )

            counts = {k: 0 for k in ALL_FILTER_KEYS}
            for r_it in cur_res:
                counts[_result_category_code(r_it)] += 1

            k1, k2, k3, k4 = st.columns(4)
            with k1.container(border=True, height="stretch"):
                st.metric("✅ Emsal Kararla Uyumlu", counts["LEHE"])
            with k2.container(border=True, height="stretch"):
                st.metric("❌ İçtihatla Çelişen", counts["CELISKI"])
            with k3.container(border=True, height="stretch"):
                st.metric("🚨 Geçersiz Karar Atfı", counts["SAHTE"])
            with k4.container(border=True, height="stretch"):
                st.metric("⚠️ Usul & İspat Uyarısı", counts["USUL"])

            with st.expander(":material/summarize: Dosya Özeti ve Strateji Yol Haritası", expanded=True):
                st.markdown(f"**📋 Uyuşmazlık Özeti:**  \n{exec_summary.dispute_summary}")
                sc1, sc2 = st.columns(2)
                with sc1:
                    st.markdown("**🚨 Tespit Edilen Riskler ve Hatalı Atıflar:**")
                    for rk in exec_summary.critical_risks_and_hallucinations:
                        st.markdown(f"- {rk}")
                with sc2:
                    st.markdown("**🧭 Önerilen Hukuki Strateji:**")
                    for rm in exec_summary.strategic_roadmap:
                        st.markdown(f"- {rm}")

            if "lf1_ALL" not in st.session_state:
                st.session_state["lf1_ALL"] = True
                for fk in ALL_FILTER_KEYS:
                    st.session_state[f"lf1_{fk}"] = False

            def _on_all_filter_toggle(prefix: str) -> None:
                if st.session_state.get(f"{prefix}_ALL"):
                    for fk in ALL_FILTER_KEYS:
                        st.session_state[f"{prefix}_{fk}"] = False

            def _on_cat_filter_toggle(prefix: str) -> None:
                if any(st.session_state.get(f"{prefix}_{fk}") for fk in ALL_FILTER_KEYS):
                    st.session_state[f"{prefix}_ALL"] = False
                else:
                    st.session_state[f"{prefix}_ALL"] = True

            fc_all, fc1, fc2, fc3, fc4 = st.columns(5)
            with fc_all:
                st.checkbox(
                    f"📋 Tümünü Göster ({len(cur_res)})",
                    key="lf1_ALL",
                    on_change=_on_all_filter_toggle,
                    args=("lf1",),
                )
            with fc1:
                st.checkbox(
                    f"✅ Uyumlu ({counts['LEHE']})",
                    key="lf1_LEHE",
                    on_change=_on_cat_filter_toggle,
                    args=("lf1",),
                )
            with fc2:
                st.checkbox(
                    f"❌ Çelişen ({counts['CELISKI']})",
                    key="lf1_CELISKI",
                    on_change=_on_cat_filter_toggle,
                    args=("lf1",),
                )
            with fc3:
                st.checkbox(
                    f"🚨 Geçersiz Atıf ({counts['SAHTE']})",
                    key="lf1_SAHTE",
                    on_change=_on_cat_filter_toggle,
                    args=("lf1",),
                )
            with fc4:
                st.checkbox(
                    f"⚠️ Usul / İspat ({counts['USUL']})",
                    key="lf1_USUL",
                    on_change=_on_cat_filter_toggle,
                    args=("lf1",),
                )

            active_cats = {fk for fk in ALL_FILTER_KEYS if st.session_state.get(f"lf1_{fk}")}
            filtered_results = (
                cur_res
                if (st.session_state.get("lf1_ALL") or not active_cats)
                else [r for r in cur_res if _result_category_code(r) in active_cats]
            )

            for r_item in filtered_results:
                v_info = get_legal_verdict_info(r_item.verdict)
                exp_title = (
                    f"{v_info['short_label']} — Paragraf {r_item.paragraph_index} ({r_item.claim_category}) "
                    f"| Karar: {r_item.best_precedent_label}"
                )
                with st.expander(exp_title, expanded=(v_info["group"] == "error")):
                    st.markdown(f"**📄 İncelenen Dilekçe Paragrafı:**  \n> {r_item.claim_text}")
                    if r_item.hallucination_warnings:
                        for hw in r_item.hallucination_warnings:
                            st.error(hw)

                    st.markdown(f"**⚖️ Hukuki Değerlendirme:**  \n{r_item.legal_analysis}")
                    st.info(f"**🧭 Avukat Tavsiyesi:**  \n{r_item.lawyer_action_advice}")

                    st.markdown("**✍️ Dilekçenizde Kullanabileceğiniz Örnek Paragraf:**")
                    st.code(r_item.draft_paragraph_suggestion, language="markdown")

                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        st.markdown(f"**🏛️ Emsal Karar Özeti (`{r_item.best_precedent_label}`):**")
                        st.caption(r_item.best_evidence_text)
                    with d_col2:
                        st.markdown("**📜 İspat ve Usul Notu:**")
                        st.caption(r_item.proof_and_procedure_note)

            st.space("small")
            if st.button(
                "✍️ Sonraki Adım: Bu Dosyaya Resmi Cevap / Dilekçe Yazdır (.docx) ➡️",
                type="primary",
                width="stretch",
            ):
                start_doc_flow(step=4)

    # -----------------------------------------------------------------------
    # SİHİRBAZ ADIM 4: YÜKLÜ DOSYAYA RESMİ CEVAP / DİLEKÇE YAZDIR
    # -----------------------------------------------------------------------
    elif doc_step == 4:
        drafter = get_drafter()
        cur_mk, active_doc_t2, _, _, active_smap_t2, active_res_t2, _, _ = sync_active_mode_globals()

        if active_doc_t2 is None or not active_res_t2:
            start_doc_flow(step=2 if active_doc_t2 else 1)
        else:
            render_guide_banner(
                step_badge="ADIM 4 — RESMİ DİLEKÇE YAZIMI",
                title=f"✍️ `{active_doc_t2.filename}` İçin Resmi Dilekçe Oluşturun",
                desc="İnceleme sonuçlarına ve emsal Yargıtay kararlarına dayalı tam metin resmi Word (.docx) dilekçenizi oluşturup indirebilirsiniz.",
            )

            with st.container(border=True):
                p_col1, p_col2 = st.columns([2.2, 1.2])
                with p_col1:
                    extra_inst = st.text_input(
                        "Eklemek istediğiniz özel bir beyan veya not varsa yazın (isteğe bağlı):",
                        placeholder="Örn: Zamanaşımı itirazını ve arabuluculuk şartını özellikle vurgula...",
                    )
                with p_col2:
                    lawyer_sig_name = st.text_input(
                        "İmza Bloğundaki Avukat Adı:",
                        value="Av. Batuhan Özmen",
                    )

                if st.button(
                    f":material/auto_awesome: Resmi Dilekçeyi ve Strateji Raporunu Oluştur",
                    type="primary",
                    width="stretch",
                ):
                    pkg = drafter.draft_from_verified_document(
                        parsed_doc=active_doc_t2,
                        verification_results=active_res_t2,
                        statutes_map=active_smap_t2,
                        mode=active_lawyer_mode,
                        lawyer_name=lawyer_sig_name,
                        extra_lawyer_instructions=extra_inst,
                    )
                    st.session_state["generated_petition_package"] = pkg

            gen_pkg: Optional[GeneratedPetitionPackage] = st.session_state.get("generated_petition_package")
            if gen_pkg is not None:
                st.success(f"✅ **{gen_pkg.title}** hazırlandı.")

                dl_c1, dl_c2 = st.columns(2)
                with dl_c1:
                    docx_petition_bytes = drafter.export_generated_petition_docx(gen_pkg)
                    st.download_button(
                        label=":material/download: Resmi Dilekçeyi Word (.docx) Olarak İndir",
                        data=docx_petition_bytes,
                        file_name=f"Resmi_Dilekce_{safe_ref_token(gen_pkg.petition_type)}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary",
                        width="stretch",
                    )
                with dl_c2:
                    st.download_button(
                        label=":material/description: Dilekçe Metnini (.txt) Olarak İndir",
                        data=gen_pkg.full_petition_text.encode("utf-8"),
                        file_name=f"Resmi_Dilekce_{safe_ref_token(gen_pkg.petition_type)}.txt",
                        mime="text/plain",
                        width="stretch",
                    )

                p_left, p_right = st.columns([1.35, 1.0])
                with p_left:
                    with st.container(border=True):
                        st.markdown("#### 📜 Resmi Dilekçe Metni")
                        st.text_area(
                            "Resmi Dilekçe Metni:",
                            value=gen_pkg.full_petition_text,
                            height=500,
                            label_visibility="collapsed",
                        )
                with p_right:
                    with st.container(border=True):
                        st.markdown("#### 👨‍⚖️ Hukuki Strateji Gerekçeleri")
                        for idx_s, s_item in enumerate(gen_pkg.strategy_report, start=1):
                            st.markdown(f"**{idx_s}. {s_item.section_title}**")
                            st.caption(f"• **Gerekçe:** {s_item.why_this_strategy}")
                            if s_item.used_precedents:
                                st.caption(f"• **Emsal Kararlar:** {', '.join(s_item.used_precedents)}")
                            if s_item.evidence_to_attach:
                                st.caption(f"• **Eklenecek Belge:** {s_item.evidence_to_attach}")
                            st.divider()

                        st.markdown("**📎 Dilekçe Ekleri Kontrol Listesi:**")
                        for ev_item in gen_pkg.evidence_checklist:
                            st.caption(f"☑️ {ev_item}")

            st.space("small")
            if st.button(
                "💬 Sonraki Adım: Dosya Hakkında Soru Sor & İnceleme Raporlarını İndir ➡️",
                type="primary",
                width="stretch",
            ):
                start_doc_flow(step=5)

    # -----------------------------------------------------------------------
    # SİHİRBAZ ADIM 5: DOSYAYA SORU SOR & RAPOR İNDİR
    # -----------------------------------------------------------------------
    elif doc_step == 5:
        cur_mk, active_doc_t4, active_cited_t4, active_cprecs_t4, active_smap_t4, active_res_t4, active_docx_t4, _ = (
            sync_active_mode_globals()
        )

        if active_doc_t4 is None or not active_res_t4:
            start_doc_flow(step=2 if active_doc_t4 else 1)
        else:
            render_guide_banner(
                step_badge="ADIM 5 — SORU-CEVAP VE RAPOR İNDİRME",
                title=f"💬 `{active_doc_t4.filename}` — Rapor İndirme ve Soru-Cevap",
                desc="İnceleme notlu Word (.docx) dosyanızı ve Excel tablonuzu indirebilir, dosya hakkında merak ettiklerinizi asistana sorabilirsiniz.",
            )

            drafter_t4 = get_drafter()
            annotated_docx_bytes = drafter_t4.build_annotated_review_docx(
                parsed_doc=active_doc_t4,
                verification_results=active_res_t4,
                original_docx_bytes=active_docx_t4,
                mode=active_lawyer_mode,
            )

            export_rows: List[Dict[str, Any]] = []
            for r_ex in active_res_t4:
                v_inf = get_legal_verdict_info(r_ex.verdict)
                export_rows.append(
                    {
                        "Paragraf No": r_ex.paragraph_index,
                        "Bölüm": r_ex.section_name,
                        "Tür": r_ex.claim_category,
                        "İnceleme Sonucu": v_inf["short_label"],
                        "Emsal Yüksek Yargı Kararı": r_ex.best_precedent_label,
                        "Dilekçe Paragrafı": r_ex.claim_text,
                        "Hukuki Değerlendirme": r_ex.legal_analysis,
                        "Avukat Tavsiyesi": r_ex.lawyer_action_advice,
                        "Önerilen Dilekçe Paragrafı": r_ex.draft_paragraph_suggestion,
                    }
                )
            df_export = pd.DataFrame(export_rows)

            with st.container(border=True):
                st.markdown("##### 📥 1. İnceleme Dosyalarını İndirin")
                b_dl1, b_dl2, b_dl3 = st.columns(3)
                with b_dl1:
                    st.download_button(
                        label=":material/rate_review: İnceleme Notlu Word (.docx) İndir",
                        data=annotated_docx_bytes,
                        file_name=f"{Path(active_doc_t4.filename).stem}_Inceleme_Notlu.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary",
                        width="stretch",
                    )
                with b_dl2:
                    csv_bytes = df_export.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label=":material/table_view: İnceleme Tablosunu İndir (Excel / CSV)",
                        data=csv_bytes,
                        file_name=f"{Path(active_doc_t4.filename).stem}_Inceleme_Tablosu.csv",
                        mime="text/csv",
                        width="stretch",
                    )
                with b_dl3:
                    session_json_bytes = serialize_legal_session_bytes(
                        parsed_doc=active_doc_t4,
                        cited_map=active_cited_t4,
                        claim_precs_map=active_cprecs_t4,
                        statutes_map=active_smap_t4,
                        verification_results=active_res_t4,
                        lawyer_mode=active_lawyer_mode,
                    )
                    st.download_button(
                        label=":material/save: Çalışma Kaydını İndir (.json)",
                        data=session_json_bytes,
                        file_name=f"{Path(active_doc_t4.filename).stem}.analiz.json",
                        mime="application/json",
                        width="stretch",
                    )

            st.markdown("##### 💬 2. Dosya Hakkında Hukuk Asistanına Soru Sorun")
            chat_assistant = LegalChatAssistant(
                fetcher=get_fetcher(),
                verifier=get_verifier(selected_model, use_llm=use_llm_flag),
                use_llm=use_llm_flag,
            )

            quick_qs = chat_assistant.get_quick_questions(active_doc_t4, mode=active_lawyer_mode)
            with st.container(border=True):
                st.caption("⚡ Hızlı sorular:")
                q_cols = st.columns(2)
                clicked_quick_q: Optional[str] = None
                for idx_qq, qq_text in enumerate(quick_qs[:4]):
                    with q_cols[idx_qq % 2]:
                        if st.button(qq_text, key=f"doc_quick_q_{idx_qq}", width="stretch"):
                            clicked_quick_q = qq_text

            user_q_input = st.chat_input("Dosya veya emsal kararlar hakkında sorunuzu yazın...")
            final_question = clicked_quick_q or user_q_input

            if "legal_chat_history" not in st.session_state:
                st.session_state["legal_chat_history"] = []

            if final_question:
                chat_resp: LegalChatResponse = chat_assistant.answer_question(
                    question=final_question,
                    parsed_doc=active_doc_t4,
                    verification_results=active_res_t4,
                    cited_precedents_map=active_cited_t4,
                    claim_precedents_map=active_cprecs_t4,
                    statutes_map=active_smap_t4,
                    generated_package=st.session_state.get("generated_petition_package"),
                    mode=active_lawyer_mode,
                )
                st.session_state["legal_chat_history"].append(chat_resp)

            for msg_item in st.session_state["legal_chat_history"]:
                with st.chat_message("user"):
                    st.write(msg_item.question)
                with st.chat_message("assistant"):
                    st.markdown(msg_item.answer_markdown)
                    if msg_item.citations:
                        with st.expander(f"📚 Dayanak Karar ve Kanun Maddeleri ({len(msg_item.citations)})"):
                            for b_cit in msg_item.citations:
                                st.markdown(f"- **{b_cit.source_type} — `{b_cit.reference_code}`:** {b_cit.quote_snippet[:350]}")

            with st.expander("📋 Tüm İnceleme Tablosunu Gör", expanded=False):
                st.dataframe(
                    df_export,
                    hide_index=True,
                    width="stretch",
                    row_height=50,
                    column_config={
                        "Dilekçe Paragrafı": st.column_config.TextColumn(
                            "Dilekçe Paragrafı", width="large"
                        ),
                        "Önerilen Dilekçe Paragrafı": st.column_config.TextColumn(
                            "Önerilen Dilekçe Paragrafı", width="large"
                        ),
                    },
                )


# ===========================================================================
# AKIŞ 2: DOSYASIZ DOĞRUDAN HUKUK ASİSTANI (SOHBET / EMSAL BUL / DİLEKÇE YAZ)
# ===========================================================================

elif wizard_track == "AI_FLOW":
    cur_mk, active_doc_ai, active_cited_ai, active_cprecs_ai, active_smap_ai, active_res_ai, _, _ = (
        sync_active_mode_globals()
    )

    if ai_tool == "CHAT":
        render_guide_banner(
            step_badge="HUKUK ASİSTANI",
            title="💬 Hukuk Asistanına Sorunuzu Yazın",
            desc="Sorularınız ilgili kanun maddeleri ve Yargıtay karar numaralarıyla yanıtlanır. Emsal karar aramak veya sıfırdan dilekçe yazdırmak için sol menüyü kullanabilirsiniz.",
        )

        chat_assistant = LegalChatAssistant(
            fetcher=get_fetcher(),
            verifier=get_verifier(selected_model, use_llm=use_llm_flag),
            use_llm=use_llm_flag,
        )

        quick_qs = chat_assistant.get_quick_questions(active_doc_ai, mode="MOD_B")
        with st.container(border=True):
            st.caption("⚡ Örnek sorular:")
            q_cols = st.columns(2)
            clicked_quick_q: Optional[str] = None
            for idx_qq, qq_text in enumerate(quick_qs[:4]):
                with q_cols[idx_qq % 2]:
                    if st.button(qq_text, key=f"ai_quick_q_{idx_qq}", width="stretch"):
                        clicked_quick_q = qq_text

        user_q_input = st.chat_input("Hukuki sorunuzu buraya yazın...")
        final_question = clicked_quick_q or user_q_input

        if "legal_chat_history" not in st.session_state:
            st.session_state["legal_chat_history"] = []

        if final_question:
            chat_resp = chat_assistant.answer_question(
                question=final_question,
                parsed_doc=active_doc_ai,
                verification_results=active_res_ai,
                cited_precedents_map=active_cited_ai,
                claim_precedents_map=active_cprecs_ai,
                statutes_map=active_smap_ai,
                generated_package=st.session_state.get("generated_petition_package"),
                mode="MOD_B",
            )
            st.session_state["legal_chat_history"].append(chat_resp)

        for msg_item in st.session_state["legal_chat_history"]:
            with st.chat_message("user"):
                st.write(msg_item.question)
            with st.chat_message("assistant"):
                st.markdown(msg_item.answer_markdown)
                if msg_item.citations:
                    with st.expander(f"📚 Dayanak Karar ve Kanun Maddeleri ({len(msg_item.citations)})"):
                        for b_cit in msg_item.citations:
                            st.markdown(f"- **{b_cit.source_type} — `{b_cit.reference_code}`:** {b_cit.quote_snippet[:350]}")

    elif ai_tool == "SEARCH":
        render_guide_banner(
            step_badge="EMSAL KARAR & KANUN ARAMA",
            title="🔎 Uyuşmazlık Konusuna Göre Emsal Karar Bulun",
            desc="Aradığınız hukuki konuyu veya kanun maddesini yazarak ilgili Yargıtay kararlarına ve kanun metinlerine ulaşabilirsiniz.",
        )

        with st.container(border=True):
            q_col1, q_col2, q_col3 = st.columns([2.6, 1.1, 0.9], vertical_alignment="bottom")
            with q_col1:
                free_legal_query = st.text_input(
                    "Uyuşmazlık konusu veya kanun maddesi:",
                    value="Beş yılı dolduran kira sözleşmesinde kira tespit davası emsal rayiç ve eski kiracı hakkaniyet indirimi TBK m. 344",
                )
            with q_col2:
                free_domain = st.selectbox("Hukuk Alanı:", options=["Tüm Alanlar"] + LEGAL_DOMAINS)
            with q_col3:
                search_btn = st.button(":material/search: Emsal Karar Bul", type="primary", width="stretch")

        if search_btn and free_legal_query.strip():
            fetcher = get_fetcher()
            temp_p = get_parser().parse_text(free_legal_query, filename="sorgu.txt")
            dom_filter = "" if free_domain == "Tüm Alanlar" else free_domain
            found_precs = fetcher.search_precedents_for_claim(
                claim_text=free_legal_query,
                legal_domain=dom_filter,
                related_statutes=[f"{s.law_code} m. {s.article}" for s in temp_p.statute_refs],
                max_results=5,
                try_live_api=try_live_api_flag,
            )
            found_stats = [fetcher.fetch_statute(s) for s in temp_p.statute_refs]
            st.session_state["free_search_precs"] = found_precs
            st.session_state["free_search_stats"] = found_stats

        free_precs: List[FetchedPrecedent] = st.session_state.get("free_search_precs", [])
        free_stats: List[FetchedStatute] = st.session_state.get("free_search_stats", [])

        if free_stats:
            st.markdown("#### 📜 İlgili Kanun Maddeleri")
            for fst in free_stats:
                with st.container(border=True):
                    st.markdown(f"**{fst.full_label}**")
                    st.write(fst.official_text)
                    st.info(f"**Uygulama Notu:** {fst.practical_note}")

        if free_precs:
            st.markdown(f"#### 🏛️ Bulunan Emsal Kararlar ({len(free_precs)})")
            for idx_fp, fp in enumerate(free_precs, start=1):
                with st.container(border=True):
                    st.html(
                        f'<div class="precedent-card-header">🏛️ {idx_fp}. {fp.citation_label}</div>'
                    )
                    st.markdown(f"**📌 Karar Özeti:**  \n{fp.summary_principle}")
                    with st.expander("Kararın Tam Metnini ve Dilekçe Alıntı Şablonunu Gör"):
                        st.write(fp.full_text)
                        st.code(
                            f"Nitekim {fp.citation_label} sayılı ilamda da açıkça hüküm altına alındığı üzere; \"{fp.summary_principle}\"",
                            language="markdown",
                        )

    elif ai_tool == "DRAFT":
        drafter = get_drafter()
        render_guide_banner(
            step_badge="DİLEKÇE YAZIM ARACI",
            title="📝 Sıfırdan Resmi Word (.docx) Dilekçe Yazdırın",
            desc="Dilekçe türünü seçip olay özetinizi yazın; emsal Yargıtay kararlarıyla desteklenmiş resmi dilekçenizi hemen indirin.",
        )

        with st.container(border=True):
            f_c1, f_c2, f_c3 = st.columns(3)
            with f_c1:
                sel_pet_type = st.selectbox("Dilekçe Türü:", options=PETITION_TYPES)
                sel_domain = st.selectbox("Hukuk Alanı:", options=LEGAL_DOMAINS)
            with f_c2:
                inp_authority = st.text_input("Hitap Edilecek Makam:", value="ANKARA NÖBETÇİ İŞ MAHKEMESİ'NE")
                inp_file_no = st.text_input("Dosya / Esas No:", value="2026/418 Esas")
            with f_c3:
                inp_client = st.text_input("Müvekkil Adı / Unvanı:", value="Anadolu Teknoloji A.Ş. (Davalı)")
                inp_counter = st.text_input("Karşı Taraf Adı / Unvanı:", value="Ahmet Yılmaz (Davacı)")

            inp_subject = st.text_input(
                "Dilekçe Konusu:",
                value="Haksız ve hukuki dayanaktan yoksun davanın usul ve esastan reddi talebidir.",
            )
            inp_instructions = st.text_area(
                "Olay Özeti ve Savunma / İddia Maddeleriniz:",
                height=125,
                value=(
                    "1. Davacı işçi kendi isteğiyle istifa etmiş olmasına rağmen kıdem ve ihbar tazminatı talep etmektedir.\n"
                    "2. İşK m. 25/II kapsamında yapılan haklı fesihte savunma alınmasının zorunlu olduğu iddia edilmektedir.\n"
                    "3. Haftanın 6 günü ara dinlenmesiz 14 saat fazla mesai yapıldığı ileri sürülerek hakkaniyet indirimi yapılmaksızın %100 zamlı ücret ve bileşik faiz istenmektedir."
                ),
            )
            inp_outcome = st.text_input(
                "Sonuç ve İstem (Netice-i Talep):",
                value="Haksız davanın öncelikle usulden, aksi kanaatte esastan reddine, yargılama giderleri ve vekâlet ücretinin karşı tarafa yükletilmesine",
            )

            if st.button(":material/draw: Resmi Dilekçeyi Oluştur", type="primary", width="stretch"):
                custom_req = PetitionDraftRequest(
                    petition_type=sel_pet_type,
                    legal_domain=sel_domain,
                    authority=inp_authority,
                    case_file_no=inp_file_no,
                    client_role="DAVALI / ŞÜPHELİ" if "Cevap" in sel_pet_type or "Savunma" in sel_pet_type else "DAVACI / MÜŞTEKİ",
                    client_name=inp_client,
                    counterparty_role="KARŞI TARAF",
                    counterparty_name=inp_counter,
                    lawyer_name="Av. Batuhan Özmen",
                    subject=inp_subject,
                    lawyer_instructions=inp_instructions,
                    requested_outcome=inp_outcome,
                )
                pkg = drafter.draft_from_instructions(custom_req)
                st.session_state["generated_petition_package"] = pkg

        gen_pkg_ai: Optional[GeneratedPetitionPackage] = st.session_state.get("generated_petition_package")
        if gen_pkg_ai is not None:
            st.space("small")
            st.success(f"✅ **{gen_pkg_ai.title}** hazırlandı.")

            dl_c1, dl_c2 = st.columns(2)
            with dl_c1:
                docx_petition_bytes = drafter.export_generated_petition_docx(gen_pkg_ai)
                st.download_button(
                    label=":material/download: Resmi Dilekçeyi Word (.docx) Olarak İndir",
                    data=docx_petition_bytes,
                    file_name=f"Resmi_Dilekce_{safe_ref_token(gen_pkg_ai.petition_type)}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                    width="stretch",
                )
            with dl_c2:
                st.download_button(
                    label=":material/description: Dilekçe Metnini (.txt) Olarak İndir",
                    data=gen_pkg_ai.full_petition_text.encode("utf-8"),
                    file_name=f"Resmi_Dilekce_{safe_ref_token(gen_pkg_ai.petition_type)}.txt",
                    mime="text/plain",
                    width="stretch",
                )

            p_left, p_right = st.columns([1.35, 1.0])
            with p_left:
                with st.container(border=True):
                    st.markdown("#### 📜 Resmi Dilekçe Metni")
                    st.text_area(
                        "Resmi Dilekçe Metni:",
                        value=gen_pkg_ai.full_petition_text,
                        height=500,
                        label_visibility="collapsed",
                    )
            with p_right:
                with st.container(border=True):
                    st.markdown("#### 👨‍⚖️ Hukuki Strateji Gerekçeleri")
                    for idx_s, s_item in enumerate(gen_pkg_ai.strategy_report, start=1):
                        st.markdown(f"**{idx_s}. {s_item.section_title}**")
                        st.caption(f"• **Gerekçe:** {s_item.why_this_strategy}")
                        if s_item.used_precedents:
                            st.caption(f"• **Emsal Kararlar:** {', '.join(s_item.used_precedents)}")
                        if s_item.evidence_to_attach:
                            st.caption(f"• **Eklenecek Belge:** {s_item.evidence_to_attach}")
                        st.divider()
