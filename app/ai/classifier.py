"""Intelligent ticket intake: hybrid (rules + embedding few-shot) classification.

Why hybrid instead of asking the LLM to classify?
  * deterministic and explainable - every decision lists the signals that drove it,
  * fast (<50 ms) and works offline, and
  * produces a calibrated-ish confidence score used for human-escalation decisions.
The LLM is reserved for grounded answer generation, where language ability matters most.
"""
import re
from dataclasses import asdict, dataclass, field

import numpy as np

from app.ai.embeddings import get_embedder
from app.ai.taxonomy import (
    CATEGORIES,
    GENERAL,
    INTENT_EXEMPLARS,
    INTENTS,
    PRIORITY_MATRIX,
    find_category,
)

QUESTION_START = re.compile(
    r"^\s*(how|what|where|why|when|which|who|is there|are there|do i|does|should i|explain|tell me|any (tips|guide))\b", re.I
)
REQUEST = re.compile(
    r"\b(i need|i want|i'd like|i would like|please install|install|provision|request(ing)?|get me|"
    r"can i (get|have)|could i (get|have)|need access|licen[cs]e for|new (laptop|monitor|mouse|keyboard|headset|phone))\b",
    re.I,
)
FAILURE = re.compile(
    r"(not working|isn'?t working|cannot|can'?t|can not|unable|won'?t|doesn'?t|does not|failing|failed|fails|"
    r"error|\bdown\b|broken|crash|stuck|keeps|not connecting|not loading|no internet|denied|freez|frozen|slow|"
    r"not responding|not syncing|disconnect|expired|locked|flicker)",
    re.I,
)
PLAYBOOK_PATTERNS: dict[str, re.Pattern] = {
    "password_reset": re.compile(r"password.{0,40}(expire|forgot|forgotten|reset)|(forgot|reset|expired).{0,20}password", re.I),
    "account_unlock": re.compile(r"locked out|account.{0,20}locked|unlock.{0,20}account|lockout", re.I),
    "outlook_cache_clear": re.compile(
        r"(outlook|e-?mails?|inbox|mailbox).{0,40}(not|isn'?t|won'?t|stopped).{0,12}(sync|updat|receiv|arriv|refresh)", re.I
    ),
    "service_restart": re.compile(r"(print|printer).{0,40}(stuck|queue|not printing|spooler)", re.I),
    "app_restart": re.compile(r"teams.{0,40}(frozen|freez|not responding|hang|crash|stuck)", re.I),
    "laptop_cleanup": re.compile(r"(laptop|computer|\bpc\b|machine).{0,40}(slow|lag|sluggish)", re.I),
}
URGENCY_HIGH = re.compile(
    r"(urgent|asap|immediately|critical|since this morning|since yesterday|all day|keeps|cannot work|can'?t work|"
    r"blocked|deadline|outage|cannot|can'?t|unable|failing)",
    re.I,
)
IMPACT_ENTERPRISE = re.compile(
    r"(everyone|entire (company|organi[sz]ation)|all (users|staff|employees)|whole (company|office|building)|company-?wide|outage)",
    re.I,
)
IMPACT_DEPARTMENT = re.compile(
    r"(our team|whole team|my team|department|several (users|people|colleagues)|multiple users|we are all|none of us|all of us)",
    re.I,
)
# ordered: the first matching symptom wins
SYMPTOMS = [
    (r"authenticat|credential|sign[- ]?in|log ?in|mfa", "authentication failure"),
    (r"expire", "expired password"),
    (r"locked|lockout", "account lockout"),
    (r"forgot|reset", "password reset request"),
    (r"sync|not receiving|not updating|outbox", "synchronization issue"),
    (r"slow|lag|sluggish|performance", "performance degradation"),
    (r"frozen|freez|not responding|hang", "application not responding"),
    (r"crash", "application crash"),
    (r"denied|permission", "access denied"),
    (r"(cannot|can'?t|unable to) access", "access failure"),
    (r"stuck|queue", "stuck print queue"),
    (r"drop|disconnect", "intermittent disconnection"),
    (r"connect|no internet", "connection failure"),
    (r"install", "installation request"),
]


