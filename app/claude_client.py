"""Anthropic API client that orchestrates the Abnahme skill.

The skill prompt is loaded from the settings store (editable by the user),
falling back to the bundled SKILL.md if no override exists. Claude parses
the free-text activity message and calls our deterministic Python tools for
night-hour computation and holiday checks. Final output is structured JSON
that the FastAPI layer turns into a PDF + booking table.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from anthropic import Anthropic

from .scripts.check_holiday import classify
from .scripts.night_hours import night_hours
from .settings_store import get_api_key, get_model, load_skill, load_settings

log = logging.getLogger(__name__)

MAX_TURNS = 8  # safety net against runaway tool loops

TOOLS = [
    {
        "name": "compute_night_hours",
        "description": (
            "Compute how many hours of a time window fall into the night zone "
            "(20:00–06:00). Returns decimal hours. Use this for every "
            "Tätigkeit that has explicit start/end times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Start time as HH:MM (24h)",
                },
                "end": {
                    "type": "string",
                    "description": "End time as HH:MM (24h). May be earlier "
                    "than start if the shift crosses midnight.",
                },
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "classify_date",
        "description": (
            "Classify a date as weekday/Saturday/Sunday/German federal "
            "holiday. Always call this once you know the Einsatz-Datum to "
            "decide which surcharges apply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "iso_date": {
                    "type": "string",
                    "description": "Date in ISO format YYYY-MM-DD",
                },
            },
            "required": ["iso_date"],
        },
    },
    {
        "name": "finalize",
        "description": (
            "Emit the final structured result. Call this exactly once when "
            "all parsing and calculation is done. After this call, do not "
            "produce any more output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kunde": {"type": "string"},
                "datum": {
                    "type": "string",
                    "description": "Display date DD.MM.YYYY",
                },
                "datum_iso": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD (for filename)",
                },
                "objekt": {"type": "string"},
                "projekt": {"type": "string"},
                "best_nr": {"type": "string"},
                "rows": {
                    "type": "array",
                    "description": "Table rows for the PDF. Max 8 rows.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "aufgabe": {"type": "string"},
                            "einheiten": {"type": "string"},
                            "summe": {"type": "string"},
                        },
                        "required": ["aufgabe", "einheiten", "summe"],
                    },
                },
                "gesamt_summe": {"type": "string"},
                "bemerkung": {"type": "string"},
                "buchung": {
                    "type": "object",
                    "description": "Booking summary for internal payroll.",
                    "properties": {
                        "regulaere_stunden_gesamt": {"type": "number"},
                        "nacht_zuschlag_stunden": {"type": "number"},
                        "sonntag_zuschlag_stunden": {"type": "number"},
                        "feiertag_zuschlag_stunden": {"type": "number"},
                        "buchung_gesamt": {"type": "number"},
                        "details": {
                            "type": "array",
                            "description": "Per-task breakdown.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "taetigkeit": {"type": "string"},
                                    "regulaer_h": {"type": "number"},
                                    "zuschlag_beschreibung": {
                                        "type": "string"
                                    },
                                    "zuschlag_h": {"type": "number"},
                                },
                                "required": [
                                    "taetigkeit",
                                    "regulaer_h",
                                    "zuschlag_h",
                                ],
                            },
                        },
                    },
                    "required": [
                        "regulaere_stunden_gesamt",
                        "nacht_zuschlag_stunden",
                        "sonntag_zuschlag_stunden",
                        "feiertag_zuschlag_stunden",
                        "buchung_gesamt",
                    ],
                },
                "plausibilitaets_warnung": {
                    "type": "string",
                    "description": "Empty if the eurosumme in the message "
                    "matches the customer rate. Otherwise a short warning sentence.",
                },
                "fehlende_eingaben": {
                    "type": "array",
                    "description": "List of fields the user still needs to "
                    "provide. Possible values: 'kunde', 'satz', 'datum'.",
                    "items": {
                        "type": "string",
                        "enum": ["kunde", "satz", "datum"],
                    },
                },
            },
            "required": ["fehlende_eingaben"],
        },
    },
]


def _run_tool(name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call to the matching Python function."""
    if name == "compute_night_hours":
        h = night_hours(params["start"], params["end"])
        return {"night_hours": round(h, 4)}
    if name == "classify_date":
        info = classify(date.fromisoformat(params["iso_date"]))
        return info
    raise ValueError(f"Unknown tool: {name}")


def process_message(
    text: str,
    kunde: str | None = None,
    satz: float | None = None,
    datum: str | None = None,
) -> dict[str, Any]:
    """Run Claude over the activity message and return structured output.

    Returns a dict matching the `finalize` schema, with an extra
    `_status` field: 'complete' if all data is present, 'needs_input' if
    the user still has to provide kunde/satz/datum.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ist nicht gesetzt. Bitte in den "
            "Einstellungen hinterlegen."
        )
    client = Anthropic(api_key=api_key)
    settings = load_settings()

    user_msg_parts: list[str] = [f"Tätigkeitsmeldung:\n\n{text}"]
    if kunde:
        user_msg_parts.append(f"\nKunde (vom Nutzer bestätigt): {kunde}")
    if satz is not None:
        user_msg_parts.append(
            f"\nKundenstundensatz (netto, vom Nutzer bestätigt): {satz} €/h"
        )
    if datum:
        user_msg_parts.append(f"\nDatum (vom Nutzer bestätigt): {datum}")

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "\n".join(user_msg_parts)}
    ]

    skill_text = load_skill()
    system = skill_text + (
        "\n\n## Ausführungs-Hinweis für diesen Lauf\n\n"
        "Du läufst hier in einem automatisierten Service, nicht im Chat. "
        "Stelle keine Rückfragen, sondern: wenn Kunde oder Stundensatz "
        "fehlen, setze sie auf Leerstring/0 und liste sie in "
        "`fehlende_eingaben` auf, wenn `finalize` aufgerufen wird. "
        "Wenn das Datum fehlt und nicht aus der Nachricht ableitbar ist, "
        "ebenfalls in `fehlende_eingaben` listen. "
        "Rufe `finalize` GENAU EINMAL als allerletzten Schritt auf.\n\n"
        f"Aktuelle Zuschlagssätze (Defaults): "
        f"Nacht {settings['surcharge_night_pct']} %, "
        f"Sonntag {settings['surcharge_sunday_pct']} %, "
        f"Feiertag {settings['surcharge_holiday_pct']} %."
    )

    final_result: dict[str, Any] | None = None
    model = get_model()

    for turn in range(MAX_TURNS):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        log.info("Turn %d, stop_reason=%s", turn, response.stop_reason)

        # Collect assistant message for the next round
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Model stopped without finalize – shouldn't happen, but bail safely
            log.warning("Model stopped without finalize at turn %d", turn)
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "finalize":
                final_result = dict(block.input)
                # Acknowledge so the conversation closes cleanly
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "ok",
                    }
                )
            else:
                try:
                    out = _run_tool(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(out),
                        }
                    )
                except Exception as exc:
                    log.exception("Tool %s failed", block.name)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"ERROR: {exc}",
                            "is_error": True,
                        }
                    )

        messages.append({"role": "user", "content": tool_results})

        if final_result is not None:
            break

    if final_result is None:
        raise RuntimeError(
            "Claude did not call finalize within turn limit. "
            "Check skill_prompt or model output."
        )

    fehlende = final_result.get("fehlende_eingaben", [])
    final_result["_status"] = "needs_input" if fehlende else "complete"
    return final_result
