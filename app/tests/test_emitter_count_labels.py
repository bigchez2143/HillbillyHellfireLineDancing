"""Focused regressions for CopperKnob count labels."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.emitter import build_sheet


def test_count_labels_match_each_line_beat_span():
    moves = [
        {
            "header": "Mixed lengths",
            "counts": 8,
            "rot": 0,
            "lines": [
                {"beats": 1, "text": "One beat"},
                {"beats": 2, "text": "Two beats"},
                {"beats": 4, "text": "Four beats"},
                {"beats": 1, "text": "Last beat"},
            ],
        },
        {
            "header": "Sync label",
            "counts": 8,
            "rot": 0,
            "lines": [
                {"beats": 2, "sync": True, "text": "Sync two beats"},
                {"beats": 6, "text": "Six beats"},
            ],
        },
    ]
    dance = {
        "moves": moves,
        "total_counts": 16,
        "wall": "1",
        "walls": 1,
        "net_rot": 0,
    }

    sheet = build_sheet({"title": "Count Label Test"}, dance)

    assert [line["label"] for line in sheet["blocks"][0]["lines"]] == [
        "1",
        "2-3",
        "4-7",
        "8",
    ]
    assert [line["label"] for line in sheet["blocks"][1]["lines"]] == [
        "1&2",
        "3-8",
    ]
