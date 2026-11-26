"""
MODÜL 1: Uzun Dilekçe, Savcılık/Mahkeme Evrakı ve Hukuki Atıf Ayrıştırıcı (legal_parser.py)
-------------------------------------------------------------------------------------------
Görevleri:
1. Word (.docx), PDF (.pdf) veya düz metin (.txt) formatındaki uzun dava dilekçelerini,
   cevap dilekçelerini, savcılık şikâyet evraklarını, iddianameleri, mütalaaları,
   bilirkişi raporuna itiraz ve istinaf/temyiz dilekçelerini hiçbir cümleyi kırpmadan okur.
2. Evrakın hukuki iskeletini otomatik haritalandırır:
   - Hitap Makamı (Mahkeme / Cumhuriyet Başsavcılığı / BAM / Yargıtay / Danıştay)
   - Dosya / Esas / Soruşturma / İcra Numarası
   - Taraflar (Davacı, Davalı, Müşteki/Katılan, Şüpheli/Sanık, Alacaklı/Borçlu, Vekiller)
   - Evrak Türü ve Hukuki Alan Tespiti (İş, Ceza, Borçlar ve Kira, Aile, İcra-İflas,
     Ticaret, İdare ve Vergi, Tüketici Hukuku)
   - Bölümler (Başlık ve Taraflar, Usul İtirazları, Olaylar ve Açıklamalar,
     Hukuki Sebepler, Hukuki Deliller, Netice-i Talep / Sonuç ve İstem)
3. Metin içindeki tüm Kanun/Mevzuat atıflarını (StatuteReference: TCK m. 157, TBK m. 344,
   İşK m. 25/II-e, HMK m. 119, 6098 sayılı Kanun vb.) ve Yüksek Yargı Emsal Karar
   atıflarını (PrecedentCitation: Yargıtay Dairesi, HGK, CGK, İBK, Danıştay, BAM, AYM
   Esas/Karar No ve Tarih) bağlam cümlesiyle birlikte yakalar.
4. Dilekçedeki her bir iddia, savunma, vakıa ve talep bendini baştan sona eksiksiz
   `LegalClaimItem` nesnelerine dönüştürür.
5. Otomatik Usul, Dava Şartı ve Risk Ön Denetimi (`ProceduralCheckItem`) yapar.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore

try:
    import docx  # python-docx
except ImportError:
    docx = None  # type: ignore


# ---------------------------------------------------------------------------
# Veri Yapıları (@dataclass)
# ---------------------------------------------------------------------------

@dataclass
class StatuteReference:
    """Dilekçede geçen tek bir kanun veya mevzuat maddesi atfını temsil eder."""
    ref_id: str                       # Örn: "MEV_1", "MEV_2"
    law_code: str                     # Örn: "TBK", "TCK", "CMK", "HMK", "İşK", "İİK", "TMK", "TTK", "İYUK", "TKHK"
    law_number: Optional[str]         # Örn: "6098", "5237", "5271", "6100", "4857", "2004", "4721", "6102", "2577", "6502"
    article: str                      # Örn: "344", "25/II-e", "119/1-ğ", "157"
    raw_mention: str                  # Metinde geçtiği tam ifade (Örn: "TBK m. 344")
    context_sentence: str             # Geçtiği tam cümle

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PrecedentCitation:
    """Dilekçede atıf yapılan yüksek yargı veya istinaf emsal kararını temsil eder."""
    cit_id: str                       # Örn: "ICT_1", "ICT_2"
    court_type: str                   # "Yargıtay", "Danıştay", "BAM", "AYM", "HGK", "CGK", "İBK"
    chamber: str                      # Örn: "9. Hukuk Dairesi", "12. Ceza Dairesi", "Hukuk Genel Kurulu"
    esas_no: Optional[str]            # Örn: "2022/1453"
    karar_no: Optional[str]           # Örn: "2023/2891"
    decision_date: Optional[str]      # Örn: "14.05.2023"
    raw_marker: str                   # Metinde yakalanan tam karar künyesi
    claim_sentence: str               # Karara dayanılarak ileri sürülen hukuki iddia paragrafı/cümlesi
    paragraph_index: int              # Dilekçedeki paragraf sırası (1-tabanlı)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LegalClaimItem:
    """Dilekçenin içindeki her bir vakıa, iddia, savunma veya talep bendini temsil eder."""
    claim_id: str                     # Örn: "IDDIA_1", "IDDIA_2"
    section_name: str                 # Örn: "OLAYLAR VE AÇIKLAMALAR", "USUL İTİRAZLARI", "HUKUKİ SEBEPLER", "NETİCE-İ TALEP"
    paragraph_index: int              # Dilekçedeki paragraf sırası (1-tabanlı)
    claim_text: str                   # İddia veya savunma paragrafının kırpılmamış tam metni
    claim_category: str               # "Vakıa / Olay", "Usul İtirazı", "Hukuki Niteleme", "Delil / İspat", "Talep / İstem"
    related_statutes: List[str] = field(default_factory=list)     # Örn: ["TBK m. 344", "HMK m. 119"]
    related_precedents: List[str] = field(default_factory=list)   # Örn: ["Yargıtay 9. HD 2022/1453 E., 2023/2891 K."]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProceduralCheckItem:
    """Otomatik usul, dava şartı ve risk ön denetim sonucunu temsil eder."""
    check_title: str                  # Örn: "Hitap Makamı ve Görevli Mahkeme"
    status: str                       # "ok" | "warning" | "missing"
    detail: str                       # Tespit açıklaması
    recommendation: str               # Avukata somut hukuki tavsiye

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ParsedLegalDocument:
    """Ayrıştırılmış hukuki dilekçe veya dava dosyasının tüm yapısını tutar."""
    filename: str
    total_chars: int
    page_count: int
    document_type: str                # "Dava Dilekçesi", "Cevap Dilekçesi", "Savcılık Şikâyet Dilekçesi", "İddianame / Savunma", "İstinaf / Temyiz Dilekçesi", "Bilirkişi Raporuna İtiraz"
    legal_domain: str                 # "İş Hukuku", "Ceza Hukuku", "Borçlar ve Kira Hukuku", "Aile Hukuku", "İcra ve İflas Hukuku", "Ticaret Hukuku", "İdare ve Vergi Hukuku", "Tüketici Hukuku"
    authority: str                    # Tespit edilen mahkeme veya savcılık makamı
    case_file_no: Optional[str]       # Tespit edilen Esas / Soruşturma / Dosya No
    parties: Dict[str, str] = field(default_factory=dict)
    full_text: str = ""
    sections: Dict[str, str] = field(default_factory=dict)
    claims: List[LegalClaimItem] = field(default_factory=list)
    statute_refs: List[StatuteReference] = field(default_factory=list)
    precedent_citations: List[PrecedentCitation] = field(default_factory=list)
    procedural_checks: List[ProceduralCheckItem] = field(default_factory=list)
    neticei_talep: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "total_chars": self.total_chars,
            "page_count": self.page_count,
            "document_type": self.document_type,
            "legal_domain": self.legal_domain,
            "authority": self.authority,
            "case_file_no": self.case_file_no,
            "parties": dict(self.parties),
            "full_text": self.full_text,
            "sections": dict(self.sections),
            "claims": [c.to_dict() for c in self.claims],
            "statute_refs": [s.to_dict() for s in self.statute_refs],
            "precedent_citations": [p.to_dict() for p in self.precedent_citations],
            "procedural_checks": [pc.to_dict() for pc in self.procedural_checks],
            "neticei_talep": self.neticei_talep,
        }


# ---------------------------------------------------------------------------
# Türk Hukuku Mevzuat Sözlüğü ve Regex Sabitleri
# ---------------------------------------------------------------------------

LAW_CATALOG: Dict[str, Tuple[str, str]] = {
    "TBK": ("6098", "Türk Borçlar Kanunu"),
    "BK": ("6098", "Türk Borçlar Kanunu"),
    "TCK": ("5237", "Türk Ceza Kanunu"),
    "CMK": ("5271", "Ceza Muhakemesi Kanunu"),
    "HMK": ("6100", "Hukuk Muhakemeleri Kanunu"),
    "HUMK": ("1086", "Hukuk Usulü Muhakemeleri Kanunu"),
    "İŞK": ("4857", "İş Kanunu"),
    "İİK": ("2004", "İcra ve İflas Kanunu"),
    "TMK": ("4721", "Türk Medeni Kanunu"),
    "MK": ("4721", "Türk Medeni Kanunu"),
    "TTK": ("6102", "Türk Ticaret Kanunu"),
    "İYUK": ("2577", "İdari Yargılama Usulü Kanunu"),
    "TKHK": ("6502", "Tüketicinin Korunması Hakkında Kanun"),
    "KVKK": ("6698", "Kişisel Verilerin Korunması Kanunu"),
    "KMK": ("634", "Kat Mülkiyeti Kanunu"),
    "KTK": ("2918", "Karayolları Trafik Kanunu"),
    "AY": ("2709", "Türkiye Cumhuriyeti Anayasası"),
    "ANAYASA": ("2709", "Türkiye Cumhuriyeti Anayasası"),
    "VUK": ("213", "Vergi Usul Kanunu"),
    "AATUHK": ("6183", "Amme Alacaklarının Tahsil Usulü Hakkında Kanun"),
    "SMK": ("6769", "Sınai Mülkiyet Kanunu"),
    "FSEK": ("5846", "Fikir ve Sanat Eserleri Kanunu"),
    "DMK": ("657", "Devlet Memurları Kanunu"),
    "SSGSSK": ("5510", "Sosyal Sigortalar ve Genel Sağlık Sigortası Kanunu"),
    "HUAK": ("6325", "Hukuk Uyuşmazlıklarında Arabuluculuk Kanunu"),
    "İK": ("3194", "İmar Kanunu"),
}

LAW_NUMBER_TO_CODE: Dict[str, str] = {
    "6098": "TBK",
    "818": "EBK",
    "5237": "TCK",
    "765": "ETCK",
    "5271": "CMK",
    "1412": "CMUK",
    "6100": "HMK",
    "1086": "HUMK",
    "4857": "İşK",
    "1475": "EİşK",
    "7036": "İşMK",
    "2004": "İİK",
    "4721": "TMK",
    "743": "EMK",
    "6102": "TTK",
    "2577": "İYUK",
    "6502": "TKHK",
    "6698": "KVKK",
    "634": "KMK",
    "2918": "KTK",
    "2709": "AY",
    "213": "VUK",
    "6183": "AATUHK",
    "6769": "SMK",
    "5846": "FSEK",
    "657": "DMK",
    "5510": "SSGSSK",
    "6325": "HUAK",
    "3194": "İK",
}

LAW_FULLNAME_TO_CODE: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"Türk\s+Borçlar\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "TBK", "6098"),
    (re.compile(r"Borçlar\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "TBK", "6098"),
    (re.compile(r"Türk\s+Ceza\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "TCK", "5237"),
    (re.compile(r"Ceza\s+Muhakemesi\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "CMK", "5271"),
    (re.compile(r"Hukuk\s+Muhakemeleri\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "HMK", "6100"),
    (re.compile(r"İş\s+Mahkemeleri\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "İşMK", "7036"),
    (re.compile(r"İş\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "İşK", "4857"),
    (re.compile(r"İcra\s+(?:ve\s+)?İflas\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "İİK", "2004"),
    (re.compile(r"Türk\s+Medeni\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "TMK", "4721"),
    (re.compile(r"Medeni\s+Kanun(?:['’]?\w*)?", re.IGNORECASE), "TMK", "4721"),
    (re.compile(r"Türk\s+Ticaret\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "TTK", "6102"),
    (re.compile(r"İdari\s+Yargılama\s+Usulü\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "İYUK", "2577"),
    (re.compile(r"Tüketicinin\s+Korunması\s+Hakkında\s+Kanun(?:['’]?\w*)?", re.IGNORECASE), "TKHK", "6502"),
    (re.compile(r"Kişisel\s+Verilerin\s+Korunması\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "KVKK", "6698"),
    (re.compile(r"Kat\s+Mülkiyeti\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "KMK", "634"),
    (re.compile(r"Karayolları\s+Trafik\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "KTK", "2918"),
    (re.compile(r"Vergi\s+Usul\s+Kanunu(?:['’]?\w*)?", re.IGNORECASE), "VUK", "213"),
    (re.compile(r"Anayasa(?:['’]?\w*)?", re.IGNORECASE), "AY", "2709"),
]


def _tr_upper(text: str) -> str:
    """Türkçe karakter duyarlı büyük harfe çevirme (i -> İ, ı -> I)."""
    if not text:
        return ""
    return (
        text.replace("i", "İ")
        .replace("ı", "I")
        .replace("ğ", "Ğ")
        .replace("ü", "Ü")
        .replace("ş", "Ş")
        .replace("ö", "Ö")
        .replace("ç", "Ç")
        .upper()
    )


def _normalize_law_code_token(raw_code: str) -> Tuple[str, Optional[str]]:
    """Yakalanan kanun kısaltmasını standart koda ('İşK', 'TBK' vb.) ve kanun numarasına çevirir."""
    up = _tr_upper(raw_code.strip().rstrip("."))
    if up in ("İŞK", "IŞK", "ISK", "İŞ KANUNU"):
        return "İşK", "4857"
    if up in ("İŞMK", "IŞMK", "ISMK"):
        return "İşMK", "7036"
    if up in ("İİK", "IIK"):
        return "İİK", "2004"
    if up in ("İYUK", "IYUK"):
        return "İYUK", "2577"
    if up in LAW_CATALOG:
        num, _ = LAW_CATALOG[up]
        display_code = "İşK" if up == "İŞK" else ("AY" if up == "ANAYASA" else up)
        return display_code, num
    return raw_code.strip(), None


# ---------------------------------------------------------------------------
# Ana Hukuki Evrak Ayrıştırıcı Sınıfı (LegalDocumentParser)
# ---------------------------------------------------------------------------

class LegalDocumentParser:
    """Word (.docx), PDF (.pdf) ve düz metin (.txt) hukuki dilekçe ve dava dosyalarını ayrıştırır."""

    def parse_file(self, file_path_or_bytes: Any, filename: str = "dilekce.docx") -> ParsedLegalDocument:
        """Dosya yolundan veya bellek içi byte akışından dilekçeyi okur ve tam ayrıştırma yapar."""
        ext = Path(filename).suffix.lower()
        page_count = 1
        if ext == ".pdf":
            raw_text, page_count = self._read_pdf(file_path_or_bytes)
        elif ext in (".docx", ".doc"):
            raw_text, page_count = self._read_docx(file_path_or_bytes)
        else:
            if isinstance(file_path_or_bytes, (str, Path)) and Path(file_path_or_bytes).exists():
                raw_text = Path(file_path_or_bytes).read_text(encoding="utf-8", errors="ignore")
            elif isinstance(file_path_or_bytes, bytes):
                raw_text = file_path_or_bytes.decode("utf-8", errors="ignore")
            else:
                raw_text = str(file_path_or_bytes)
            page_count = max(1, (len(raw_text) // 2800) + 1)

        return self.parse_text(raw_text, filename=filename, page_count=page_count)

    # -----------------------------------------------------------------------
    # 1. PDF ve Word (.docx) Okuyucular (zelisimv1/document_parser.py Mimarisi)
    # -----------------------------------------------------------------------

    def _read_pdf(self, source: Any) -> Tuple[str, int]:
        """PyMuPDF ile uzun PDF dava dosyalarını ve dilekçeleri gürültüsüz okur."""
        if isinstance(source, (str, Path)):
            doc = fitz.open(str(source))
        elif isinstance(source, bytes):
            doc = fitz.open(stream=source, filetype="pdf")
        else:
            doc = fitz.open(stream=source.read(), filetype="pdf")

        page_count = max(1, len(doc))
        pages_text: List[str] = []

        for page in doc:
            text = page.get_text("text")
            clean_lines: List[str] = []
            for ln in text.split("\n"):
                s = ln.strip()
                if not s:
                    clean_lines.append("")
                    continue
                # Tek başına sayfa numaralarını ("1", "12", "Sayfa 3 / 15") atla
                if re.match(r"^(?:Sayfa\s*)?\d{1,3}(?:\s*/\s*\d{1,3})?$", s, re.IGNORECASE):
                    continue
                # UYAP e-imza sayfa altbilgisi tekrarlarını temizle
                if re.search(
                    r"5070\s+sayılı\s+Elektronik\s+İmza\s+Kanunu|UYAP\s+Bilişim\s+Sistemi\s+üzerinden|evrak\s+doğrulama\s+kodu",
                    s,
                    re.IGNORECASE,
                ):
                    continue
                clean_lines.append(ln)

            page_clean = "\n".join(clean_lines)
            # Satır sonu tire bölünmelerini birleştir
            page_clean = re.sub(
                r"([A-Za-zÇĞİÖŞÜçğıöşü])-\s*\n\s*([a-zçğıöşü])",
                r"\1\2",
                page_clean,
            )
            pages_text.append(page_clean)

        doc.close()
        return "\n".join(pages_text), page_count

    def _read_docx(self, source: Any) -> Tuple[str, int]:
        """
        python-docx ile Word dilekçesindeki tüm paragrafları ve tabloları
        XML (<w:p>, <w:r>, <w:t>) düzeyinde eksiksiz okur (<w:del> silinmiş metinleri atlar).
        """
        if isinstance(source, (str, Path)):
            document = docx.Document(str(source))
        elif isinstance(source, bytes):
            document = docx.Document(io.BytesIO(source))
        else:
            document = docx.Document(source)

        paragraphs: List[str] = []
        for p in document.paragraphs:
            p_txt = self._extract_docx_paragraph_text(p._p).strip()
            if p_txt:
                paragraphs.append(p_txt)

        # Dilekçe içindeki delil/alacak/hesap tablolarını da kaçırmamak için oku
        for table in document.tables:
            for row in table.rows:
                cell_texts: List[str] = []
                for cell in row.cells:
                    c_parts = [
                        self._extract_docx_paragraph_text(cp._p).strip()
                        for cp in cell.paragraphs
                    ]
                    c_txt = " ".join(x for x in c_parts if x)
                    if c_txt and (not cell_texts or c_txt != cell_texts[-1]):
                        cell_texts.append(c_txt)
                row_txt = " | ".join(cell_texts).strip()
                if row_txt:
                    paragraphs.append(row_txt)

        full_txt = "\n".join(paragraphs)
        est_pages = max(1, (len(full_txt) // 2800) + 1)
        return full_txt, est_pages

    def _extract_docx_paragraph_text(self, p_elem: Any) -> str:
        """Word XML paragrafındaki görünür metinleri (<w:t>, <w:tab>, <w:br>) çıkarır."""
        w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        chunks: List[str] = []

        for r in p_elem.iter(f"{w_ns}r"):
            parent = r.getparent()
            in_del = False
            while parent is not None and parent != p_elem:
                if parent.tag == f"{w_ns}del":
                    in_del = True
                    break
                parent = parent.getparent()
            if in_del:
                continue

            for child in r:
                if child.tag == f"{w_ns}t" and child.text:
                    chunks.append(child.text)
                elif child.tag == f"{w_ns}tab":
                    chunks.append(" ")
                elif child.tag == f"{w_ns}br":
                    chunks.append("\n")

        return "".join(chunks)

    # -----------------------------------------------------------------------
    # 2. Ana Metin Ayrıştırma Boru Hattı (parse_text)
    # -----------------------------------------------------------------------

    def parse_text(
        self, full_text: str, filename: str = "dilekce.txt", page_count: Optional[int] = None
    ) -> ParsedLegalDocument:
        """Tam metni hukuki bileşenlerine, iddialara, mevzuat ve içtihat atıflarına ayırır."""
        cleaned_text = (full_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if page_count is None:
            page_count = max(1, (len(cleaned_text) // 2800) + 1)

        paragraphs = self._split_into_paragraphs(cleaned_text)

        authority = self._detect_authority(paragraphs)
        case_file_no = self._detect_case_file_no(paragraphs)
        parties = self._extract_parties(paragraphs)
        document_type = self._detect_document_type(cleaned_text, authority)
        legal_domain = self._detect_legal_domain(cleaned_text, authority)
        sections, neticei_talep = self._split_legal_sections(paragraphs)

        statute_refs = self._extract_statute_references(paragraphs)
        precedent_citations = self._extract_precedent_citations(paragraphs)
        claims = self._extract_legal_claims(paragraphs, statute_refs, precedent_citations)

        procedural_checks = self._run_procedural_checks(
            full_text=cleaned_text,
            document_type=document_type,
            legal_domain=legal_domain,
            authority=authority,
            case_file_no=case_file_no,
            parties=parties,
            sections=sections,
            neticei_talep=neticei_talep,
            statute_refs=statute_refs,
            precedent_citations=precedent_citations,
        )

        return ParsedLegalDocument(
            filename=filename,
            total_chars=len(cleaned_text),
            page_count=page_count,
            document_type=document_type,
            legal_domain=legal_domain,
            authority=authority,
            case_file_no=case_file_no,
            parties=parties,
            full_text=cleaned_text,
            sections=sections,
            claims=claims,
            statute_refs=statute_refs,
            precedent_citations=precedent_citations,
            procedural_checks=procedural_checks,
            neticei_talep=neticei_talep,
        )

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Metni anlamlı paragraflara böler; çok satırlı tek paragrafları korur."""
        raw_lines = [ln.strip() for ln in text.split("\n")]
        paragraphs: List[str] = []
        buffer: List[str] = []

        # Yeni bir paragraf / bent başlangıcı olduğunu gösteren kalıplar
        new_block_re = re.compile(
            r"^(?:"
            r"\d{1,3}[\.\)\-]\s+"
            r"|[A-ZÇĞİÖŞÜ]{1,4}[\.\)\-]\s+"
            r"|(?:DAVACI|DAVALI|MÜŞTEKİ|KATILAN|ŞÜPHELİ|SANIK|ALACAKLI|BORÇLU|VEKİLİ|KONU|DAVA\s+KONUSU|SUÇ|SUÇ\s+TARİHİ|ESAS\s+NO|SORUŞTURMA\s+NO|DOSYA\s+NO|DAVA\s+DEĞERİ|HARCA\s+ESAS\s+DEĞER)\s*[:\-]"
            r"|(?:AÇIKLAMALAR|OLAYLAR|USUL\s+YÖNÜNDEN|ESAS\s+YÖNÜNDEN|HUKUKİ\s+SEBEPLER|HUKUKİ\s+NEDENLER|HUKUKİ\s+DELİLLER|DELİLLER|SONUÇ\s+VE\s+İSTEM|NETİCE[\-\s]*İ\s+TALEP|SONUÇ\s+VE\s+TALEP)"
            r"|.*[Mm][Aa][Hh][Kk][Ee][Mm][Ee][Ss][İi]'?[Nn][Ee]"
            r"|.*[Bb][Aa][Şş][Ss][Aa][Vv][Cc][Ii][Ll][Ii][Ğğ][Ii]'?[Nn][Aa]"
            r"|.*[Dd][Aa][İi][Rr][Ee][Ss][İi]\s*[Bb][Aa][Şş][Kk][Aa][Nn][Ll][Ii][Ğğ][Ii]'?[Nn][Aa]"
            r")",
            re.IGNORECASE,
        )

        for ln in raw_lines:
            if not ln:
                if buffer:
                    paragraphs.append(" ".join(buffer).strip())
                    buffer = []
                continue

            if new_block_re.match(ln) and buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer = [ln]
            else:
                # Eğer önceki satır nokta/iki nokta ile bitmişse ve bu satır büyük harfle başlıyorsa ayrı paragraf olarak tut
                if buffer and (
                    buffer[-1].endswith((".", ":", ";", "!", "?"))
                    and len(buffer[-1]) > 45
                ):
                    paragraphs.append(" ".join(buffer).strip())
                    buffer = [ln]
                else:
                    buffer.append(ln)

        if buffer:
            paragraphs.append(" ".join(buffer).strip())

        return [p for p in paragraphs if p]

    # -----------------------------------------------------------------------
    # 3. Hitap Makamı, Dosya No, Taraflar, Evrak Türü ve Hukuki Alan Tespiti
    # -----------------------------------------------------------------------

    def _detect_authority(self, paragraphs: List[str]) -> str:
        """Dilekçenin hitap ettiği mahkeme veya savcılık makamını tespit eder."""
        authority_re = re.compile(
            r"([A-ZÇĞİÖŞÜ0-9\.\s/\(\)\-]+?(?:"
            r"MAHKEMESİ(?:\s*SAYIN\s*HAKİMLİĞİ)?(?:['’]?NE|['’]?NDEN)?"
            r"|CUMHURİYET\s+BAŞSAVCILIĞI(?:['’]?NA)?"
            r"|BÖLGE\s+ADLİYE\s+MAHKEMESİ\s+[^\n]{0,50}?DAİRESİ(?:['’]?NE|['’]?BAŞKANLIĞI['’]?NA)?"
            r"|YARGITAY\s+[^\n]{0,50}?DAİRESİ(?:['’]?NE|['’]?BAŞKANLIĞI['’]?NA)?"
            r"|DANIŞTAY\s+[^\n]{0,50}?DAİRESİ(?:['’]?NE|['’]?BAŞKANLIĞI['’]?NA)?"
            r"|İCRA\s+(?:HUKUK\s+|CEZA\s+)?(?:MAHKEMESİ|MÜDÜRLÜĞÜ|DAİRESİ)(?:['’]?NE)?"
            r"|ANAYASA\s+MAHKEMESİ\s+BAŞKANLIĞI(?:['’]?NA)?"
            r"))",
            re.IGNORECASE,
        )
        for p in paragraphs[:12]:
            m = authority_re.search(p)
            if m and len(m.group(1).strip()) >= 10:
                return re.sub(r"\s+", " ", m.group(1)).strip()
        return "Hitap Makamı Belirtilmemiş"

    def _detect_case_file_no(self, paragraphs: List[str]) -> Optional[str]:
        """Dilekçe başlığındaki Esas No, Soruşturma No veya İcra Dosya No bilgisini yakalar."""
        file_no_re = re.compile(
            r"(?:ESAS|SORUŞTURMA|DOSYA|İCRA\s+DOSYA|KARAR|TALİMAT)\s*(?:NO|NUMARASI)?\s*[:\-]\s*(\d{4}\s*/\s*\d+(?:\s*(?:E\.|Esas|Soruşturma|K\.))?)",
            re.IGNORECASE,
        )
        for p in paragraphs[:18]:
            m = file_no_re.search(p)
            if m:
                return m.group(1).strip()
        return None

    def _extract_parties(self, paragraphs: List[str]) -> Dict[str, str]:
        """Dilekçe başlığındaki Davacı, Davalı, Müşteki, Şüpheli/Sanık ve Vekil bilgilerini ayıklar."""
        parties: Dict[str, str] = {}
        role_re = re.compile(
            r"^(DAVACI(?:\s*/\s*KARŞI\s*DAVALI)?|DAVALI(?:\s*/\s*KARŞI\s*DAVACI)?|"
            r"MÜŞTEKİ(?:\s*/\s*KATILAN)?|KATILAN|ŞİKÂYETÇİ|ŞİKAYETÇİ|"
            r"ŞÜPHELİ|SANIK|ALACAKLI|BORÇLU|"
            r"İSTİNAF\s+EDEN(?:\s*\([^\)]+\))?|TEMYİZ\s+EDEN(?:\s*\([^\)]+\))?|"
            r"VEKİLİ|MÜDAFİİ|KARŞI\s+TARAF)\s*[:\-]\s*(.+)$",
            re.IGNORECASE,
        )
        last_role: Optional[str] = None
        for p in paragraphs[:20]:
            m = role_re.match(p.strip())
            if m:
                raw_role = _tr_upper(m.group(1).strip())
                val = m.group(2).strip()
                if raw_role in ("VEKİLİ", "MÜDAFİİ") and last_role:
                    role_key = f"{last_role} {raw_role}"
                else:
                    role_key = raw_role
                    last_role = raw_role
                parties[role_key] = val
        return parties

    def _detect_document_type(self, text: str, authority: str) -> str:
        """Dilekçe veya evrakın hukuki türünü tespit eder."""
        head = _tr_upper(text[:3500])
        auth_up = _tr_upper(authority)

        if "BİLİRKİŞİ RAPORUNA İTİRAZ" in head or "BİLİRKİŞİ RAPORUNA BEYAN" in head:
            return "Bilirkişi Raporuna İtiraz Dilekçesi"
        if "İSTİNAF" in head and ("BÖLGE ADLİYE MAHKEMESİ" in head or "İSTİNAF KANUN YOLU" in head or "İSTİNAF DİLEKÇESİ" in head):
            return "İstinaf Başvuru Dilekçesi"
        if "TEMYİZ" in head and ("YARGITAY" in auth_up or "DANIŞTAY" in auth_up or "TEMYİZ DİLEKÇESİ" in head):
            return "Temyiz Başvuru Dilekçesi"
        if "İDDİANAME" in head and "CUMHURİYET BAŞSAVCILIĞI" in auth_up and "KAMU DAVASI" in head:
            return "Cumhuriyet Savcılığı İddianamesi"
        if "ESAS HAKKINDA MÜTALAA" in head or "ESAS HAKKINDA SAVUNMA" in head:
            return "Ceza Mahkemesi Esas Hakkında Savunma Dilekçesi"
        if "BAŞSAVCILIĞI" in auth_up or "SUÇ DUYURUSU" in head or "ŞİKÂYET DİLEKÇESİ" in head or "ŞİKAYET DİLEKÇESİ" in head:
            return "Savcılık Şikâyet (Suç Duyurusu) Dilekçesi"
        if "CEVABA CEVAP" in head or "REPLİK" in head:
            return "Cevaba Cevap (Replik) Dilekçesi"
        if "İKİNCİ CEVAP" in head or "DÜPLİK" in head:
            return "İkinci Cevap (Düplik) Dilekçesi"
        if "CEVAP DİLEKÇESİ" in head or "DAVAYA CEVAP" in head or "CEVAPLARIMIZIN SUNULMASI" in head:
            return "Cevap Dilekçesi"
        if "SAVUNMA DİLEKÇESİ" in head or ("SANIK" in head and "BERAAT" in _tr_upper(text)):
            return "Ceza Savunma Dilekçesi"
        return "Dava Dilekçesi"

    def _detect_legal_domain(self, text: str, authority: str) -> str:
        """Dilekçenin ait olduğu temel hukuk dalını anahtar kelime ve mahkeme türüyle tespit eder."""
        up = _tr_upper(text)
        auth_up = _tr_upper(authority)

        # 1. Hitap makamından doğrudan tespit
        if "İŞ MAHKEMESİ" in auth_up:
            return "İş Hukuku"
        if any(k in auth_up for k in ("CEZA MAHKEMESİ", "AĞIR CEZA", "ASLİYE CEZA", "SULH CEZA", "CUMHURİYET BAŞSAVCILIĞI")):
            return "Ceza Hukuku"
        if "AİLE MAHKEMESİ" in auth_up:
            return "Aile Hukuku"
        if "TİCARET MAHKEMESİ" in auth_up:
            return "Ticaret Hukuku"
        if "İDARE MAHKEMESİ" in auth_up or "VERGİ MAHKEMESİ" in auth_up or "DANIŞTAY" in auth_up:
            return "İdare ve Vergi Hukuku"
        if "TÜKETİCİ MAHKEMESİ" in auth_up:
            return "Tüketici Hukuku"
        if "İCRA" in auth_up:
            return "İcra ve İflas Hukuku"

        # 2. İçerik puanlaması
        scores: Dict[str, int] = {
            "İş Hukuku": sum(up.count(w) for w in ("KIDEM TAZMİNATI", "İHBAR TAZMİNATI", "İŞE İADE", "FAZLA MESAİ", "İŞ AKDİ", "İŞ SÖZLEŞMESİ", "4857", "MOBBİNG", "SGK")),
            "Ceza Hukuku": sum(up.count(w) for w in ("TCK", "CMK", "ŞÜPHELİ", "SANIK", "MÜŞTEKİ", "BERAAT", "İDDİANAME", "DOLANDIRICILIK", "SUÇ", "CEZALANDIRILMASI")),
            "Borçlar ve Kira Hukuku": sum(up.count(w) for w in ("TBK", "6098", "KİRA", "TAHLİYE", "TAZMİNAT", "HAKSIZ FİİL", "SEBEPSİZ ZENGİNLEŞME", "SÖZLEŞME", "TEMERRÜT")),
            "Aile Hukuku": sum(up.count(w) for w in ("BOŞANMA", "VELAYET", "NAFAKA", "ZİNA", "MAL REJİMİ", "KATILMA ALACAĞI", "TMK M. 166")),
            "İcra ve İflas Hukuku": sum(up.count(w) for w in ("İİK", "İTİRAZIN İPTALİ", "İCRA İNKAR", "ÖDEME EMRİ", "HACİZ", "MENFİ TESPİT", "İCRA DOSYASI")),
            "Ticaret Hukuku": sum(up.count(w) for w in ("TTK", "6102", "FATURA", "CARİ HESAP", "BONO", "ÇEK", "ANONİM ŞİRKET", "LİMİTED ŞİRKET", "HAKSIZ REKABET")),
            "İdare ve Vergi Hukuku": sum(up.count(w) for w in ("İYUK", "İDARİ İŞLEM", "İPTAL DAVASI", "TAM YARGI", "YÜRÜTMENİN DURDURULMASI", "VERGİ ZİYAI")),
            "Tüketici Hukuku": sum(up.count(w) for w in ("TKHK", "6502", "AYIPLI MAL", "AYIPLI HİZMET", "TÜKETİCİ HAKEM HEYETİ")),
        }
        best_domain, best_score = max(scores.items(), key=lambda kv: kv[1])
        return best_domain if best_score > 0 else "Borçlar ve Kira Hukuku"

    # -----------------------------------------------------------------------
    # 4. Dilekçe Bölümlerini ve Netice-i Talep Kısmını Ayırma
    # -----------------------------------------------------------------------

    def _split_legal_sections(self, paragraphs: List[str]) -> Tuple[Dict[str, str], str]:
        """Dilekçeyi Türk hukuk usulüne göre ana bölümlere ayırır ve Netice-i Talep metnini çıkarır."""
        section_buffers: Dict[str, List[str]] = {
            "BAŞLIK VE TARAFLAR": [],
            "USUL İTİRAZLARI": [],
            "OLAYLAR VE AÇIKLAMALAR": [],
            "HUKUKİ SEBEPLER": [],
            "HUKUKİ DELİLLER": [],
            "NETİCE-İ TALEP (SONUÇ VE İSTEM)": [],
        }

        current_section = "BAŞLIK VE TARAFLAR"

        heading_rules: List[Tuple[re.Pattern, str]] = [
            (
                re.compile(
                    r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:USUL(?:E\s+İLİŞKİN|\s+YÖNÜNDEN)?\s+(?:İTİRAZLAR\w*|BEYANLAR\w*|AÇIKLAMALAR\w*)|GÖREV\s+VE\s+YETKİ\s+İTİRAZ\w*|ZAMANAŞIMI\s+İTİRAZ\w*)\s*:?",
                    re.IGNORECASE,
                ),
                "USUL İTİRAZLARI",
            ),
            (
                re.compile(
                    r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:AÇIKLAMALAR\w*|OLAYLAR(?:\s+VE\s+AÇIKLAMALAR)?|ESASA\s+İLİŞKİN\s+(?:AÇIKLAMALAR\w*|BEYANLAR\w*|SAVUNMALAR\w*)|ESAS\s+YÖNÜNDEN|SAVUNMALARIMIZ|İTİRAZ\s+NEDENLERİMİZ|İSTİNAF\s+(?:SEBEPLERİMİZ|NEDENLERİMİZ)|TEMYİZ\s+SEBEPLERİMİZ)\s*:?",
                    re.IGNORECASE,
                ),
                "OLAYLAR VE AÇIKLAMALAR",
            ),
            (
                re.compile(
                    r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:HUKUKİ\s+SEBEPLER|HUKUKİ\s+NEDENLER|HUKUKİ\s+DAYANAKLAR)\s*:?",
                    re.IGNORECASE,
                ),
                "HUKUKİ SEBEPLER",
            ),
            (
                re.compile(
                    r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:HUKUKİ\s+DELİLLER|DELİLLER(?:İMİZ)?|SUBUT\s+DELİLLER\w*)\s*:?",
                    re.IGNORECASE,
                ),
                "HUKUKİ DELİLLER",
            ),
            (
                re.compile(
                    r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:SONUÇ\s+VE\s+(?:İSTEM|TALEP)|NETİCE[\-\s]*İ\s+TALEP|SONUÇ\s+VE\s+NETİCE[\-\s]*İ\s+TALEP|NETİCE\s+VE\s+TALEP|İSTEM\s+VE\s+SONUÇ)\s*:?",
                    re.IGNORECASE,
                ),
                "NETİCE-İ TALEP (SONUÇ VE İSTEM)",
            ),
        ]

        for idx, p in enumerate(paragraphs):
            matched_heading = False
            for pat, target_sec in heading_rules:
                if pat.match(p.strip()):
                    current_section = target_sec
                    matched_heading = True
                    break

            # Eğer henüz BAŞLIK VE TARAFLAR içindeysek ve 1., 2. gibi uzun bir açıklama paragrafı başladıysa OLAYLAR VE AÇIKLAMALAR'a geç
            if (
                not matched_heading
                and current_section == "BAŞLIK VE TARAFLAR"
                and idx >= 3
                and len(p) > 130
                and not re.match(
                    r"^(?:DAVACI|DAVALI|MÜŞTEKİ|ŞÜPHELİ|SANIK|VEKİLİ|KONU|DAVA\s+KONUSU|SUÇ)\s*[:\-]",
                    p,
                    re.IGNORECASE,
                )
            ):
                current_section = "OLAYLAR VE AÇIKLAMALAR"

            # Başlık etiketi olmadan doğrudan "Yukarıda arz ve izah edilen nedenlerle... arz ve talep ederiz" ile biten sonuç paragrafı
            if (
                current_section != "NETİCE-İ TALEP (SONUÇ VE İSTEM)"
                and re.search(
                    r"^(?:Yukarıda\s+(?:arz\s+ve\s+izah|açıklanan)|Açıklanan\s+nedenlerle).*?(?:karar\s+verilmesini|arz\s+ve\s+talep)",
                    p,
                    re.IGNORECASE,
                )
            ):
                current_section = "NETİCE-İ TALEP (SONUÇ VE İSTEM)"

            section_buffers[current_section].append(p)

        sections = {k: "\n\n".join(v).strip() for k, v in section_buffers.items() if v}
        neticei_talep = sections.get("NETİCE-İ TALEP (SONUÇ VE İSTEM)", "")
        return sections, neticei_talep

    # -----------------------------------------------------------------------
    # 5. Kanun / Mevzuat Maddesi Yakalayıcı (_extract_statute_references)
    # -----------------------------------------------------------------------

    def _extract_statute_references(self, paragraphs: List[str]) -> List[StatuteReference]:
        """
        Metin içindeki tüm kanun maddesi atıflarını yakalar:
        - Kısaltmalı: 'TBK m. 344', 'TCK md. 157/1', 'İşK m. 25/II-e', 'HMK'nın 119/1-ğ maddesi'
        - Sayılı Kanun: '6098 sayılı Kanun'un 344. maddesi', '4857 sayılı İş Kanunu m. 18'
        - Tam İsimli: 'Türk Borçlar Kanunu'nun 344. maddesi'
        """
        refs: List[StatuteReference] = []
        seen_keys: set[Tuple[str, str, int]] = set()

        # Desen 1: Kısaltma + m./md./madde + numara (Örn: TBK m. 344, İşK m. 25/II-e, HMK'nın 119/1-ğ maddesi)
        code_tokens = r"(?:TBK|BK|TCK|CMK|HMK|HUMK|İşK|İŞK|IŞK|İşMK|İŞMK|İİK|IIK|TMK|MK|TTK|İYUK|IYUK|TKHK|KVKK|KMK|KTK|VUK|AATUHK|SMK|FSEK|DMK|SSGSSK|HUAK|AY|Anayasa)"
        art_token = r"(\d{1,4}(?:\s*/\s*(?:[IVX]+|\d+))?(?:\s*[\-/]\s*[a-zçğıöşü0-9]+)?)"

        pattern_short = re.compile(
            rf"\b({code_tokens})(?:['’]?[nNdDaAeEıİuÜ]{1,4})?\s*"
            rf"(?:(?:m\.|md\.|mad\.|madde|maddesi)\s*{art_token}|{art_token}\s*(?:\.|['’]?[ncıiuü]+)?\s*(?:maddesi\w*|md\.|m\.))",
            re.IGNORECASE,
        )

        # Desen 2: Sayılı Kanun + madde (Örn: 6098 sayılı Türk Borçlar Kanunu'nun 344. maddesi / 5237 sayılı Kanun m. 158)
        pattern_numbered = re.compile(
            rf"\b(\d{{3,4}})\s+sayılı\s+(?:[A-ZÇĞİÖŞÜa-zçğıöşü\s]{{2,45}}?)?(?:Kanun(?:u)?(?:['’]?\w*)?\s*)?"
            rf"(?:(?:m\.|md\.|madde)\s*{art_token}|{art_token}\s*(?:\.|['’]?[ncıiuü]+)?\s*maddesi\w*)",
            re.IGNORECASE,
        )

        for p_idx, para in enumerate(paragraphs, start=1):
            sentences = self._split_sentences(para)
            for sent in sentences:
                # 1. Kısaltmalı kanun maddeleri
                for m in pattern_short.finditer(sent):
                    raw_code = m.group(1)
                    article = (m.group(2) or m.group(3) or "").replace(" ", "")
                    if not article:
                        continue
                    law_code, law_num = _normalize_law_code_token(raw_code)
                    dedup_key = (law_code, article, p_idx)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    refs.append(
                        StatuteReference(
                            ref_id=f"MEV_{len(refs) + 1}",
                            law_code=law_code,
                            law_number=law_num,
                            article=article,
                            raw_mention=m.group(0).strip(),
                            context_sentence=sent.strip(),
                        )
                    )

                # 2. Sayılı kanun maddeleri
                for m in pattern_numbered.finditer(sent):
                    law_num = m.group(1).strip()
                    article = (m.group(2) or m.group(3) or "").replace(" ", "")
                    if not article:
                        continue
                    law_code = LAW_NUMBER_TO_CODE.get(law_num, f"{law_num} S.K.")
                    dedup_key = (law_code, article, p_idx)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)
                    refs.append(
                        StatuteReference(
                            ref_id=f"MEV_{len(refs) + 1}",
                            law_code=law_code,
                            law_number=law_num,
                            article=article,
                            raw_mention=m.group(0).strip(),
                            context_sentence=sent.strip(),
                        )
                    )

                # 3. Tam isimli kanun maddeleri (Örn: "Türk Borçlar Kanunu'nun 344. maddesi")
                for law_pat, law_code, law_num in LAW_FULLNAME_TO_CODE:
                    full_art_re = re.compile(
                        rf"({law_pat.pattern})\s*(?:(?:m\.|md\.|madde)\s*{art_token}|{art_token}\s*(?:\.|['’]?[ncıiuü]+)?\s*maddesi\w*)",
                        re.IGNORECASE,
                    )
                    for fm in full_art_re.finditer(sent):
                        article = (fm.group(2) or fm.group(3) or "").replace(" ", "")
                        if not article:
                            continue
                        dedup_key = (law_code, article, p_idx)
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)
                        refs.append(
                            StatuteReference(
                                ref_id=f"MEV_{len(refs) + 1}",
                                law_code=law_code,
                                law_number=law_num,
                                article=article,
                                raw_mention=fm.group(0).strip(),
                                context_sentence=sent.strip(),
                            )
                        )

        return refs

    # -----------------------------------------------------------------------
    # 6. Yüksek Yargı / Emsal Karar Yakalayıcı (_extract_precedent_citations)
    # -----------------------------------------------------------------------

    def _extract_precedent_citations(self, paragraphs: List[str]) -> List[PrecedentCitation]:
        """
        Dilekçede geçen tüm Yargıtay, HGK, CGK, İBK, Danıştay, BAM (İstinaf) ve AYM
        karar atıflarını Esas No, Karar No, Tarih, Daire ve iddia cümlesiyle birlikte yakalar.
        """
        citations: List[PrecedentCitation] = []
        seen_spans: set[Tuple[int, str]] = set()

        # Yüksek mahkeme ve daire başlangıcı yakalayıcı
        court_pattern = re.compile(
            r"\b(?:"
            r"Yargıtay\s+(?:Hukuk\s+Genel\s+Kurulu|Ceza\s+Genel\s+Kurulu|İçtihadı\s+Birleştirme\s+(?:Büyük\s+)?Genel\s+Kurulu|HGK|CGK|İBK|\d{1,2}\.\s*(?:Hukuk\s+Dairesi|Ceza\s+Dairesi|HD\.?|CD\.?))"
            r"|Danıştay\s+(?:İdari\s+Dava\s+Daireleri\s+Kurulu|Vergi\s+Dava\s+Daireleri\s+Kurulu|İDDK|VDDK|\d{1,2}\.\s*Daire(?:si)?)"
            r"|(?:Ankara|İstanbul|İzmir|Bursa|Antalya|Adana|Gaziantep|Konya|Samsun|Kayseri|Trabzon|Erzurum|Diyarbakır|Van|Sakarya)\s+Bölge\s+Adliye\s+Mahkemesi\s+\d{1,2}\.\s*(?:Hukuk\s+Dairesi|Ceza\s+Dairesi|HD\.?|CD\.?)"
            r"|BAM\s+\d{1,2}\.\s*(?:Hukuk\s+Dairesi|Ceza\s+Dairesi|HD\.?|CD\.?)"
            r"|Anayasa\s+Mahkemesi(?:['’]?nin)?|AYM(?:['’]?nin)?"
            r")(?:['’]?[nN][ıiİuü][nN])?",
            re.IGNORECASE,
        )

        esas_re = re.compile(
            r"(?:Esas\s*(?:No)?\s*[:\.]?\s*(\d{4}\s*/\s*\d+)|(\d{4}\s*/\s*\d+)\s*(?:E\.|Esas))",
            re.IGNORECASE,
        )
        karar_re = re.compile(
            r"(?:Karar\s*(?:No)?\s*[:\.]?\s*(\d{4}\s*/\s*\d+)|(\d{4}\s*/\s*\d+)\s*(?:K\.|Karar))",
            re.IGNORECASE,
        )
        aym_basvuru_re = re.compile(
            r"(?:B\.\s*No|Başvuru\s*No)\s*[:\.]?\s*(\d{4}\s*/\s*\d+)",
            re.IGNORECASE,
        )
        date_re = re.compile(r"\b(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{4})\b")

        for p_idx, para in enumerate(paragraphs, start=1):
            court_matches = list(court_pattern.finditer(para))
            for i_cm, cm in enumerate(court_matches):
                start_pos = cm.start()
                # Bir sonraki mahkeme adına kadar olan pencereyi tara ki ardışık iki mahkeme adı aynı Esas/Karar numarasını paylaşmasın
                next_court_pos = (
                    court_matches[i_cm + 1].start()
                    if i_cm + 1 < len(court_matches)
                    else len(para)
                )
                window_end = min(next_court_pos, cm.end() + 175)
                window = para[start_pos:window_end]
                pre_start = court_matches[i_cm - 1].end() if i_cm > 0 else max(0, start_pos - 45)
                pre_window = para[max(pre_start, start_pos - 45) : window_end]

                m_esas = esas_re.search(window)
                m_karar = karar_re.search(window)
                m_aym = aym_basvuru_re.search(window)
                m_date = date_re.search(pre_window)

                esas_no = (m_esas.group(1) or m_esas.group(2)).replace(" ", "") if m_esas else None
                karar_no = (m_karar.group(1) or m_karar.group(2)).replace(" ", "") if m_karar else None
                if not esas_no and m_aym:
                    esas_no = m_aym.group(1).replace(" ", "")
                decision_date = m_date.group(1) if m_date else None

                raw_court = cm.group(0).strip()
                court_type, chamber = self._classify_court_and_chamber(raw_court)

                # Marker metnini oluştur ("HGK Yargıtay..." gibi çift ön eki önle)
                base_label = chamber if court_type in ("HGK", "CGK", "İBK", "AYM", "BAM") else f"{court_type} {chamber}".strip()
                marker_parts = [base_label]
                if decision_date:
                    marker_parts.append(f"T. {decision_date}")
                if esas_no:
                    marker_parts.append(f"{esas_no} E.")
                if karar_no:
                    marker_parts.append(f"{karar_no} K.")
                raw_marker = ", ".join(marker_parts)

                dedup_key = (p_idx, f"{court_type}|{chamber}|{esas_no}|{karar_no}")
                if dedup_key in seen_spans:
                    continue
                seen_spans.add(dedup_key)

                citations.append(
                    PrecedentCitation(
                        cit_id=f"ICT_{len(citations) + 1}",
                        court_type=court_type,
                        chamber=chamber,
                        esas_no=esas_no,
                        karar_no=karar_no,
                        decision_date=decision_date,
                        raw_marker=raw_marker,
                        claim_sentence=para.strip(),
                        paragraph_index=p_idx,
                    )
                )

        return citations

    def _classify_court_and_chamber(self, raw_court: str) -> Tuple[str, str]:
        """Mahkeme metnini standart (court_type, chamber) çiftine dönüştürür."""
        up = _tr_upper(raw_court)
        if "HUKUK GENEL KURULU" in up or "HGK" in up:
            return "HGK", "Yargıtay Hukuk Genel Kurulu"
        if "CEZA GENEL KURULU" in up or "CGK" in up:
            return "CGK", "Yargıtay Ceza Genel Kurulu"
        if "İÇTİHADI BİRLEŞTİRME" in up or "İBK" in up:
            return "İBK", "Yargıtay İçtihadı Birleştirme Genel Kurulu"
        if "ANAYASA MAHKEMESİ" in up or up.startswith("AYM"):
            return "AYM", "Anayasa Mahkemesi"
        if "BÖLGE ADLİYE MAHKEMESİ" in up or up.startswith("BAM"):
            m_ch = re.search(r"(\d{1,2})\.\s*(Hukuk|Ceza|HD|CD)", raw_court, re.IGNORECASE)
            if m_ch:
                kind = "Hukuk Dairesi" if "H" in _tr_upper(m_ch.group(2)) else "Ceza Dairesi"
                city_m = re.match(r"^([A-ZÇĞİÖŞÜa-zçğıöşü]+)\s+Bölge", raw_court)
                city_prefix = f"{city_m.group(1)} BAM " if city_m else "BAM "
                return "BAM", f"{city_prefix}{m_ch.group(1)}. {kind}"
            return "BAM", raw_court
        if "DANIŞTAY" in up:
            if "İDARİ DAVA DAİRELERİ" in up or "İDDK" in up:
                return "Danıştay", "İdari Dava Daireleri Kurulu"
            if "VERGİ DAVA DAİRELERİ" in up or "VDDK" in up:
                return "Danıştay", "Vergi Dava Daireleri Kurulu"
            m_d = re.search(r"(\d{1,2})\.\s*Daire", raw_court, re.IGNORECASE)
            if m_d:
                return "Danıştay", f"{m_d.group(1)}. Dairesi"
            return "Danıştay", raw_court

        # Yargıtay Dairesi
        m_y = re.search(r"(\d{1,2})\.\s*(Hukuk|Ceza|HD|CD)", raw_court, re.IGNORECASE)
        if m_y:
            kind = "Hukuk Dairesi" if "H" in _tr_upper(m_y.group(2)) else "Ceza Dairesi"
            return "Yargıtay", f"{m_y.group(1)}. {kind}"
        return "Yargıtay", raw_court

    # -----------------------------------------------------------------------
    # 7. İddia ve Savunma Bentlerini Çıkarma (_extract_legal_claims)
    # -----------------------------------------------------------------------

    def _extract_legal_claims(
        self,
        paragraphs: List[str],
        statute_refs: List[StatuteReference],
        precedent_citations: List[PrecedentCitation],
    ) -> List[LegalClaimItem]:
        """
        Uzun dilekçenin başından sonuna kadar tüm iddia, vakıa, usul itirazı,
        delil ve talep paragraflarını eksiksiz `LegalClaimItem` listesine dönüştürür.
        """
        claims: List[LegalClaimItem] = []
        current_section = "OLAYLAR VE AÇIKLAMALAR"

        # Bölüm başlığı satırlarını yakalayan desen
        sec_heading_re = re.compile(
            r"^(?:[IVX\d]+[\.\)\-]\s*)?(?:AÇIKLAMALAR|OLAYLAR(?:\s+VE\s+AÇIKLAMALAR)?|USUL(?:E\s+İLİŞKİN|\s+YÖNÜNDEN)?\s+(?:İTİRAZLAR\w*|BEYANLAR\w*)|ESASA\s+İLİŞKİN\s+AÇIKLAMALAR\w*|ESAS\s+YÖNÜNDEN|SAVUNMALARIMIZ|HUKUKİ\s+SEBEPLER|HUKUKİ\s+NEDENLER|HUKUKİ\s+DELİLLER|DELİLLER(?:İMİZ)?|SONUÇ\s+VE\s+(?:İSTEM|TALEP)|NETİCE[\-\s]*İ\s+TALEP)\s*:?\s*$",
            re.IGNORECASE,
        )

        # Künye/taraf satırlarını atlayan desen (bunlar zaten `parties`, `authority`, `case_file_no` alanında tutulur)
        meta_line_re = re.compile(
            r"^(?:DAVACI|DAVALI|MÜŞTEKİ|KATILAN|ŞÜPHELİ|SANIK|ALACAKLI|BORÇLU|VEKİLİ|MÜDAFİİ|ADRES\w*|TC\s+KİMLİK|ESAS\s+NO|SORUŞTURMA\s+NO|DOSYA\s+NO|KARAR\s+NO)\s*[:\-]",
            re.IGNORECASE,
        )

        for p_idx, para in enumerate(paragraphs, start=1):
            p_clean = para.strip()
            if not p_clean:
                continue

            # Bölüm başlığı kontrolü
            up_p = _tr_upper(p_clean)
            if sec_heading_re.match(p_clean):
                if "USUL" in up_p:
                    current_section = "USUL İTİRAZLARI"
                elif "HUKUKİ SEBEP" in up_p or "HUKUKİ NEDEN" in up_p:
                    current_section = "HUKUKİ SEBEPLER"
                elif "DELİL" in up_p:
                    current_section = "HUKUKİ DELİLLER"
                elif "SONUÇ" in up_p or "NETİCE" in up_p or "İSTEM" in up_p:
                    current_section = "NETİCE-İ TALEP"
                else:
                    current_section = "OLAYLAR VE AÇIKLAMALAR"
                continue

            # Tek satırlık mahkeme hitap başlığı veya taraf künyesi ise iddia listesine alma
            if p_idx <= 12 and (
                meta_line_re.match(p_clean)
                or (
                    len(p_clean) < 110
                    and re.search(r"(?:MAHKEMESİ|BAŞSAVCILIĞI|DAİRESİ)(?:['’]?NE|['’]?NA)?$", p_clean, re.IGNORECASE)
                )
            ):
                continue

            # Çok kısa imza/tarih satırlarını ("Davacı Vekili Av. ...", "Saygılarımla,") atla
            if len(p_clean) < 40 and not any(c.paragraph_index == p_idx for c in precedent_citations):
                continue

            # Bu paragrafla ilişkili mevzuat ve emsal kararları bul
            rel_statutes: List[str] = []
            for s in statute_refs:
                if s.raw_mention in p_clean or s.context_sentence in p_clean:
                    label = f"{s.law_code} m. {s.article}"
                    if label not in rel_statutes:
                        rel_statutes.append(label)

            rel_precedents: List[str] = [
                c.raw_marker for c in precedent_citations if c.paragraph_index == p_idx
            ]

            category = self._categorize_claim(p_clean, current_section, rel_statutes, rel_precedents)

            claims.append(
                LegalClaimItem(
                    claim_id=f"IDDIA_{len(claims) + 1}",
                    section_name=current_section,
                    paragraph_index=p_idx,
                    claim_text=p_clean,
                    claim_category=category,
                    related_statutes=rel_statutes,
                    related_precedents=rel_precedents,
                )
            )

        return claims

    def _categorize_claim(
        self,
        text: str,
        section_name: str,
        rel_statutes: List[str],
        rel_precedents: List[str],
    ) -> str:
        """Paragrafın hukuki niteliğini 5 kategoriden birine sınıflandırır."""
        up = _tr_upper(text)
        if section_name == "NETİCE-İ TALEP" or re.search(
            r"\b(?:ARZ\s+VE\s+TALEP|KARAR\s+VERİLMESİNİ|CEZALANDIRILMASINA|BERAATİNE|REDDİNE|KABULÜNE)\b",
            up,
        ):
            return "Talep / İstem"
        if section_name == "USUL İTİRAZLARI" or any(
            k in up
            for k in (
                "GÖREVSİZLİK",
                "YETKİSİZLİK",
                "ZAMANAŞIMI",
                "HAK DÜŞÜRÜCÜ SÜRE",
                "DAVA ŞARTI",
                "ARABULUCULUK",
                "HUSUMET",
                "DERDESTLİK",
                "KESİN HÜKÜM",
            )
        ):
            return "Usul İtirazı"
        if section_name == "HUKUKİ DELİLLER" or any(
            k in up for k in ("DELİL", "TANIK", "BİLİRKİŞİ", "KEŞİF", "İSPAT YÜKÜ", "YEMİN", "BANKA KAYITLARI", "HTS")
        ):
            if not rel_precedents and not rel_statutes:
                return "Delil / İspat"
        if rel_statutes or rel_precedents or section_name == "HUKUKİ SEBEPLER":
            return "Hukuki Niteleme"
        return "Vakıa / Olay"

    # -----------------------------------------------------------------------
    # 8. Otomatik Usul, Dava Şartı ve Risk Ön Denetimi (_run_procedural_checks)
    # -----------------------------------------------------------------------

    def _run_procedural_checks(
        self,
        full_text: str,
        document_type: str,
        legal_domain: str,
        authority: str,
        case_file_no: Optional[str],
        parties: Dict[str, str],
        sections: Dict[str, str],
        neticei_talep: str,
        statute_refs: List[StatuteReference],
        precedent_citations: List[PrecedentCitation],
    ) -> List[ProceduralCheckItem]:
        """Dilekçe türüne ve hukuki alana göre 5 kritik usul ve risk kontrolü yapar."""
        checks: List[ProceduralCheckItem] = []
        up_full = _tr_upper(full_text)
        up_talep = _tr_upper(neticei_talep)

        # 1. Hitap Makamı ve Görevli Mahkeme Kontrolü
        if authority == "Hitap Makamı Belirtilmemiş":
            checks.append(
                ProceduralCheckItem(
                    check_title="Hitap Makamı ve Görevli Mahkeme (HMK m. 119/1-a / CMK m. 170)",
                    status="missing",
                    detail="Dilekçenin başında hitap edilen mahkeme veya Cumhuriyet Başsavcılığı makamı tespit edilemedi.",
                    recommendation="Dilekçenin en üstüne görevli ve yetkili makamı (Örn: 'ANKARA NÖBETÇİ İŞ MAHKEMESİ'NE' veya 'İSTANBUL CUMHURİYET BAŞSAVCILIĞI'NA') büyük harflerle ekleyin.",
                )
            )
        else:
            checks.append(
                ProceduralCheckItem(
                    check_title="Hitap Makamı ve Görevli Mahkeme (HMK m. 119/1-a)",
                    status="ok",
                    detail=f"Hitap makamı '{authority}' olarak tespit edildi ve '{legal_domain}' alanıyla uyumlu.",
                    recommendation="Görev kamu düzenine ilişkindir (HMK m. 1); dava konusu uyuşmazlığın özel görevli mahkeme (İş, Tüketici, Ticaret, Aile) kapsamına girip girmediğini son kez teyit edin.",
                )
            )

        # 2. Zorunlu Arabuluculuk / Dava Şartı Kontrolü
        needs_mediation = legal_domain in (
            "İş Hukuku",
            "Ticaret Hukuku",
            "Tüketici Hukuku",
        ) or ("KİRA" in up_full or "TAHLİYE" in up_full)
        is_first_petition = document_type == "Dava Dilekçesi"

        if is_first_petition and needs_mediation:
            if "ARABULUCU" in up_full or "SON TUTANAK" in up_full:
                checks.append(
                    ProceduralCheckItem(
                        check_title="Zorunlu Arabuluculuk Dava Şartı (7036 S.K. m. 3 / TTK m. 5/A / TKHK m. 73/A / HUAK m. 18/B)",
                        status="ok",
                        detail=f"'{legal_domain}' kapsamındaki dava dilekçesinde arabuluculuk sürecine ve tutanağına atıf yapıldığı tespit edildi.",
                        recommendation="Arabuluculuk anlaşamama son tutanağının aslını veya arabulucu tarafından onaylanmış örneğini dilekçe ekine (EK-1) mutlaka ekleyin (HMK m. 115 uyarınca usulden ret sebebidir).",
                    )
                )
            else:
                checks.append(
                    ProceduralCheckItem(
                        check_title="Zorunlu Arabuluculuk Dava Şartı Riski",
                        status="warning",
                        detail=f"'{legal_domain}' uyuşmazlıklarında dava açılmadan önce arabulucuya başvurulması dava şartıdır; ancak metinde arabuluculuk son tutanağına ilişkin bir ibare bulunamadı.",
                        recommendation="Dava zorunlu arabuluculuğa tabi ise (işçi-işveren alacak/işe iade, ticari alacak, tüketici, kira uyuşmazlıkları) arabuluculuk son tutanak tarih ve numarasını dilekçeye işleyin ve ekler kısmına ekleyin.",
                    )
                )
        else:
            checks.append(
                ProceduralCheckItem(
                    check_title="Usul ve Dosya / Soruşturma Künyesi Denetimi",
                    status="ok" if (case_file_no or is_first_petition) else "warning",
                    detail=(
                        f"Dosya/Soruşturma numarası ({case_file_no}) ve taraf bilgileri mevcut."
                        if case_file_no
                        else "Mevcut bir dosyaya sunulan dilekçede Esas / Soruşturma No açıkça belirtilmemiş olabilir."
                    ),
                    recommendation="Cevap, beyan, itiraz ve kanun yolu dilekçelerinde Esas/Soruşturma numarasını başlıkta açıkça belirtin.",
                )
            )

        # 3. Zamanaşımı / Hak Düşürücü Süre / Şikâyet Süresi Kontrolü
        has_time_limit_mention = any(
            k in up_full
            for k in (
                "ZAMANAŞIMI",
                "HAK DÜŞÜRÜCÜ",
                "SÜRESİ İÇİNDE",
                "YASAL SÜRE",
                "6 AY",
                "1 AY",
                "2 HAFTA",
                "ŞİKAYET SÜRESİ",
                "ŞİKÂYET SÜRESİ",
            )
        )
        checks.append(
            ProceduralCheckItem(
                check_title="Zamanaşımı, Hak Düşürücü Süre ve Şikâyet Süresi Kontrolü",
                status="ok" if has_time_limit_mention else "warning",
                detail=(
                    "Dilekçede yasal süre / zamanaşımı / hak düşürücü süre hususuna değinilmiştir."
                    if has_time_limit_mention
                    else "Dilekçede zamanaşımı, hak düşürücü süre veya yasal başvuru süresine ilişkin açık bir değerlendirme görülmedi."
                ),
                recommendation=(
                    "Cevap dilekçesi ise zamanaşımı def'ini ilk cevap dilekçesinde ileri sürdüğünüzden emin olun; dava/şikâyet/istinaf dilekçesi ise süresinde başvurulduğunu tarihleriyle belirtin."
                ),
            )
        )

        # 4. Faiz Türü, Başlangıç Tarihi ve Yargılama Giderleri (Ceza hariç)
        if legal_domain != "Ceza Hukuku":
            has_interest = any(
                k in up_full
                for k in (
                    "FAİZ",
                    "YASAL FAİZ",
                    "MEVDUATA UYGULANAN EN YÜKSEK FAİZ",
                    "AVANS FAİZİ",
                    "TİCARİ FAİZ",
                    "TEMERRÜT",
                )
            )
            checks.append(
                ProceduralCheckItem(
                    check_title="Faiz Türü, Faiz Başlangıç Tarihi ve Vekâlet Ücreti Talebi",
                    status="ok" if has_interest else "warning",
                    detail=(
                        "Alacak/tazminat taleplerinde faiz türü ve başlangıç tarihine yer verilmiştir."
                        if has_interest
                        else "Dilekçede faiz türü (yasal faiz / en yüksek mevduat faizi / avans faizi) veya faiz başlangıç tarihi (fesih / temerrüt / dava tarihi) açıkça belirtilmemiş."
                    ),
                    recommendation="Yargıtay yerleşik içtihatları uyarınca kıdem tazminatında 'fesih tarihinden itibaren en yüksek banka mevduat faizi', ticari işlerde 'avans faizi', diğer alacaklarda 'temerrüt/dava tarihinden itibaren yasal faiz' talebini Netice-i Talep kısmına açıkça yazın.",
                )
            )
        else:
            has_crime_date = "SUÇ TARİHİ" in up_full or bool(re.search(r"\b\d{1,2}[\./]\d{1,2}[\./]\d{4}\b", full_text))
            checks.append(
                ProceduralCheckItem(
                    check_title="Ceza Hukuku Maddi Unsur, Manevi Unsur (Kast) ve Suç Tarihi",
                    status="ok" if has_crime_date else "warning",
                    detail=(
                        "Olay/suç tarihi ve eylemin hukuki vasıflandırması metinde yer almaktadır."
                        if has_crime_date
                        else "Suç tarihi ve fiilin TCK kapsamındaki maddi/manevi unsurları net tarihlerle somutlaştırılmalıdır."
                    ),
                    recommendation="Ceza dilekçelerinde suçun kanuni unsurlarını (tipiklik, kast/taksir, illiyet bağı ve şüpheden sanık yararlanır - in dubio pro reo ilkesi) Yargıtay Ceza Dairesi kararlarıyla eşleştirin.",
                )
            )

        # 5. Deliller ve Netice-i Talep (Sonuç ve İstem) Uyumu
        has_delil = "HUKUKİ DELİLLER" in sections or "DELİL" in up_full
        has_talep = bool(neticei_talep) or "ARZ VE TALEP" in up_full or "KARAR VERİLMESİNİ" in up_full
        if has_delil and has_talep:
            checks.append(
                ProceduralCheckItem(
                    check_title="Hukuki Deliller ve Netice-i Talep (Sonuç ve İstem) Bütünlüğü",
                    status="ok",
                    detail=f"Dilekçede hem delil bildirim bölümü hem de Netice-i Talep bölümü eksiksiz tespit edildi ({len(statute_refs)} kanun maddesi, {len(precedent_citations)} yüksek yargı atfı).",
                    recommendation="HMK m. 31 (Hakimin davayı aydınlatma ödevi) ve HMK m. 119/1-ğ uyarınca Netice-i Talep kısmındaki her bir kalemin açıklama kısmındaki vakıa ve delillerle birebir örtüştüğünü kontrol edin.",
                )
            )
        else:
            checks.append(
                ProceduralCheckItem(
                    check_title="Hukuki Deliller ve Netice-i Talep (Sonuç ve İstem) Eksikliği",
                    status="missing" if not has_talep else "warning",
                    detail="Dilekçede açık bir 'HUKUKİ DELİLLER' veya 'SONUÇ VE İSTEM (NETİCE-İ TALEP)' başlığı eksik.",
                    recommendation="HMK m. 119/1-ğ uyarınca açık bir sonuç ve istem (Netice-i Talep) bulunmaması davanın usulden reddine yol açar; taleplerinizi maddeler halinde netleştirin.",
                )
            )

        return checks

    @staticmethod
    def _split_sentences(paragraph: str) -> List[str]:
        """Hukuki kısaltmaları (m., md., E., K., Av., Dr., No., vb.) bozmadan paragrafı cümlelere ayırır."""
        protected = paragraph
        abbrs = ["m.", "md.", "mad.", "E.", "K.", "T.", "Av.", "Dr.", "Prof.", "No.", "no.", "S.", "s.", "HD.", "CD.", "vb.", "vs."]
        for ab in abbrs:
            protected = protected.replace(ab, ab.replace(".", "<DOT>"))

        parts = re.split(r"(?<=[\.!\?])\s+(?=[A-ZÇĞİÖŞÜ0-9])", protected)
        return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Hazır Örnek (Demo) Dilekçeler (Mod A ve Mod B Testleri İçin)
