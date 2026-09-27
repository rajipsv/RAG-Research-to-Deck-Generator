"""Gemini synthesis: findings -> slide titles, bullets, and citation mapping."""

from __future__ import annotations

import json
import re

import gemini

SYSTEM_PROMPT = (
    "You are a research analyst preparing a slide deck from academic literature. "
    "You will be given numbered findings, each drawn from one paper, plus a list "
    "of cross-cutting concepts that recur across multiple findings. Organize the "
    "deck around those concepts, not around individual papers — each slide should "
    "synthesize what several papers say about one concept (compare, contrast, or "
    "combine their perspectives), not restate a single paper's abstract. Every "
    "claim you make must be traceable to at least one numbered finding via its "
    "index — do not introduce facts, statistics, or citations that are not present "
    "in the provided findings. Prefer concrete detail (named methods, mechanisms, "
    "metrics, numbers) over generic restatements. If the findings are thin on a "
    "topic, say less rather than inventing detail."
)


def _build_findings_block(findings: list[dict]) -> tuple[str, list[dict]]:
    """Assign a stable citation index to each unique paper, in first-appearance order."""
    references: list[dict] = []
    paper_index: dict[str, int] = {}
    lines = []

    for finding in findings:
        paper_id = finding["paper_id"]
        if paper_id not in paper_index:
            paper_index[paper_id] = len(references) + 1
            references.append(
                {
                    "index": paper_index[paper_id],
                    "title": finding.get("title") or "Untitled",
                    "authors": finding.get("authors") or "Unknown authors",
                    "year": finding.get("year"),
                    "url": finding.get("url"),
                }
            )
        idx = paper_index[paper_id]
        lines.append(f"[{idx}] ({finding.get('title')}, {finding.get('year')}): {finding['content']}")

    return "\n\n".join(lines), references


def _identify_themes(topic: str, findings_block: str, paper_count: int) -> list[str]:
    """Ask Gemini for 5-8 cross-cutting concepts each supported by >=2 papers.

    Falls back to an empty list on any failure — synthesis still works without
    themes, it just reverts to organizing however the model sees fit.
    """
    prompt = (
        f"Topic: {topic}\n\n"
        f"Numbered findings drawn from {paper_count} different papers:\n{findings_block}\n\n"
        "Identify 5 to 8 cross-cutting CONCEPTS or THEMES that recur across "
        "MULTIPLE of these findings — e.g. a shared method, a shared challenge, a "
        "shared application area, a point of agreement or disagreement. Do not "
        "propose a theme that only one finding supports. Return ONLY a JSON array "
        "of short theme names (3-6 words each), nothing else."
    )
    try:
        text = gemini.generate_text(prompt, max_output_tokens=300, json_mode=True).strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        themes = json.loads(match.group(0)) if match else []
        if isinstance(themes, list):
            return [str(t) for t in themes][:8]
    except Exception:
        pass
    return []


def synthesize_deck(topic: str, findings: list[dict]) -> dict:
    if not findings:
        raise ValueError(f"No findings retrieved for topic '{topic}' — cannot synthesize a deck.")

    findings_block, references = _build_findings_block(findings)
    valid_indices = {r["index"] for r in references}

    themes = _identify_themes(topic, findings_block, len(references))
    themes_block = (
        "Cross-cutting concepts to organize the deck around (merge or drop one if "
        "it turns out to lack support):\n" + "\n".join(f"- {t}" for t in themes)
        if themes
        else "No pre-identified concepts — infer cross-cutting themes yourself; do "
        "not default to one slide per paper."
    )

    user_prompt = (
        f"Topic: {topic}\n\n"
        f"Numbered findings:\n{findings_block}\n\n"
        f"{themes_block}\n\n"
        "Produce a slide deck with 5 to 8 content slides (not counting title or "
        "references), each built around one concept above. Each slide must "
        "synthesize findings from at least two different papers wherever the "
        "concept has that support — compare, contrast, or combine their "
        "perspectives rather than paraphrasing a single paper's abstract. Only "
        "cite a single paper on a slide if truly no other finding relates to that "
        "slide's concept. Bullets should surface concrete detail (named methods, "
        "mechanisms, metrics, numbers) from the findings, not generic "
        "restatements. Return ONLY valid JSON matching this shape, nothing else:\n"
        "{\n"
        '  "deck_title": string,\n'
        '  "slides": [\n'
        "    {\n"
        '      "title": string,\n'
        '      "bullets": [string, ...],  // 3-5 bullets, each a complete claim\n'
        '      "citation_indices": [int, ...]  // indices into the numbered findings above\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Every bullet's claim must map to at least one citation index that actually "
        "supports it. Do not use an index that was not given above."
    )

    raw_text = gemini.generate_text(
        user_prompt,
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=4000,
        json_mode=True,
    ).strip()

    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError(f"Synthesis did not return JSON: {raw_text[:500]}")
    deck = json.loads(match.group(0))

    for slide in deck.get("slides", []):
        slide["citation_indices"] = [
            i for i in slide.get("citation_indices", []) if i in valid_indices
        ]

    deck["references"] = references
    return deck