@dataclass
class Classification:
    intent: str
    intent_confidence: float
    category: str
    subcategory: str
    category_confidence: float
    assignment_group: str
    impact: str
    urgency: str
    priority: str
    summary: str
    suggested_resolution: str
    kb_article: str | None
    playbook: str | None
    diagnostic: str | None
    confidence: float
    intent_scores: dict = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class TicketClassifier:
    def __init__(self) -> None:
        self.embedder = get_embedder()
        self._intent_vecs: dict[str, np.ndarray] | None = None
        self._cat_vecs: np.ndarray | None = None

    def _ensure_vectors(self) -> None:
        if self._intent_vecs is None:
            self._intent_vecs = {i: self.embedder.encode(ex) for i, ex in INTENT_EXEMPLARS.items()}
            self._cat_vecs = self.embedder.encode(
                [f"{c['category']} {c['subcategory']}: {c['description']}" for c in CATEGORIES]
            )

    def classify(self, text: str, catalog_names: list[str] | None = None) -> Classification:
        self._ensure_vectors()
        text_l = text.lower()
        qvec = self.embedder.encode([text])[0]
        signals: list[str] = []

        # ---------------- intent: rule evidence
        rule = {i: 0.0 for i in INTENTS}
        is_question = bool(QUESTION_START.search(text)) or text.strip().endswith("?")
        has_failure = bool(FAILURE.search(text))
        has_request = bool(REQUEST.search(text))
        playbook = next((p for p, rx in PLAYBOOK_PATTERNS.items() if rx.search(text)), None)
        software_hit = next(
            (n for n in sorted(catalog_names or [], key=len, reverse=True) if re.search(rf"\b{re.escape(n.lower())}\b", text_l)),
            None,
        )

        if QUESTION_START.search(text):
            rule["knowledge_question"] += 1.0
            signals.append("question phrasing (how/what/where...)")
        elif text.strip().endswith("?"):
            rule["knowledge_question"] += 0.4
        if has_failure:
            rule["incident"] += 0.8
            signals.append("failure / symptom language")
        if has_request and not has_failure:
            rule["service_request"] += 1.0
            signals.append("request language (need / install / access)")
        if software_hit:
            rule["service_request"] += 0.8
            signals.append(f"catalogue item mentioned: {software_hit}")
        if playbook and not QUESTION_START.search(text):
            rule["automatable"] += 1.5
            signals.append(f"matches self-heal playbook: {playbook}")
        if not any(rule.values()):
            rule["incident"] = 0.3

        # ---------------- intent: embedding few-shot similarity
        sims = {i: float(np.max(v @ qvec)) for i, v in self._intent_vecs.items()}
        emb = _softmax(np.array([sims[i] for i in INTENTS]) * 12)
        rule_arr = np.array([rule[i] for i in INTENTS])
        rule_norm = rule_arr / rule_arr.sum()
        combined = 0.65 * rule_norm + 0.35 * emb
        order = np.argsort(combined)[::-1]
        intent = INTENTS[order[0]]
        margin = float(combined[order[0]] - combined[order[1]])
        intent_conf = 0.35 + 0.45 * float(combined[order[0]]) + 0.2 * margin
        if rule_arr.max() < 0.8:  # weak rule evidence -> rely on embeddings only, be humble
            intent_conf -= 0.15
        intent_conf = float(min(0.97, intent_conf))

        # ---------------- category
        cat_sims = self._cat_vecs @ qvec
        kw = np.array([_keyword_score(text_l, c["keywords"]) for c in CATEGORIES])
        if software_hit:
            kw[[i for i, c in enumerate(CATEGORIES) if c["subcategory"] == "Installation"][0]] += 3
        if playbook:
            for i, c in enumerate(CATEGORIES):
                if c["playbook"] == playbook:
                    kw[i] += 3
        cat_combined = 0.6 * (kw / kw.sum() if kw.sum() else kw) + 0.4 * _softmax(cat_sims * 12)
        best = int(np.argmax(cat_combined))
        if kw.max() == 0 and cat_sims.max() < 0.35:
            cat, cat_conf = GENERAL, float(max(0.2, cat_sims.max()))
            signals.append("no known IT category matched")
        else:
            cat = CATEGORIES[best]
            ranked = np.sort(cat_combined)[::-1]
            cat_conf = 0.35 + 0.45 * float(ranked[0]) + 0.2 * float(ranked[0] - ranked[1]) + (0.05 if kw.max() > 0 else -0.1)
            cat_conf = float(min(0.97, cat_conf))
            signals.append(f"category evidence: {cat['category']}/{cat['subcategory']}")

        if intent == "automatable" and cat.get("playbook") != playbook:
            cat = next((c for c in CATEGORIES if c["playbook"] == playbook), cat)
        if intent == "service_request" and software_hit:
            cat = find_category("Installation")

        # ---------------- impact / urgency / priority (ITIL matrix)
        impact = "Enterprise" if IMPACT_ENTERPRISE.search(text) else "Department" if IMPACT_DEPARTMENT.search(text) else "Individual"
        if intent in ("service_request", "knowledge_question"):
            urgency = "Low"
        else:
            urgency = "High" if URGENCY_HIGH.search(text) else "Medium"
        priority = PRIORITY_MATRIX[(impact, urgency)]

        confidence = round(0.5 * intent_conf + 0.5 * cat_conf, 3)
        return Classification(
            intent=intent,
            intent_confidence=round(intent_conf, 3),
            category=cat["category"],
            subcategory=cat["subcategory"],
            category_confidence=round(cat_conf, 3),
            assignment_group=cat["assignment_group"],
            impact=impact,
            urgency=urgency,
            priority=priority,
            summary=_summarise(text, cat, intent, software_hit),
            suggested_resolution=cat["resolution"],
            kb_article=cat["kb"],
            playbook=playbook if intent == "automatable" else None,
            diagnostic=cat.get("diagnostic"),
            confidence=confidence,
            intent_scores={i: round(float(s), 3) for i, s in zip(INTENTS, combined)},
            signals=signals,
        )


def _keyword_score(text: str, keywords: list[str]) -> float:
    return float(sum((2.0 if " " in k else 1.0) for k in keywords if k in text))


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def _summarise(text: str, cat: dict, intent: str, software: str | None) -> str:
    if intent == "service_request" and software:
        return f"Software request: {software}"
    symptom = next((label for rx, label in SYMPTOMS if re.search(rx, text, re.I)), None)
    if cat is GENERAL:
        first = re.split(r"[.!?]", text.strip())[0]
        return first[:80]
    subject = cat["subcategory"]
    if symptom:
        words = [w for w in subject.split() if w.lower() not in symptom]
        phrase = " ".join(words + [symptom])
        return phrase[0].upper() + phrase[1:]
    return f"{subject} issue" if intent != "service_request" else f"{subject} request"


_classifier: TicketClassifier | None = None


def get_classifier() -> TicketClassifier:
    global _classifier
    if _classifier is None:
        _classifier = TicketClassifier()
    return _classifier
