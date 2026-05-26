import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlparse

from app.schemas import Evidence


KNOWN_ALIASES = {
    "飞书": ["飞书", "feishu", "lark"],
    "钉钉": ["钉钉", "dingtalk"],
    "企业微信": ["企业微信", "wecom", "wechat work", "weixin work"],
}


@dataclass(frozen=True)
class EvidenceRelevanceResult:
    relevance_score: float
    relevance_level: str
    relevance_reason: str
    entity_match_signals: dict


def normalize_competitor_name(name: str) -> str:
    text = name.strip().lower()
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return re.sub(r"\s+", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def generate_competitor_aliases(name: str) -> list[str]:
    aliases = [name.strip()]
    aliases.extend(KNOWN_ALIASES.get(name.strip(), []))
    normalized = normalize_competitor_name(name)
    if normalized:
        aliases.append(normalized)
    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        clean = alias.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)
    return deduped


def score_evidence_relevance(evidence: Evidence, competitor: str, aliases: list[str] | None = None, title: str = "") -> EvidenceRelevanceResult:
    aliases = aliases or generate_competitor_aliases(competitor)
    url = evidence.url or ""
    domain = evidence.source_domain or _domain(url)
    snippet = evidence.snippet or ""

    title_text = title.lower()
    snippet_text = snippet.lower()
    url_text = url.lower()
    domain_text = domain.lower()
    normalized_domain = normalize_competitor_name(domain_text)
    normalized_competitor = normalize_competitor_name(competitor)

    competitor_in_title = _contains_alias(title_text, aliases)
    competitor_in_snippet = _contains_alias(snippet_text, aliases)
    competitor_in_url = _contains_alias(url_text, aliases)
    competitor_in_domain = _contains_alias(domain_text, aliases) or _contains_alias(normalized_domain, aliases)
    competitor_alias_matched = any([competitor_in_title, competitor_in_snippet, competitor_in_url, competitor_in_domain])
    domain_similarity_score = _similarity(normalized_competitor, normalized_domain)

    score = 0.0
    if competitor_in_title:
        score += 0.35
    if competitor_in_snippet:
        score += 0.35
    if competitor_in_url:
        score += 0.20
    if competitor_in_domain:
        score += 0.20
    if domain_similarity_score >= 0.75:
        score += 0.10

    if not competitor_alias_matched:
        score = min(score, 0.35)
    score = round(max(0.0, min(1.0, score)), 2)

    if score >= 0.75:
        level = "high"
    elif score >= 0.45:
        level = "medium"
    elif score >= 0.25:
        level = "low"
    else:
        level = "unrelated"

    signals = {
        "competitor_in_title": competitor_in_title,
        "competitor_in_snippet": competitor_in_snippet,
        "competitor_in_url": competitor_in_url,
        "competitor_in_domain": competitor_in_domain,
        "competitor_alias_matched": competitor_alias_matched,
        "domain_similarity_score": round(domain_similarity_score, 2),
    }
    reason = _reason(competitor, aliases, signals, level)
    return EvidenceRelevanceResult(
        relevance_score=score,
        relevance_level=level,
        relevance_reason=reason,
        entity_match_signals=signals,
    )


def apply_relevance(evidence: Evidence, competitor: str, title: str = "") -> Evidence:
    result = score_evidence_relevance(evidence, competitor, title=title)
    data = evidence.model_dump()
    data.update(
        {
            "relevance_score": result.relevance_score,
            "relevance_level": result.relevance_level,
            "relevance_reason": result.relevance_reason,
            "entity_match_signals": result.entity_match_signals,
        }
    )
    return Evidence(**data)


def is_relevant_evidence(evidence: Evidence) -> bool:
    return evidence.relevance_level in {"high", "medium"}


def _contains_alias(text: str, aliases: list[str]) -> bool:
    normalized_text = normalize_competitor_name(text)
    for alias in aliases:
        clean = alias.lower().strip()
        normalized_alias = normalize_competitor_name(clean)
        if clean and clean in text:
            return True
        if normalized_alias and normalized_alias in normalized_text:
            return True
    return False


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _reason(competitor: str, aliases: list[str], signals: dict, level: str) -> str:
    matched = [key for key, value in signals.items() if key.startswith("competitor_in_") and value]
    if matched:
        return f"{competitor} matched by {', '.join(matched)}; aliases={aliases}; relevance={level}."
    return f"No competitor or alias match for {competitor}; evidence is {level}."
