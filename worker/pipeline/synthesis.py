"""Cohere synthesis: findings -> slide titles, bullets, and citation mapping."""

from __future__ import annotations

import json
import os
import re

import cohere

SYNTHESIS_MODEL = "command-r-plus-08-2024"

SYSTEM_PROMPT = (
    "You are a research analyst preparing a slide deck from academic literature. "
    "You will be given numbered findings, each drawn from one paper. Synthesize "
    "them into a coherent narrative deck. Every claim you make must be traceable "
    "to at least one numbered finding via its index — do not introduce facts, "
    "statistics, or citations that are not present in the provided findings. "
    "If the findings are thin on a topic, say less rather than inventing detail."
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


def synthesize_deck(topic: str, findings: list[dict]) -> dict:
    if not findings:
        raise ValueError(f"No findings retrieved for topic '{topic}' — cannot synthesize a deck.")

    findings_block, references = _build_findings_block(findings)
    valid_indices = {r["index"] for r in references}

    user_prompt = (
        f"Topic: {topic}\n\n"
        f"Numbered findings:\n{findings_block}\n\n"
        "Produce a slide deck with 5 to 8 content slides (not counting title or "
        "references). Return ONLY valid JSON matching this shape, nothing else:\n"
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

    client = cohere.ClientV2(api_key=os.environ["COHERE_API_KEY"])
    response = client.chat(
        model=SYNTHESIS_MODEL,
        max_tokens=4000,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw_text = response.message.content[0].text.strip()

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
