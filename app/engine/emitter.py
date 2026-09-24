"""CopperKnob-format emitter: structured sheet -> TXT / HTML / PDF + the
challenge kit (STEERING.md sections 7 and 12).

Format ground truth: references/sheet-examples.md (High Valley Fools /
Cut Loose Get Loud).  Header field order, count labels (1-2, 1&2), clock
facings, blocks of 8 with named-move section headers, prose intro block,
tags/restarts summary line, Intro line, styling in parentheses, Ending line.
"""
import datetime
import html as html_mod

CLOCK = {0: "12:00", 90: "3:00", 180: "6:00", 270: "9:00",
         45: "1:30", 135: "4:30", 225: "7:30", 315: "10:30"}


def _facing(rot):
    return CLOCK.get(rot % 360, f"{rot % 360} deg")


def _count_label(local_pos, beats, sync):
    """local_pos: 0-based count offset within the 8-block."""
    c = local_pos + 1
    if beats == 1:
        return f"{c}"
    if sync:
        return f"{c}&{c+1}"
    return f"{c}-{c+beats-1}"


def build_sheet(meta, dance, analysis=None, phrase=None):
    """Assemble the structured sheet dict from a dance (list of move variants).

    meta: title (dance title), song_title, artist, choreographer, country,
          level_label, description, contact, signature_note, ending_note.
    dance: {"moves": [...], "total_counts": int, "wall": "1|2|4",
            "walls": int, "net_rot": int}
    """
    moves = dance["moves"]
    total = dance["total_counts"]
    bpm = analysis.get("bpm") if analysis else None

    # --- walk the moves into 8-count blocks with labels + facings -----------
    blocks = []
    pos = 0
    rot = 0
    cur = None
    for m in moves:
        block_idx = pos // 8
        if cur is None or cur["n"] != block_idx + 1:
            cur = {"n": block_idx + 1, "headers": [], "lines": []}
            blocks.append(cur)
        # header bookkeeping (combine consecutive repeats as x2)
        h = m["header"]
        if cur["headers"] and cur["headers"][-1][0] == h:
            cur["headers"][-1][1] += 1
        else:
            cur["headers"].append([h, 1])

        move_rot = m["rot"]
        # find which line carries the turn annotation
        turn_line = None
        if move_rot:
            for i, ln in enumerate(m["lines"]):
                if "turn" in ln["text"].lower() or "pivot" in ln["text"].lower():
                    turn_line = i
            if turn_line is None:
                turn_line = len(m["lines"]) - 1
        local = pos % 8
        for i, ln in enumerate(m["lines"]):
            label = _count_label(local, ln["beats"], ln.get("sync", False))
            text = ln["text"]
            if move_rot and i == turn_line:
                rot = (rot + move_rot) % 360
                text += f" (facing {_facing(rot)})"
            cur["lines"].append({"label": label, "text": text})
            local += ln["beats"]
        pos += m["counts"]

    for b in blocks:
        b["header"] = ", ".join(h if n == 1 else f"{h} ×{n}"
                                for h, n in b["headers"])
        del b["headers"]

    # --- signature note on the final line (STEERING 12: one deliberate
    #     personality moment, in parentheses like real sheets) ---------------
    sig = meta.get("signature_note")
    if sig and blocks and blocks[-1]["lines"]:
        blocks[-1]["lines"][-1]["text"] += f" ({sig})"

    # --- header fields -------------------------------------------------------
    # Honesty contract (STEERING sections 4/8): the ARTIFACT carries the
    # warnings, not just the UI.  Never print a measurement that wasn't made,
    # never round the count-in, never claim "clean" under open flags.
    today = datetime.date.today()
    intro_line = None
    tags_line = ("Music map preserved; no tags or restarts were automatically "
                 "invented from section lengths.")
    warnings = []
    phrase_status = (phrase or {}).get("status")

    if phrase and phrase.get("intro") is not None:
        # print the MEASURED intro, never the rounded suggestion
        intro_beats = phrase["intro"].get("beats")
        if intro_beats:
            secs = round(intro_beats * 60.0 / bpm, 1) if bpm else None
            intro_line = f"Intro: {intro_beats} counts" + \
                         (f" / approx {secs} secs" if secs else "")
            res = phrase["intro"].get("residual", 0)
            if abs(res) >= 2:
                intro_line += (f" (measured — {res:+d} off a clean 8; confirm "
                               "the start point by ear)")
        elif intro_beats == 0:
            intro_line = "Intro: none — start on the first beat (Start on Vocals)"
    if intro_line is None:
        intro_line = "Intro: NOT MEASURED — run the phrasing check before publishing"

    if phrase:
        flags = phrase.get("flags", [])
        if any(f["code"] == "RESTART_NEEDED" for f in flags):
            tags_line = ("NOTE: the phrasing check shows this pattern does not "
                         "tile the song cleanly — a restart/tag is needed "
                         "(not auto-placed; see the phrasing report).")
        # every non-clean flag rides along on the sheet, located
        for f in flags:
            if f.get("severity") == "info":
                continue
            if f["code"] == "RESTART_NEEDED":
                continue
            prefix = "!!" if f["severity"] == "error" else "!"
            where = f" [{f['section']}]" if f.get("section") else ""
            warnings.append(f"{prefix}{where} {f['message']}")
        if phrase_status == "UNCERTAIN":
            warnings.insert(0, "!! PHRASING UNCERTAIN — this sheet is a DRAFT. "
                               "Do not publish until the flags below are resolved.")
        elif phrase_status == "REVIEW":
            warnings.insert(0, "! Phrasing needs review — read the flags below "
                               "before publishing.")
    else:
        warnings.append("! No phrasing check has been run for this song, so the "
                        "counts have not been verified against the audio.")

    # octave ambiguity must be presented, never silently resolved (P0-4)
    bpm_note = ""
    if analysis:
        alts = analysis.get("octave_alternates") or []
        if alts:
            alt_txt = " / ".join(f"{a['bpm']:.0f}" for a in alts)
            bpm_note = (f" (octave-ambiguous: also scores at {alt_txt} — "
                        "confirm which grid the floor counts)")
            warnings.append(f"! Tempo octave ambiguity: {bpm} vs {alt_txt} BPM. "
                            "Both are legitimate counts of the same audio.")
        if analysis.get("drift"):
            d = analysis["drift"]
            warnings.append(f"!! Tempo drifts {d['drift_pct']}% across the song "
                            f"({d['first_half_bpm']:.0f} to "
                            f"{d['second_half_bpm']:.0f} BPM) — a fixed count "
                            "sheet cannot phrase a drifting grid.")
        conf = analysis.get("bpm_confidence")
        if conf and conf != "high":
            warnings.append(f"! BPM confidence is {conf}: " +
                            "; ".join(analysis.get("bpm_confidence_notes") or []))

    # A step sheet must carry the 132 BPM product boundary too.  Someone may
    # build a manual sequence rather than use the generator, so this cannot
    # live only in the generation endpoint.
    measured_bpm = bpm or (dance.get("tempo") or {}).get("bpm")
    if measured_bpm and measured_bpm > 132:
        warnings.insert(0, f"!! EXPERIMENTAL TEMPO: {measured_bpm:.0f} BPM exceeds "
                        "the validated 132 BPM range. Manual choreography review "
                        "is required before teaching, submitting, or publishing.")

    # dance validation failures (hard publish gates, STEERING section 8 rule 4)
    val = dance.get("validation") or {}
    if val and not val.get("valid", True):
        warnings.insert(0, "!! THIS DANCE FAILED VALIDATION — DRAFT ONLY, "
                           "DO NOT SUBMIT:")
        for pr in val.get("problems", []):
            warnings.append(f"!!   {pr['message']}")
    for n in val.get("notes", []):
        warnings.append(f"! {n}")

    clean = not warnings
    dance_title = meta.get("title") or "Untitled"
    song_title = meta.get("song_title") or dance_title
    description = meta.get("description") or (
        f"A simple, floor-ready starter dance for \"{song_title}\" — "
        "standard steps" + (", clean phrasing" if clean else "") +
        ", built to be easy to teach. "
        "This is a scratch baseline: put your own spin on it and make the "
        "definitive dance for this song.")

    choreo = meta.get("choreographer") or "Hillbilly Hellfire"
    country = meta.get("country") or "USA"
    level_label = meta.get("level_label") or "Absolute Beginner"

    return {
        "title": dance_title,
        "song_title": song_title,
        "artist": meta.get("artist", "Hillbilly Hellfire"),
        "count": total,
        "wall": dance.get("walls", 1),
        "level": level_label,
        "choreographer_line": f"Choreographer: {choreo} ({country}) - "
                              f"{today.strftime('%B %Y')}",
        "music_line": f"Music: {song_title} - "
                      f"{meta.get('artist','Hillbilly Hellfire')}",
        "description": description,
        "tags_line": tags_line,
        "intro_line": intro_line,
        "bpm": bpm,
        "bpm_note": bpm_note,
        "warnings": warnings,
        "is_draft": bool(warnings and any(w.startswith("!!") for w in warnings)),
        "phrase_status": phrase_status,
        "blocks": blocks,
        "ending": meta.get("ending_note"),
        "contact": meta.get("contact"),
        "last_update": today.strftime("%d %b %Y"),
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_txt(sheet):
    L = []
    if sheet.get("is_draft"):
        L.append("=" * 66)
        L.append("  DRAFT — FAILED CHECKS. NOT READY TO SUBMIT OR PUBLISH.")
        L.append("=" * 66)
        L.append("")
    L.append(sheet["title"])
    L.append(f"Count: {sheet['count']}    Wall: {sheet['wall']}    "
             f"Level: {sheet['level']}")
    L.append(sheet["choreographer_line"])
    L.append(sheet["music_line"])
    L.append("")
    L.append(sheet["description"])
    L.append("")
    L.append(sheet["tags_line"])
    L.append("")
    line = sheet["intro_line"]
    if sheet.get("bpm"):
        line += f"    BPM: {sheet['bpm']:.0f}{sheet.get('bpm_note', '')}"
    L.append(line)
    L.append("")
    if sheet.get("warnings"):
        L.append("-" * 66)
        L.append("CHECKS AND CAVEATS (read before teaching or submitting)")
        for w in sheet["warnings"]:
            L.append(f"  {w}")
        L.append("-" * 66)
        L.append("")
    for b in sheet["blocks"]:
        L.append(f"Section {b['n']} – {b['header']}")
        for ln in b["lines"]:
            L.append(f"{ln['label']:<8}{ln['text']}")
        L.append("")
    if sheet.get("ending"):
        L.append(f"ENDING: {sheet['ending']}")
        L.append("")
    if sheet.get("contact"):
        L.append(f"Contact: {sheet['contact']}")
    L.append(f"Last Update: {sheet['last_update']}")
    return "\n".join(L)


def render_html(sheet):
    esc = html_mod.escape
    rows = []
    for b in sheet["blocks"]:
        rows.append(f"<h3>Section {b['n']} &ndash; {esc(b['header'])}</h3>")
        rows.append("<table class='counts'>")
        for ln in b["lines"]:
            rows.append(f"<tr><td class='lbl'>{esc(ln['label'])}</td>"
                        f"<td>{esc(ln['text'])}</td></tr>")
        rows.append("</table>")
    ending = (f"<p class='ending'><strong>ENDING:</strong> "
              f"{esc(sheet['ending'])}</p>" if sheet.get("ending") else "")
    contact = (f"<p class='contact'>Contact: {esc(sheet['contact'])}</p>"
               if sheet.get("contact") else "")
    bpm = (f"&nbsp;&nbsp;&nbsp;BPM: {sheet['bpm']:.0f}"
           f"{esc(sheet.get('bpm_note', ''))}") if sheet.get("bpm") else ""
    draft = ('<div class="draftbanner">DRAFT &mdash; FAILED CHECKS. '
             'NOT READY TO SUBMIT OR PUBLISH.</div>'
             if sheet.get("is_draft") else "")
    warn = ""
    if sheet.get("warnings"):
        items = "".join(f"<li>{esc(w.lstrip('! '))}</li>"
                        for w in sheet["warnings"])
        warn = ('<div class="warnbox"><strong>Checks and caveats</strong> '
                f'(read before teaching or submitting)<ul>{items}</ul></div>')
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{esc(sheet['title'])} — step sheet</title>
<style>
 body {{ font-family: Georgia, 'Times New Roman', serif; max-width: 46rem;
        margin: 2rem auto; padding: 0 1rem; color: #111; }}
 h1 {{ margin-bottom: .2rem; }}
 .meta {{ margin: .15rem 0; }}
 .desc {{ font-style: italic; margin: 1rem 0; }}
 .tagsline {{ font-weight: bold; margin: .6rem 0; }}
 h3 {{ margin: 1.1rem 0 .3rem; border-bottom: 1px solid #999; }}
 table.counts {{ border-collapse: collapse; }}
 table.counts td {{ padding: .12rem .6rem .12rem 0; vertical-align: top; }}
 td.lbl {{ font-weight: bold; white-space: nowrap; width: 4.5rem; }}
 .ending {{ margin-top: 1rem; }}
 .contact, .last {{ color: #444; font-size: .9rem; }}
 .draftbanner {{ background: #8b0000; color: #fff; font-weight: bold;
    padding: .6rem .9rem; border-radius: 6px; margin-bottom: 1rem;
    letter-spacing: .5px; text-align: center; }}
 .warnbox {{ background: #fff6e0; border: 1px solid #c99700; color: #5a4200;
    padding: .6rem .9rem; border-radius: 6px; margin: 1rem 0;
    font-family: system-ui, sans-serif; font-size: .88rem; }}
 .warnbox ul {{ margin: .4rem 0 0 1.1rem; padding: 0; }}
 @media print {{ body {{ margin: 0 auto; }} }}
</style></head><body>
{draft}
<h1>{esc(sheet['title'])}</h1>
<p class="meta"><strong>Count:</strong> {sheet['count']}
 &nbsp;&nbsp; <strong>Wall:</strong> {sheet['wall']}
 &nbsp;&nbsp; <strong>Level:</strong> {esc(sheet['level'])}</p>
<p class="meta">{esc(sheet['choreographer_line'])}</p>
<p class="meta">{esc(sheet['music_line'])}</p>
<p class="desc">{esc(sheet['description'])}</p>
<p class="tagsline">{esc(sheet['tags_line'])}</p>
<p class="meta">{esc(sheet['intro_line'])}{bpm}</p>
{warn}
{''.join(rows)}
{ending}
{contact}
<p class="last">Last Update: {esc(sheet['last_update'])}</p>
</body></html>"""


def render_pdf(sheet, path):
    """CopperKnob submissions accept text/PDF/Word <= 2 MB; images rejected."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle)
    from reportlab.lib import colors

    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("T", parent=styles["Title"], spaceAfter=4)
    meta_s = ParagraphStyle("M", parent=styles["Normal"], spaceAfter=2)
    desc_s = ParagraphStyle("D", parent=styles["Italic"], spaceBefore=6,
                            spaceAfter=6)
    sec_s = ParagraphStyle("S", parent=styles["Heading3"], spaceBefore=10,
                           spaceAfter=2)

    draft_s = ParagraphStyle("DR", parent=styles["Normal"], fontSize=12,
                             textColor=colors.white, backColor=colors.HexColor("#8b0000"),
                             alignment=1, spaceAfter=10, borderPadding=6,
                             fontName="Helvetica-Bold", leading=16)
    warn_s = ParagraphStyle("W", parent=styles["Normal"], fontSize=8.5,
                            textColor=colors.HexColor("#5a4200"),
                            backColor=colors.HexColor("#fff6e0"),
                            borderPadding=5, spaceBefore=6, spaceAfter=8,
                            leading=11)

    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            topMargin=0.7 * inch, bottomMargin=0.7 * inch)
    story = []
    if sheet.get("is_draft"):
        story.append(Paragraph(
            "DRAFT — FAILED CHECKS. NOT READY TO SUBMIT OR PUBLISH.", draft_s))
    story += [Paragraph(sheet["title"], title_s),
             Paragraph(f"<b>Count:</b> {sheet['count']} &nbsp;&nbsp; "
                       f"<b>Wall:</b> {sheet['wall']} &nbsp;&nbsp; "
                       f"<b>Level:</b> {sheet['level']}", meta_s),
             Paragraph(sheet["choreographer_line"], meta_s),
             Paragraph(sheet["music_line"], meta_s),
             Paragraph(sheet["description"], desc_s),
             Paragraph(f"<b>{sheet['tags_line']}</b>", meta_s)]
    intro = sheet["intro_line"]
    if sheet.get("bpm"):
        intro += f" &nbsp;&nbsp; BPM: {sheet['bpm']:.0f}{sheet.get('bpm_note', '')}"
    story.append(Paragraph(intro, meta_s))
    if sheet.get("warnings"):
        body = "<br/>".join("• " + w.lstrip("! ") for w in sheet["warnings"])
        story.append(Paragraph(
            "<b>Checks and caveats</b> (read before teaching or submitting)"
            f"<br/>{body}", warn_s))
    story.append(Spacer(1, 6))

    for b in sheet["blocks"]:
        story.append(Paragraph(f"Section {b['n']} – {b['header']}", sec_s))
        data = [[ln["label"], ln["text"]] for ln in b["lines"]]
        t = Table(data, colWidths=[0.7 * inch, 5.6 * inch])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#333333")),
        ]))
        story.append(t)
    if sheet.get("ending"):
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>ENDING:</b> {sheet['ending']}", meta_s))
    story.append(Spacer(1, 10))
    if sheet.get("contact"):
        story.append(Paragraph(f"Contact: {sheet['contact']}", meta_s))
    story.append(Paragraph(f"Last Update: {sheet['last_update']}", meta_s))
    doc.build(story)
    return path


# ---------------------------------------------------------------------------
# Challenge kit (STEERING section 12 — the reframed, credit-first challenge)
# ---------------------------------------------------------------------------
def build_challenge_kit(sheet, meta, analysis=None, phrase=None):
    """The public post. It must not claim more certainty than the app measured:
    'steady' only when the tempo really is steady, 'Verified' only at high
    confidence. Overclaiming here is what costs credibility with dancers."""
    title = meta.get("title", "")
    artist = meta.get("artist", "Hillbilly Hellfire")
    bpm = f"{analysis['bpm']:.0f}" if analysis and analysis.get("bpm") else "?"
    conf = (analysis or {}).get("bpm_confidence")
    steady = bool(analysis and analysis.get("tempo_steady")
                  and not analysis.get("drift"))
    alts = (analysis or {}).get("octave_alternates") or []

    tempo_phrase = f"steady {bpm} BPM" if steady else f"{bpm} BPM"
    if conf == "high" and not alts:
        bpm_claim = (f"- Verified BPM: {bpm} (measured from the audio, "
                     "not the label)")
    else:
        notes = "; ".join((analysis or {}).get("bpm_confidence_notes") or [])
        bpm_claim = f"- Measured BPM: {bpm} (confidence: {conf or 'unknown'}"
        bpm_claim += f" — {notes})" if notes else ")"
        if alts:
            bpm_claim += ("\n- Heads up: the tempo is octave-ambiguous — it "
                          "also counts as "
                          + " / ".join(f"{a['bpm']:.0f}" for a in alts) +
                          " BPM. Count it whichever way feels right on the floor.")

    phrasing_claim = "defined sections"
    if phrase and phrase.get("status") and phrase["status"] != "CLEAN":
        phrasing_claim = ("sections mapped, with the rough spots flagged "
                          "honestly in the sheet")

    yt_title = (f"{title} - {artist} | Line Dance "
                f"({sheet['level']}, {sheet['count']} Count, "
                f"{sheet['wall']} Wall, {bpm} BPM)")
    description = f"""Here's a floor-ready track and a scratch starter dance to prove it phrases: {sheet['count']} counts, {sheet['wall']} wall, {tempo_phrase}, {phrasing_claim}.

THE CHALLENGE: put YOUR name on the definitive dance for this song.

The starter sheet below is a skeleton, not the ceiling. Choreograph your own dance to "{title}" and I'll push the best one to my whole audience:
- Featured on this channel with FULL credit — your name, your country, your CopperKnob link
- I'll produce a clean count-on-screen demo video of YOUR dance
- Yours becomes the official dance for the song, linked everywhere it appears

What you get to work with (the friction is already removed):
- The song file, free to choreograph to
{bpm_claim}
- A phrasing map — where the blocks, bridges and odd bars fall
- A pre-filled CopperKnob header block

Step sheet: link in pinned comment.
Drop your video as a response or tag us. Deadline in the pinned comment.

Music: {title} - {artist}"""
    hashtags = ("#linedance #linedancechallenge #linedancedemo "
                "#linedancersoftiktok #countrydance #newlinedance "
                "#hillbillyhellfire")
    return {
        "youtube_title": yt_title,
        "description": description,
        "hashtags": hashtags,
        "copperknob_music_line": f"Music: {title} - {artist}",
        "upload_title_schema": yt_title,
    }


def build_publish_kit(sheet, meta, analysis=None, phrase=None):
    """Prepare truthful, copy-ready material for each publishing destination.

    The user still uploads and reviews the content on each site; this keeps
    account access and the final publication decision in their hands.
    """
    dance_title = sheet["title"]
    song_title = sheet.get("song_title") or meta.get("song_title") or dance_title
    artist = sheet.get("artist") or meta.get("artist", "Hillbilly Hellfire")
    bpm = f"{analysis['bpm']:.0f}" if analysis and analysis.get("bpm") else "?"
    phrasing_ready = (phrase or {}).get("status") == "CLEAN"
    youtube_url = meta.get("youtube_url") or "[paste YouTube video URL]"
    sheet_url = meta.get("sheet_url") or "[add CopperKnob or BootStepper link once live]"
    tempo_phrase = f"{bpm} BPM" if bpm != "?" else "tempo to be confirmed"

    youtube_title = (f"{dance_title} | {sheet['count']} Count {sheet['wall']} Wall "
                     f"{sheet['level']} Line Dance | {song_title} - {artist}")
    youtube_add_on = f"""LINE DANCE DETAILS
Dance: {dance_title}
Choreography: {sheet['choreographer_line'].replace('Choreographer: ', '')}
Music: {song_title} - {artist}
Level: {sheet['level']} | {sheet['count']} Count | {sheet['wall']} Wall
Start: {sheet['intro_line']}
Tempo: {tempo_phrase}
Phrase check: {'ready' if phrasing_ready else 'review the sheet before publishing'}
Step sheet: {sheet_url}

For the written steps, use the step-sheet link above. Please credit the choreography when sharing a demo."""
    hashtags = ("#LineDance #LineDancing #CountryDance #LineDanceSheet "
                "#HillbillyHellfire #DarkCountry #CountryEDM")
    copperknob_comments = f"""Stepsheet submission for: {dance_title}
Music: {song_title} - {artist}
YouTube demonstration: {youtube_url}

Please find the final text/PDF stepsheet attached. Thank you."""
    copperknob_checklist = [
        "Confirm the PDF has no DRAFT banner or unresolved warning.",
        "On CopperKnob Contact Us, choose “Stepsheet Submission” and attach the generated PDF.",
        "Paste the prepared comments, including the YouTube demonstration URL.",
        "After the sheet is live, use CopperKnob’s Submit Video control on that sheet to attach or verify the video.",
    ]
    bootstepper_checklist = [
        "Upload the same generated PDF in BootStepper’s Submit a Dance flow.",
        "Review its extracted title, level, counts, walls, song details, and every step block before publishing.",
        "Add the YouTube demonstration and the CopperKnob URL once those links are live.",
    ]
    return {
        "youtube_title": youtube_title,
        "youtube_add_on": youtube_add_on,
        "hashtags": hashtags,
        "copperknob_comments": copperknob_comments,
        "copperknob_checklist": copperknob_checklist,
        "bootstepper_checklist": bootstepper_checklist,
        "sheet_filename": f"{dance_title} - step sheet.pdf",
    }
