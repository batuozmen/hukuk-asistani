"""
MODÜL 5: Dilekçe ve Resmi İçtihat Üzerinden Kanıtlı Hukuki Soru-Cevap Asistanı (legal_chat.py)
----------------------------------------------------------------------------------------------
Görevleri:
1. Avukatın yüklediği dilekçe/dava dosyası (`ParsedLegalDocument`), denetim sonuçları
   (`LegalClaimVerificationResult`), çekilen gerçek yüksek yargı kararları (`FetchedPrecedent`),
   resmi kanun maddeleri (`FetchedStatute`) ve üretilen resmi dilekçe (`GeneratedPetitionPackage`)
   üzerinde çalışan interaktif, sıfır halüsinasyonlu hukuk asistanıdır.
2. Verdiği her cevabın içine resmi kaynak referanslarını (`[Paragraf 4 / IDDIA_5]`,
   `[Yargıtay 9. HD, E. 2023/4512, K. 2023/6784]`, `[4857 S.K. (İşK) m. 41]`) yerleştirir
   ve kullandığı kanıtları `LegalCitationBadge` listesi olarak ayrıca döndürür.
3. Eğer avukatın sorusunda dosyada henüz yer almayan yeni bir hukuki konu veya kanun maddesi
   geçiyorsa, `PrecedentFetcher.search_precedents_for_claim()` ile anında resmi veritabanlarından
   ve doğrulanmış katalogdan gerçek kararları çekip kanıt havuzuna dahil eder.
4. Yerel Ollama (`qwen2.5:3b`) aktifse 90 sn timeout koruması ve "Sıfır Yabancı Esas/Karar
   Numarası Güvenlik Filtresi" ile yanıtı zenginleştirir; kaynakta olmayan hiçbir bilgiyi uydurmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

try:
    import ollama
except ImportError:
    ollama = None  # type: ignore

from legal_parser import (
    ParsedLegalDocument,
    StatuteReference,
    _tr_upper,
)
from precedent_fetcher import (
    PrecedentFetcher,
    FetchedPrecedent,
    FetchedStatute,
)
from legal_rag_verifier import (
    LegalClaimVerificationResult,
    LegalRAGVerifier,
    normalize_legal_text,
    _call_with_timeout,
    LLM_TIMEOUT,
)
from petition_drafter import (
    GeneratedPetitionPackage,
    get_legal_verdict_info,
)


# ---------------------------------------------------------------------------
# Veri Yapıları (@dataclass)
# ---------------------------------------------------------------------------

@dataclass
class LegalCitationBadge:
    """Soru-cevap asistanının yanıtında dayanak gösterdiği tek bir doğrulanmış kaynak."""
    source_type: str                  # "Dilekçe Paragrafı" | "Yüksek Yargı İçtihadı" | "Kanun Maddesi" | "Usul Denetimi"
    reference_code: str               # Örn: "[Yargıtay 9. HD, T. 10.05.2023, E. 2023/4512, K. 2023/6784]"
    quote_snippet: str                # Kaynaktan alınan kanıt metni

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LegalChatResponse:
    """Avukatın sorusuna verilen kanıtlı hukuki yanıt paketi."""
    question: str
    answer_markdown: str
    citations: List[LegalCitationBadge] = field(default_factory=list)
    suggested_followup_questions: List[str] = field(default_factory=list)
    used_llm_model: str = ""
    decision_source: str = "kural+rag"  # "kural+rag" | "kural+rag+llm"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question": self.question,
            "answer_markdown": self.answer_markdown,
            "citations": [c.to_dict() for c in self.citations],
            "suggested_followup_questions": list(self.suggested_followup_questions),
            "used_llm_model": self.used_llm_model,
            "decision_source": self.decision_source,
        }


# ---------------------------------------------------------------------------
# Ana Kanıtlı Hukuki Soru-Cevap Asistanı Sınıfı (LegalChatAssistant)
# ---------------------------------------------------------------------------

class LegalChatAssistant:
    """
    Yüklü dava dosyası ve doğrulanmış yüksek yargı kararları üzerinde çalışan
    sıfır halüsinasyonlu hukuki soru-cevap motoru.
    """

    def __init__(
        self,
        fetcher: Optional[PrecedentFetcher] = None,
        verifier: Optional[LegalRAGVerifier] = None,
        use_llm: bool = True,
    ):
        self.fetcher = fetcher or PrecedentFetcher(timeout=4)
        self.verifier = verifier or LegalRAGVerifier(use_llm=use_llm)
        self.use_llm = use_llm

    # -----------------------------------------------------------------------
    # 1. Dosyaya Özel Hızlı Soru Önerileri (Arayüzde Tek Tıkla Sormak İçin)
    # -----------------------------------------------------------------------

    @staticmethod
    def get_quick_questions(
        parsed_doc: Optional[ParsedLegalDocument],
        mode: str = "MOD_B",
    ) -> List[str]:
        """Yüklü dilekçenin hukuk dalına ve çalışma moduna göre 5 kritik soru önerir."""
        if parsed_doc is None:
            return [
                "İşK m. 25/II haklı nedenle derhal fesihte işçiden savunma alınması zorunlu mudur?",
                "Beş yılı dolduran kira sözleşmesinde kira tespit davası (TBK m. 344/3) şartları nelerdir?",
                "Ticari sözleşmede malın eksik teslimi ve çekin ödenmemesi TCK m. 158 dolandırıcılık suçunu oluşturur mu?",
                "Fazla mesai alacağında %30 hakkaniyet indirimi ve faiz türü nasıl uygulanır?",
                "Kendi isteğiyle istifa eden işçi kıdem ve ihbar tazminatı talep edebilir mi?",
            ]

        if mode == "MOD_B":
            return [
                "Karşı tarafın dilekçesinde uydurma (sahte / halüsinasyon) Yargıtay kararı var mı?",
                "Karşı tarafın yerleşik Yargıtay içtihatlarıyla ve kanunla çelişen en zayıf iddiaları hangileri?",
                "Cevap / savunma dilekçemizde hangi usul, dava şartı ve zamanaşımı itirazlarını ileri sürmeliyiz?",
                "Karşı tarafın taleplerini çürütmek için hangi gerçek Esas/Karar numaralı Yargıtay kararlarını sunmalıyız?",
                "Bu dosyada mahkemeye / savcılığa sunacağımız en güçlü Netice-i Talep ve savunma stratejisi ne olmalı?",
            ]
        return [
            "Kendi dilekçemde usulden ret veya hak kaybı doğurabilecek bir dava şartı eksikliği var mı?",
            "Dilekçemdeki iddiaları güçlendiren en kritik Yargıtay / HGK kararları hangileri?",
            "Dilekçemde düzeltmem veya çıkarmam gereken riskli / çelişkili bir ifade var mı?",
            "Yargıtay'a göre bu davada ispat yükü kimde ve dilekçe ekine hangi delilleri koymalıyım?",
            "Netice-i Talep kısmında faiz türü, başlangıç tarihi ve talepler nasıl yazılmalı?",
        ]

    # -----------------------------------------------------------------------
    # 2. Ana Soru Cevaplama Boru Hattı (answer_question)
    # -----------------------------------------------------------------------

    def answer_question(
        self,
        question: str,
        parsed_doc: Optional[ParsedLegalDocument] = None,
        verification_results: Optional[List[LegalClaimVerificationResult]] = None,
        cited_precedents_map: Optional[Dict[str, FetchedPrecedent]] = None,
        claim_precedents_map: Optional[Dict[str, List[FetchedPrecedent]]] = None,
        statutes_map: Optional[Dict[str, FetchedStatute]] = None,
        generated_package: Optional[GeneratedPetitionPackage] = None,
        mode: str = "MOD_B",
    ) -> LegalChatResponse:
        """
        Avukatın sorusunu:
        1. Yüklü dosya + doğrulama sonuçları + çekilen resmi içtihat/mevzuat havuzunda arar,
        2. Soruya özel yeni emsal karar gerekiyorsa `PrecedentFetcher` ile anında çeker,
        3. Tüm iddialarını resmi `[Esas/Karar No]`, `[Kanun Maddesi]` ve `[Paragraf No]`
           etiketleriyle kanıtlandırarak yanıtlar.
        """
        q_clean = (question or "").strip()
        if not q_clean:
            return LegalChatResponse(
                question="",
                answer_markdown="Lütfen dosya, dilekçe veya içtihatlarla ilgili bir hukuk sorusu yazın.",
            )

        v_results = list(verification_results or [])
        s_map = dict(statutes_map or {})
        cited_map = dict(cited_precedents_map or {})
        c_precs_map = dict(claim_precedents_map or {})

        # A. Sorunun kendisi için de doğrulanmış içtihat havuzundan en yakın kararları çek
        domain_hint = parsed_doc.legal_domain if parsed_doc else ""
        extra_precs = self.fetcher.search_precedents_for_claim(
            claim_text=q_clean,
            legal_domain=domain_hint,
            max_results=3,
            try_live_api=False,
        )

        # B. Birleşik Kanıt Havuzunu (Knowledge Corpus) oluştur ve soruya göre sırala
        corpus_badges = self._build_and_rank_corpus(
            question=q_clean,
            parsed_doc=parsed_doc,
            verification_results=v_results,
            cited_map=cited_map,
            claim_precedents_map=c_precs_map,
            statutes_map=s_map,
            extra_precedents=extra_precs,
        )

        # C. Sorunun niyetine göre (Sahte karar sorgusu, Çelişki/Çürütme sorgusu, Usul sorgusu, Genel içtihat sorgusu)
        #    %100 kanıtlı deterministik hukukçu yanıtını oluştur
        deterministic_md, used_badges = self._compose_grounded_legal_answer(
            question=q_clean,
            parsed_doc=parsed_doc,
            verification_results=v_results,
            statutes_map=s_map,
            extra_precedents=extra_precs,
            top_badges=corpus_badges[:6],
            generated_package=generated_package,
            mode=mode,
        )

        final_md = deterministic_md
        used_model = ""
        dec_source = "kural+rag"

        # D. Eğer yerel Ollama aktifse, deterministik kanıtları bağlam vererek yanıtı zenginleştir (Sıfır halüsinasyon filtreli)
        if self.use_llm and self.verifier.active_ollama_model:
            llm_md = self._enhance_with_ollama(
                question=q_clean,
                deterministic_md=deterministic_md,
                badges=used_badges,
                mode=mode,
            )
            if llm_md:
                final_md = llm_md
                used_model = self.verifier.active_ollama_model
                dec_source = "kural+rag+llm"

        followups = [
            q for q in self.get_quick_questions(parsed_doc, mode=mode)
            if _tr_upper(q[:25]) != _tr_upper(q_clean[:25])
        ][:3]

        return LegalChatResponse(
            question=q_clean,
            answer_markdown=final_md,
            citations=used_badges,
            suggested_followup_questions=followups,
            used_llm_model=used_model,
            decision_source=dec_source,
        )

    # -----------------------------------------------------------------------
    # 3. Birleşik Kanıt Havuzu Oluşturma ve Sıralama (_build_and_rank_corpus)
    # -----------------------------------------------------------------------

    def _build_and_rank_corpus(
        self,
        question: str,
        parsed_doc: Optional[ParsedLegalDocument],
        verification_results: List[LegalClaimVerificationResult],
        cited_map: Dict[str, FetchedPrecedent],
        claim_precedents_map: Dict[str, List[FetchedPrecedent]],
        statutes_map: Dict[str, FetchedStatute],
        extra_precedents: List[FetchedPrecedent],
    ) -> List[LegalCitationBadge]:
        """Tüm dosya paragraflarını, emsal kararları, kanun maddelerini ve usul kontrollerini puanlar."""
        candidates: List[Tuple[float, LegalCitationBadge]] = []
        seen_refs: set[str] = set()
        norm_q = normalize_legal_text(question)

        def _add_candidate(source_type: str, ref_code: str, snippet: str, bonus: float = 0.0) -> None:
            if not snippet or ref_code in seen_refs:
                return
            seen_refs.add(ref_code)
            sim = self.verifier._fallback_lexical_similarity(norm_q, normalize_legal_text(f"{ref_code} {snippet}"))
            candidates.append(
                (
                    sim + bonus,
                    LegalCitationBadge(
                        source_type=source_type,
                        reference_code=ref_code,
                        quote_snippet=snippet,
                    ),
                )
            )

        # 1. Doğrulanan İddia Bentleri
        for r in verification_results:
            v_info = get_legal_verdict_info(r.verdict)
            ref_c = f"[Paragraf {r.paragraph_index} / {r.claim_id} — {v_info['short_label']}]"
            snip = (
                f"Dilekçe Metni: \"{r.claim_text}\" | Hukuki Tahlil: {r.legal_analysis} | "
                f"Dayanak Karar: {r.best_precedent_label}"
            )
            bonus = 0.15 if r.verdict in ("SAHTE_VEYA_CARPITILMIS_ATIF", "ICTIHAT_VE_KANUNLA_CELISIYOR") else 0.05
            _add_candidate("Dilekçe Paragrafı", ref_c, snip, bonus=bonus)

        # 2. Çekilen Tüm Yüksek Yargı Kararları
        all_precs: List[FetchedPrecedent] = list(cited_map.values()) + list(extra_precedents)
        for plist in claim_precedents_map.values():
            all_precs.extend(plist)

        for fp in all_precs:
            if fp.lookup_status == "fake_or_mismatch":
                ref_c = f"[SAHTE ATIF TESPİTİ: {fp.query_text}]"
                _add_candidate("Yüksek Yargı İçtihadı", ref_c, fp.hallucination_warning, bonus=0.20)
            elif fp.verified_online:
                ref_c = f"[{fp.citation_label}]"
                _add_candidate(
                    "Yüksek Yargı İçtihadı",
                    ref_c,
                    fp.full_text or fp.summary_principle,
                    bonus=0.12,
                )

        # 3. Resmi Kanun Maddeleri
        for st in statutes_map.values():
            ref_c = f"[{st.law_number} S.K. ({st.law_code}) m. {st.article} — {st.title}]"
            _add_candidate(
                "Kanun Maddesi",
                ref_c,
                f"{st.official_text} | Uygulama Notu: {st.practical_note}",
                bonus=0.10,
            )

        # 4. Usul Denetimi Bulguları
        if parsed_doc:
            for pc in parsed_doc.procedural_checks:
                ref_c = f"[Usul Denetimi: {pc.check_title}]"
                _add_candidate(
                    "Usul Denetimi",
                    ref_c,
                    f"Durum ({pc.status.upper()}): {pc.detail} — Tavsiye: {pc.recommendation}",
                    bonus=0.08,
                )

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates]

    # -----------------------------------------------------------------------
    # 4. Kanıtlı ve Sıfır Halüsinasyonlu Hukukçu Yanıtı Kurgulayıcı
    # -----------------------------------------------------------------------

    def _compose_grounded_legal_answer(
        self,
        question: str,
        parsed_doc: Optional[ParsedLegalDocument],
        verification_results: List[LegalClaimVerificationResult],
        statutes_map: Dict[str, FetchedStatute],
        extra_precedents: List[FetchedPrecedent],
        top_badges: List[LegalCitationBadge],
        generated_package: Optional[GeneratedPetitionPackage],
        mode: str,
    ) -> Tuple[str, List[LegalCitationBadge]]:
        """Sorunun niyetine göre kaynak etiketli Markdown hukuki mütalaa üretir."""
        up_q = _tr_upper(question)
        used_badges: List[LegalCitationBadge] = []

        def _add_badge(b: LegalCitationBadge) -> None:
            if b.reference_code not in {x.reference_code for x in used_badges}:
                used_badges.append(b)

        # NİYET 1: Sahte / Uydurma / Halüsinasyon Karar Sorgusu
        if any(k in up_q for k in ("SAHTE", "UYDURMA", "HALÜSİNASYON", "GERÇEK Mİ", "DOĞRU MU", "VAR MI")):
            fakes = [r for r in verification_results if r.verdict == "SAHTE_VEYA_CARPITILMIS_ATIF"]
            if fakes:
                lines = [
                    "### 🚨 Sahte / Uydurma İçtihat (Yapay Zekâ Halüsinasyonu) Tespit Raporu",
                    f"İncelenen dilekçede resmi Yargıtay ve UYAP Emsal kayıtlarında bulunmayan **{len(fakes)} adet sahte/uydurma karar atfı** tespit edilmiştir:",
                    "",
                ]
                for fr in fakes:
                    lines.extend(
                        [
                            f"- **[Paragraf {fr.paragraph_index} / {fr.claim_id}]:** {fr.legal_analysis}",
                            f"  - **Doğrulanmış Gerçek Yüksek Yargı İçtihadı:** `[{fr.best_precedent_label}]`",
                            f"  - **Avukat Aksiyon Tavsiyesi:** {fr.lawyer_action_advice}",
                            f"  - **Dilekçeye Eklenecek Resmi İfşa Paragrafı:**\n    > *\"{fr.draft_paragraph_suggestion}\"*",
                            "",
                        ]
                    )
                    _add_badge(
                        LegalCitationBadge(
                            source_type="Dilekçe Paragrafı",
                            reference_code=f"[Paragraf {fr.paragraph_index} / {fr.claim_id}]",
                            quote_snippet=fr.legal_analysis,
                        )
                    )
                    _add_badge(
                        LegalCitationBadge(
                            source_type="Yüksek Yargı İçtihadı",
                            reference_code=f"[{fr.best_precedent_label}]",
                            quote_snippet=fr.best_evidence_text,
                        )
                    )
                return "\n".join(lines).strip(), used_badges
            elif parsed_doc is not None:
                for b in top_badges[:3]:
                    _add_badge(b)
                return (
                    "### ✅ İçtihat Numarası Doğrulama Sonucu\n"
                    f"`{parsed_doc.filename}` içerisinde atıf yapılan tüm yüksek yargı karar numaraları "
                    "kontrol edilmiş olup **sahte veya uydurma (halüsinasyon) bir Esas/Karar numarasına rastlanmamıştır.**\n\n"
                    + "\n".join(f"- **{b.reference_code}:** {b.quote_snippet[:240]}" for b in used_badges),
                    used_badges,
                )

        # NİYET 2: Usul, Dava Şartı, Arabuluculuk, Zamanaşımı veya Faiz Sorgusu (Öncelikli kontrol)
        if parsed_doc and any(k in up_q for k in ("USUL", "DAVA ŞARTI", "ARABULUCU", "ZAMANAŞIMI", "FAİZ", "GÖREV", "SÜRE")):
            lines = [
                f"### ⚖️ `{parsed_doc.filename}` Usul, Dava Şartı ve Süre Denetimi",
                f"- **Hitap Makamı:** `{parsed_doc.authority}` | **Hukuk Dalı:** `{parsed_doc.legal_domain}` | **Evrak Türü:** `{parsed_doc.document_type}`",
                "",
            ]
            for pc in parsed_doc.procedural_checks:
                icon = "✅" if pc.status == "ok" else ("⚠️" if pc.status == "warning" else "🚨")
                lines.append(f"- {icon} **[{pc.check_title}]:** {pc.detail}\n  - *Hukuki Tavsiye:* {pc.recommendation}")
                _add_badge(
                    LegalCitationBadge(
                        source_type="Usul Denetimi",
                        reference_code=f"[{pc.check_title}]",
                        quote_snippet=f"{pc.detail} ({pc.recommendation})",
                    )
                )
            for b in top_badges[:3]:
                _add_badge(b)
            return "\n".join(lines).strip(), used_badges

        # NİYET 3: Çelişkiler, Zayıf Noktalar ve Çürütme Stratejisi Sorgusu
        if any(k in up_q for k in ("ÇELİŞ", "ZAYIF", "ÇÜRÜT", "HATA", "RİSK", "SAVUNMA", "CEVAP")):
            bad_items = [
                r
                for r in verification_results
                if r.verdict in ("SAHTE_VEYA_CARPITILMIS_ATIF", "ICTIHAT_VE_KANUNLA_CELISIYOR", "EK_ISPAT_VE_USUL_UYARISI")
            ]
            if bad_items:
                lines = [
                    "### 🛡️ Tespit Edilen Hukuki Çelişkiler, Açıklar ve Çürütme / Düzeltme Stratejisi",
                    "Yüklü evrak üzerinde yapılan madde madde incelemede yüksek yargı içtihatları ve kanun hükümleriyle çelişen veya usul riski taşıyan noktalar şunlardır:",
                    "",
                ]
                for r in bad_items:
                    v_info = get_legal_verdict_info(r.verdict)
                    lines.extend(
                        [
                            f"#### {v_info['badge']} — `[Paragraf {r.paragraph_index} / {r.claim_id}]`",
                            f"- **İncelenen İddia:** *\"{r.claim_text}\"*",
                            f"- **Hukuki Tahlil ve Dayanak:** {r.legal_analysis} (`[{r.best_precedent_label}]`)",
                            f"- **Avukat Stratejisi:** {r.lawyer_action_advice}",
                            f"- **Hazır Resmi Dilekçe Paragrafı:**\n  > *\"{r.draft_paragraph_suggestion}\"*",
                            "",
                        ]
                    )
                    _add_badge(
                        LegalCitationBadge(
                            source_type="Yüksek Yargı İçtihadı",
                            reference_code=f"[{r.best_precedent_label}]",
                            quote_snippet=r.best_evidence_text,
                        )
                    )
                return "\n".join(lines).strip(), used_badges

        # NİYET 4: Genel / Spesifik Hukuki Soruya Doğrudan Emsal Karar ve Kanun Maddesiyle Yanıt
        for b in top_badges[:4]:
            _add_badge(b)
        for ep in extra_precedents[:2]:
            _add_badge(
                LegalCitationBadge(
                    source_type="Yüksek Yargı İçtihadı",
                    reference_code=f"[{ep.citation_label}]",
                    quote_snippet=ep.full_text or ep.summary_principle,
                )
            )

        lines = [
            "### ⚖️ Kanıtlı Hukuki Değerlendirme ve Yüksek Yargı İçtihadı",
            f"Sorunuz (**\"{question}\"**) kapsamında dosyadaki veriler ve doğrulanmış resmi yüksek yargı içtihatları incelenmiştir:",
            "",
        ]

        if used_badges:
            for idx_b, b in enumerate(used_badges, start=1):
                lines.append(
                    f"{idx_b}. **{b.source_type} — `{b.reference_code}`:**\n   {b.quote_snippet}"
                )
        else:
            lines.append(
                "Bu soruya ilişkin yüklü dosyada veya doğrulanmış içtihat havuzunda doğrudan eşleşen bir kayıt "
                "bulunamadı. **Sıfır Halüsinasyon İlkesi** gereğince sistem ezberden karar numarası üretmez."
            )

        # Eğer ilgili doğrulanmış bir dilekçe paragrafı önerisi varsa ekle
        if verification_results:
            best_r = max(
                verification_results,
                key=lambda r: self.verifier._fallback_lexical_similarity(question, r.claim_text + " " + r.legal_analysis),
            )
            lines.extend(
                [
                    "",
                    f"#### ✍️ Dilekçede Kullanabileceğiniz Hazır Resmi Paragraf (`[Paragraf {best_r.paragraph_index} / {best_r.best_precedent_label}]`):",
                    f"> *\"{best_r.draft_paragraph_suggestion}\"*",
                ]
            )

        return "\n".join(lines).strip(), used_badges

    # -----------------------------------------------------------------------
    # 5. Sıfır Halüsinasyon Filtreli Yerel Ollama (qwen2.5:3b) Yanıt Zenginleştirici
    # -----------------------------------------------------------------------

    def _enhance_with_ollama(
        self,
        question: str,
        deterministic_md: str,
        badges: List[LegalCitationBadge],
        mode: str,
    ) -> Optional[str]:
        """
        Yerel Ollama modeline yalnızca doğrulanmış `badges` kanıtlarını verir.
        Modelin yanıtında kanıt havuzunda olmayan tek bir yabancı `YYYY/NNNN` numarası
        bile çıkarsa yanıtı reddeder ve `deterministic_md` yanıtını korur.
        """
        if ollama is None or not self.verifier.active_ollama_model or not badges:
            return None

        evidence_context = "\n\n".join(
            f"KAYNAK {i} {b.reference_code} ({b.source_type}):\n{b.quote_snippet}"
            for i, b in enumerate(badges, start=1)
        )
        prompt = (
            "Sen kıdemli bir Türk Hukuku Başdanışman Avukatısın.\n"
            "KESİN EMİR: Yalnızca aşağıda verilen KAYNAK metinlerindeki gerçek Esas/Karar numaralarını ve "
            "kanun maddelerini kullan. Kaynaklarda yer almayan HİÇBİR karar numarasını uydurma! "
            "Her hukuki bilginin sonuna ilgili kaynağın köşeli parantezli referans kodunu (Örn: [Yargıtay 9. HD, ...]) yaz.\n\n"
            f"AVUKATIN SORUSU: {question}\n\n"
            f"DOĞRULANMIŞ KANIT HAVUZU:\n{evidence_context}\n\n"
            f"ÖN TASLAK YANIT:\n{deterministic_md}\n\n"
            "Yukarıdaki ön taslak yanıtı ve kanıt havuzunu kullanarak, hiçbir karar numarasını değiştirmeden "
            "veya uydurmadan, avukata net, maddeli ve profesyonel Türkçe Markdown formatında cevap ver:"
        )

        def _invoke() -> Any:
            return ollama.chat(
                model=self.verifier.active_ollama_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 600},
            )

        status, resp = _call_with_timeout(_invoke, timeout=LLM_TIMEOUT)
        if status != "ok" or not resp:
            return None

        try:
            content = (
                resp.get("message", {}).get("content", "")
                if isinstance(resp, dict)
                else getattr(getattr(resp, "message", None), "content", "")
            )
            llm_text = str(content or "").strip()
            if len(llm_text) < 80:
                return None

            # Sıfır halüsinasyon kontrolü: izin verilen Esas/Karar numaraları dışındaki numaraları denetle
            allowed_nums = set(re.findall(r"\d{4}/\d+", evidence_context + " " + deterministic_md))
            llm_nums = set(re.findall(r"\d{4}/\d+", llm_text))
            if not llm_nums.issubset(allowed_nums):
                return None

            return llm_text
        except Exception:
            return None