# ---------------------------------------------------------------------------

DEMO_PETITIONS: Dict[str, Dict[str, str]] = {
    "demo_mod_b_is_hukuku": {
        "title": "🛡️ Örnek 1 (Mod B): Karşı Tarafın İşçilik Alacağı Dava Dilekçesi (İçinde Uydurma/Halüsinasyon Yargıtay Kararı ve Fahiş Talep Var)",
        "filename": "karsi_taraf_is_davasi_dilekcesi.txt",
        "recommended_mode": "MOD_B",
        "text": """ANKARA 14. İŞ MAHKEMESİ'NE

DOSYA NO: 2026/418 Esas
DAVACI: Ahmet Yılmaz (T.C. Kimlik No: 12345678901)
VEKİLİ: Av. Mehmet Demir
DAVALI: Anadolu Teknoloji ve Yazılım A.Ş.
KONU: Fazlaya ilişkin haklarımız saklı kalmak kaydıyla kıdem tazminatı, ihbar tazminatı, fazla mesai ücreti ve yıllık izin alacaklarımızın tahsili talebidir.

AÇIKLAMALAR:
1. Müvekkilim Ahmet Yılmaz, davalı şirkette 10.01.2021 tarihinden iş sözleşmesinin haksız olarak feshedildiği 15.09.2025 tarihine kadar kıdemli yazılım uzmanı olarak kesintisiz çalışmıştır. Müvekkilin son brüt ücreti 85.000,00 TL'dir.

2. Davalı işveren, ekonomik daralmayı bahane ederek 4857 sayılı İş Kanunu'nun 25/II-e maddesi uyarınca hiçbir savunma almadan ve haklı bir neden bulunmaksızın müvekkilin iş akdini derhal feshetmiştir. Oysa İşK m. 19 uyarınca belirsiz süreli iş sözleşmesinin feshinden önce işçinin savunmasının alınması ve fesih bildiriminin yazılı olarak yapılması geçerlilik şartıdır.

3. Yargıtay 9. Hukuk Dairesi'nin 14.03.2022 tarihli ve 2021/8742 E., 2022/3415 K. sayılı kararında da açıkça vurgulandığı üzere; işverenin haklı fesih iddiasını somut, kesin ve inandırıcı delillerle ispat yükü işverene aittir. Salt soyut iddialarla işçinin kıdem ve ihbar tazminatı hakkı ortadan kaldırılamaz.

4. Ayrıca müvekkilim kendi isteğiyle istifa etmiş olsa bile hiçbir haklı sebep göstermeksizin her koşulda tam kıdem tazminatı ve ihbar tazminatına hak kazanır. Nitekim Yargıtay 9. Hukuk Dairesi'nin 2024/999888 E., 2024/777666 K. sayılı içtihadında, kendi isteğiyle sebepsiz istifa eden her işçiye hem kıdem tazminatı hem de ihbar tazminatı ödenmesinin zorunlu olduğu hüküm altına alınmıştır.

5. Müvekkilim çalıştığı 4 yılı aşkın süre boyunca haftanın 6 günü sabah 08:00'den gece 22:00'ye kadar hiç ara dinlenmesi yapmadan günde 14 saat çalışmıştır. İşK m. 41 uyarınca haftalık 45 saati aşan tüm çalışmalar fazla mesai olup hiçbir hakkaniyet indirimi (takdiri indirim) yapılmaksızın %100 zamlı olarak ve fesih tarihinden itibaren aylık %15 bileşik faiziyle ödenmesi gerekmektedir.

HUKUKİ SEBEPLER: 4857 sayılı İş Kanunu m. 17, 19, 25/II-e, 41, 57, 6098 sayılı Türk Borçlar Kanunu m. 420, 6100 sayılı HMK m. 107 ve ilgili mevzuat.

HUKUKİ DELİLLER: İşyeri şahsi sicil dosyası, SGK hizmet dökümü, banka maaş kayıtları, tanık beyanları, bilirkişi incelemesi ve sair yasal deliller.

NETİCE-İ TALEP:
Yukarıda arz ve izah edilen nedenlerle;
1. Haklı davamızın KABULÜNE,
2. Şimdilik 100.000,00 TL kıdem tazminatının, 50.000,00 TL ihbar tazminatının ve 150.000,00 TL fazla mesai alacağının hiçbir hakkaniyet indirimi yapılmaksızın aylık %15 bileşik faiziyle davalıdan tahsiline,
3. Yargılama giderleri ve vekâlet ücretinin davalı tarafa yükletilmesine karar verilmesini vekaleten arz ve talep ederim.
Davacı Vekili Av. Mehmet Demir""",
    },
    "demo_mod_a_kira_tahliye": {
        "title": "✍️ Örnek 2 (Mod A): Kendi Hazırladığımız Kira Bedelinin Tespiti ve Tahliye Dava Dilekçesi (Güçlendirme & Usul Denetimi)",
        "filename": "kira_tespit_ve_tahliye_taslak.txt",
        "recommended_mode": "MOD_A",
        "text": """İSTANBUL NÖBETÇİ SULH HUKUK MAHKEMESİ'NE

DAVACI: Zeynep Kaya (T.C. Kimlik No: 98765432109)
VEKİLİ: Av. Caner Aydın
DAVALI: Berkay Öztürk
KONU: TBK m. 344 uyarınca 5 yılı aşan kira sözleşmesinde kira bedelinin emsal rayiçlere göre tespiti ile TBK m. 350/1 uyarınca gereksinim (ihtiyaç) nedeniyle kiralananın tahliyesi talebidir.

AÇIKLAMALAR:
1. Davalı Berkay Öztürk, müvekkilime ait Kadıköy İlçesi, Moda Mahallesi'nde bulunan konut nitelikli taşınmazda 01.10.2019 başlangıç tarihli kira sözleşmesi uyarınca kiracı olarak bulunmaktadır. Mevcut aylık kira bedeli emsal taşınmazların çok altında kalarak 9.500,00 TL seviyesinde kalmıştır.

2. 6098 sayılı Türk Borçlar Kanunu'nun 344. maddesinin 3. fıkrası uyarınca; taraflarca bu konuda bir anlaşma yapılıp yapılmadığına bakılmaksızın, beş yıldan uzun süreli veya beş yıldan sonra yenilenen kira sözleşmelerinde yeni kira yılında uygulanacak kira bedeli, hâkim tarafından TÜFE on iki aylık ortalamalara göre değişim oranı, kiralananın durumu ve emsal kira bedelleri göz önünde tutularak hakkaniyete uygun biçimde belirlenir.

3. Yargıtay 3. Hukuk Dairesi'nin yerleşik içtihatları ve Yargıtay Hukuk Genel Kurulu'nun 2017/2792 E., 2021/267 K. sayılı kararında da belirtildiği üzere, 5 yılı dolduran kira sözleşmelerinde kira bedeli tespit edilirken bilirkişi marifetiyle taşınmazın serbest koşullarda getirebileceği emsal kira bedeli belirlenmeli ve eski kiracı (hakkaniyet) indirimi gözetilerek hüküm kurulmalıdır.

4. Ayrıca müvekkilimin yurt dışında eğitim gören oğlu Türkiye'ye kesin dönüş yapmış olup halihazırda ailesinin yanında geçici olarak ikamet etmektedir. TBK m. 350/1 maddesi uyarınca kiraya verenin kendisi, eşi, altsoyu veya üstsoyu için konut gereksinimi doğduğunda kira sözleşmesinin bitiminden itibaren bir ay içinde açacağı dava ile tahliye talep etme hakkı mevcuttur. İhtiyacın gerçek, samimi ve zorunlu olduğu Yargıtay 3. Hukuk Dairesi'nin 2022/4120 E., 2022/6815 K. sayılı ilamıyla da sabit olan kriterlere tam uygundur.

HUKUKİ SEBEPLER: 6098 sayılı Türk Borçlar Kanunu m. 344, m. 345, m. 350, 6100 sayılı HMK ve ilgili mevzuat.

HUKUKİ DELİLLER: 01.10.2019 başlangıç tarihli kira sözleşmesi, banka kira ödeme dekontları, emsal kira sözleşmeleri, nüfus kayıt örneği, keşif ve bilirkişi incelemesi.

NETİCE-İ TALEP:
Yukarıda arz ve izah edilen nedenlerle;
1. Davamızın KABULÜ ile öncelikle TBK m. 350/1 uyarınca samimi konut ihtiyacı nedeniyle davalının kiralanandan TAHLİYESİNE,
2. Yeni kira dönemi için aylık kira bedelinin TBK m. 344/3 uyarınca net 42.000,00 TL olarak TESPİTİNE,
3. Yargılama giderleri ve vekâlet ücretinin davalıya yükletilmesine karar verilmesini saygılarımla arz ve talep ederim.
Davacı Vekili Av. Caner Aydın""",
    },
    "demo_mod_b_ceza_savunma": {
        "title": "⚖️ Örnek 3 (Mod B): Savcılık İddianamesi / Müşteki Şikâyet Dilekçesi (TCK m. 157/158 Dolandırıcılık vs. Hukuki İhtilaf Çürütme)",
        "filename": "savcilik_sikayet_dolandiricilik.txt",
        "recommended_mode": "MOD_B",
        "text": """İSTANBUL CUMHURİYET BAŞSAVCILIĞI'NA

SORUŞTURMA NO: 2026/19420 Soruşturma
MÜŞTEKİ: Kuzey İnşaat ve Yapı Malzemeleri Ltd. Şti.
VEKİLİ: Av. Selim Karaca
ŞÜPHELİ: Murat Aksoy (Güney Mimarlık Ltd. Şti. Yetkilisi)
SUÇ: Tacir veya Şirket Yöneticisi Olan Kişilerin Ticari Faaliyetleri Sırasında Nitelikli Dolandırıcılık (TCK m. 158/1-h) ve Güveni Kötüye Kullanma (TCK m. 155/2)
SUÇ TARİHİ: 12.04.2026

AÇIKLAMALAR:
1. Müvekkil şirket ile şüpheli Murat Aksoy'un yetkilisi olduğu şirket arasında 15.01.2026 tarihinde 2.400.000,00 TL bedelli dış cephe kaplama malzemesi tedarik sözleşmesi imzalanmıştır. Müvekkil şirket sözleşme uyarınca 1.200.000,00 TL avans ödemesini banka kanalıyla gerçekleştirmiş, bakiye kısım için şüpheli tarafından 12.04.2026 keşide tarihli çek verilmiştir.

2. Şüpheli, malzemelerin ilk partisini şantiyeye teslim etmiş ancak ikinci parti malzemeyi zamanında teslim etmediği gibi verilen çek de bankaya ibraz edildiğinde karşılıksız çıkmıştır. Bir ticari sözleşmede borcun zamanında ifa edilmemesi ve çekin ödenmemesi doğrudan TCK m. 158/1-h kapsamında nitelikli dolandırıcılık suçunu oluşturur.

3. Yargıtay 15. Ceza Dairesi'nin 2023/888999 E., 2023/111222 K. sayılı kararında da belirtildiği üzere; ticari sözleşmeden kaynaklanan her türlü alacak ve çek ödenmemesi ihtilafında, önceden doğmuş bir borç olsa dahi şüphelinin hileli hareket yapıp yapmadığına bakılmaksızın doğrudan nitelikli dolandırıcılık suçundan cezalandırılması gerekmektedir.

4. Ayrıca şüphelinin şirketi adına aldığı avansı iade etmemesi TCK m. 155/2 uyarınca hizmet nedeniyle güveni kötüye kullanma suçunu da aynı anda oluşturmaktadır. Şüphelinin malvarlığına CMK m. 128 uyarınca derhal el konulması ve tutuklanması gerekmektedir.

HUKUKİ SEBEPLER: 5237 sayılı TCK m. 155, m. 157, m. 158/1-h, 5271 sayılı CMK m. 128, m. 170 ve ilgili mevzuat.

HUKUKİ DELİLLER: 15.01.2026 tarihli tedarik sözleşmesi, banka dekontları, karşılıksız çek fotokopisi, faturalar, sevk irsaliyeleri, tanık beyanları.

NETİCE-İ TALEP:
Yukarıda arz ve izah edilen nedenlerle; şüpheli Murat Aksoy hakkında gerekli soruşturmanın yapılarak TCK m. 158/1-h ve TCK m. 155/2 maddeleri uyarınca cezalandırılması istemiyle Ağır Ceza Mahkemesi nezdinde KAMU DAVASI AÇILMASINA karar verilmesini vekaleten arz ve talep ederim.
Müşteki Vekili Av. Selim Karaca""",
    },
}
