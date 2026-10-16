from __future__ import annotations

import fcntl
import json
import sqlite3
import time
import uuid
from pathlib import Path
from html.parser import HTMLParser
from typing import Literal

from anki.collection import Collection
from anki.cards import Card
from anki.scheduler.v3 import CardAnswer

Rating = Literal["again", "hard", "good", "easy"]
RATINGS = {"again": CardAnswer.AGAIN, "hard": CardAnswer.HARD,
           "good": CardAnswer.GOOD, "easy": CardAnswer.EASY}


class StudyText(HTMLParser):
    """Extract text without leaking cloze data attributes or script/style content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = []

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script", "template"}:
            self.ignored.append(tag)
        if tag in {"br", "p", "div", "hr"} and not self.ignored:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.ignored and self.ignored[-1] == tag:
            self.ignored.pop()

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def study_text(html: str) -> str:
    parser = StudyText()
    parser.feed(html)
    return "".join(parser.parts).strip()


class CollectionLease:
    """One local service per collection; create a consistent DB snapshot first."""

    def __init__(self, path: Path, *, create: bool = False):
        self.path = path.resolve()
        if not create and not self.path.is_file():
            raise ValueError("Collection does not exist. Run the demo command first.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = self.path.with_suffix(".anki-mcp.lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if create and self.path.exists():
                raise ValueError("Refusing to overwrite an existing collection.")
            if self.path.exists():
                folder = self.path.parent / "backups"
                folder.mkdir(exist_ok=True)
                backup = folder / f"{self.path.stem}-{time.time_ns()}.anki2"
                with sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True) as source:
                    with sqlite3.connect(backup) as destination:
                        source.backup(destination)
            self.col = Collection(str(self.path))
        except BaseException:
            self.lock.close()
            raise

    def close(self):
        try:
            self.col.close()
        finally:
            self.lock.close()


def demo_marker(path: Path) -> Path:
    return path.with_suffix(".anki-mcp-demo.json")


SPANISH_A1 = [
    ("hola", "hello"), ("adiós", "goodbye"), ("gracias", "thanks"),
    ("sí", "yes"), ("no", "no"), ("agua", "water"), ("pan", "bread"),
    ("leche", "milk"), ("casa", "house"), ("libro", "book"),
    ("mesa", "table"), ("silla", "chair"), ("perro", "dog"),
    ("gato", "cat"), ("sol", "sun"), ("luna", "moon"),
    ("rojo", "red"), ("azul", "blue"), ("grande", "big"), ("pequeño", "small"),
]


def create_demo(path: Path, *, spanish: bool = False) -> dict:
    lease = CollectionLease(path, create=True)
    try:
        col = lease.col
        deck_id = col.decks.id("Spanish A1 · Practice" if spanish else "MCP Practice")
        model = col.models.by_name("Basic (and reversed card)" if spanish else "Basic")
        pairs = SPANISH_A1 if spanish else [
            ("What is the capital of France?", "Paris."),
            ("What does MCP stand for?", "Model Context Protocol."),
            ("What is 7 × 8?", "56."),
        ]
        for front, back in pairs:
            note = col.new_note(model)
            note["Front"], note["Back"] = front, back
            col.add_note(note, deck_id)
    finally:
        lease.close()
    # Only our synthetic collections are accepted by the initial server.
    demo_marker(lease.path).write_text(json.dumps({"kind": "synthetic-demo", "version": 1}))
    return {"collection": str(lease.path), "deck_id": deck_id,
            "notes": len(pairs), "cards": len(pairs) * (2 if spanish else 1)}


class ReviewService:
    """One reviewer; require an explicit tool rating and reveal before saving."""

    def __init__(self, path: Path):
        path = path.resolve()
        marker = demo_marker(path)
        if path.exists() and (not marker.is_file() or
                              json.loads(marker.read_text()).get("kind") != "synthetic-demo"):
            raise ValueError("Only practice collections created by the demo command are supported.")
        self.lease = CollectionLease(path)
        self.col = self.lease.col
        self.active = None
        self.receipts = {}
        self.failed_reason = None
        self.batch = None
        self.batch_receipts = {}

    def close(self):
        self.lease.close()

    def _ensure_available(self):
        if self.failed_reason:
            raise ValueError(self.failed_reason)

    def list_decks(self) -> dict:
        self._ensure_available()
        return {"decks": [{"id": d.id, "name": d.name}
                          for d in self.col.decks.all_names_and_ids()]}

    def _ensure_no_batch(self):
        if self.batch:
            raise ValueError("Commit the pending batch before using single-card tools.")

    def next_card(self, deck_id: int) -> dict:
        self._ensure_available()
        self._ensure_no_batch()
        if self.active:
            if self.active["deck_id"] != deck_id:
                raise ValueError("Finish or cancel the active review before switching decks.")
            return self.active["front"]
        if not self.col.decks.name_if_exists(deck_id):
            raise ValueError("Unknown deck ID.")
        self.col.decks.select(deck_id)
        queued = self.col.sched.get_queued_cards(fetch_limit=1)
        counts = {"new": queued.new_count, "learning": queued.learning_count,
                  "review": queued.review_count}
        if not queued.cards:
            return {"done": True, "counts": counts}
        item = queued.cards[0]
        card = self.col.get_card(item.card.id)
        card.start_timer()
        front = {"done": False, "review_token": uuid.uuid4().hex,
                 "card_id": card.id, "question_text": study_text(card.question()), "counts": counts}
        self.active = {"deck_id": deck_id, "card": card, "states": item.states,
                       "front": front, "revealed": False}
        return front

    def _require_active(self, token: str) -> dict:
        self._ensure_available()
        self._ensure_no_batch()
        if not self.active or self.active["front"]["review_token"] != token:
            raise ValueError("Unknown or expired review token. Fetch the next card.")
        return self.active

    def reveal_answer(self, review_token: str) -> dict:
        active = self._require_active(review_token)
        card: Card = active["card"]
        intervals = self.col.sched.describe_next_states(active["states"])
        active["revealed"] = True
        return {"review_token": review_token, "card_id": card.id,
                "answer_text": study_text(card.answer()),
                "ratings": dict(zip(RATINGS, intervals))}

    def rate_card(self, review_token: str, rating: Rating) -> dict:
        self._ensure_no_batch()
        if rating not in RATINGS:
            raise ValueError("Rating must be again, hard, good, or easy.")
        if review_token in self.receipts:
            receipt = self.receipts[review_token]
            if receipt["rating"] != rating:
                raise ValueError("This review was already recorded with another rating.")
            return receipt
        active = self._require_active(review_token)
        if not active["revealed"]:
            raise ValueError("Reveal the answer before recording a rating.")
        card: Card = active["card"]
        answer = self.col.sched.build_answer(
            card=card, states=active["states"], rating=RATINGS[rating])
        # Consume the token before fallible writes; never repeat a possibly saved review.
        receipt = {"recorded": None, "status": "uncertain", "review_token": review_token,
                   "card_id": card.id, "rating": rating, "service_available": False}
        self.receipts[review_token] = receipt
        self.active = None
        try:
            self.col.sched.answer_card(answer)
            # Public API persistence boundary for this conservative prototype.
            self.col.close()
            receipt.update(recorded=True, status="recorded", reps=card.reps + 1)
            self.col = self.lease.col = Collection(str(self.lease.path))
            updated = self.col.get_card(card.id)
            receipt.update(reps=updated.reps, service_available=True)
        except Exception:
            self.failed_reason = ("Review service stopped after a storage error. "
                                  "Do not resubmit this review. Restart and inspect its history.")
            receipt["message"] = self.failed_reason
        return receipt

    def cancel_review(self, review_token: str) -> dict:
        self._require_active(review_token)
        self.active = None
        return {"cancelled": True, "review_recorded": False}


    def prepare_batch(self, deck_id: int, limit: int = 10) -> dict:
        """Preview queued cards for an agent; no scheduling writes are made.

        Answers are trusted only as study content and must not be presented before
        the user's attempt. Pending answers/ratings have no durable storage.
        """
        self._ensure_available()
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("Batch limit must be an integer from 1 to 10.")
        if self.batch:
            if self.batch["deck_id"] != deck_id:
                raise ValueError("Commit the pending batch before switching decks.")
            return self.batch["preview"]
        if not self.col.decks.name_if_exists(deck_id):
            raise ValueError("Unknown deck ID.")
        if self.active and self.active["deck_id"] != deck_id:
            raise ValueError("Finish or cancel the active review before switching decks.")
        self.col.decks.select(deck_id)
        queued = self.col.sched.get_queued_cards(fetch_limit=1000)
        candidates = []
        if self.active:
            candidates.append((self.active["card"], self.active["front"]["review_token"]))
        candidates.extend((self.col.get_card(item.card.id), uuid.uuid4().hex)
                          for item in queued.cards)
        cards, notes = [], set()
        for card, token in candidates:
            if card.nid in notes:
                continue
            notes.add(card.nid)
            cards.append({"review_token": token, "card_id": card.id,
                          "question_text": study_text(card.question()),
                          "answer_text": study_text(card.answer())})
            if len(cards) == limit:
                break
        preview = {"batch_token": uuid.uuid4().hex, "cards": cards,
                   "recorded": False, "pending_in_memory": True}
        self.batch = {"deck_id": deck_id, "preview": preview}
        self.active = None
        return preview

    def commit_batch(self, batch_token: str, ratings: list[dict]) -> dict:
        """Save explicit ratings sequentially, never replay an uncertain save.

        This is not an atomic transaction. A partial result is final for this
        token; inspect receipts and fetch a new batch for remaining cards.
        """
        if not isinstance(ratings, list):
            raise ValueError("Ratings must be a list.")
        normalized = []
        for item in ratings:
            if (not isinstance(item, dict) or set(item) != {"card_id", "rating"}
                    or type(item["card_id"]) is not int
                    or not isinstance(item["rating"], str) or item["rating"] not in RATINGS):
                raise ValueError("Each rating needs an integer card_id and valid rating.")
            normalized.append({"card_id": item["card_id"], "rating": item["rating"]})
        if batch_token in self.batch_receipts:
            saved = self.batch_receipts[batch_token]
            if saved["ratings"] != normalized:
                raise ValueError("This batch was already committed with different ratings.")
            return saved["result"]
        self._ensure_available()
        if not self.batch or self.batch["preview"]["batch_token"] != batch_token:
            raise ValueError("Unknown or expired batch token.")
        batch = self.batch
        cards = batch["preview"]["cards"]
        # Only an ordered prefix may be submitted: an unfinished batch is allowed.
        ids = [item["card_id"] for item in normalized]
        if ids != [card["card_id"] for card in cards[:len(ids)]] or len(ids) > len(cards):
            raise ValueError("Ratings must match an ordered prefix of the pending batch.")
        result = {"batch_token": batch_token, "status": "partial", "receipts": [],
                  "unrecorded_card_ids": [card["card_id"] for card in cards],
                  "uncertain_card_ids": [], "submitted_count": len(normalized),
                  "recorded_count": 0, "atomic": False}
        # Cache before any fallible write. Retrying this token never starts it again.
        self.batch_receipts[batch_token] = {"ratings": normalized, "result": result}
        self.batch = None
        for preview, item in zip(cards, normalized):
            try:
                self.col.decks.select(batch["deck_id"])
                queued = self.col.sched.get_queued_cards(fetch_limit=1000)
                fresh = next((q for q in queued.cards if q.card.id == item["card_id"]), None)
                if fresh is None:
                    result["message"] = "A card is no longer queued; remaining cards were not saved."
                    break
                card = self.col.get_card(item["card_id"])
                card.start_timer()
                self.active = {"deck_id": batch["deck_id"], "card": card,
                               "states": fresh.states, "front": preview, "revealed": True}
                receipt = self.rate_card(preview["review_token"], item["rating"])
                result["receipts"].append(receipt)
                if receipt["recorded"] is True:
                    result["unrecorded_card_ids"].remove(card.id)
                    result["recorded_count"] += 1
                elif receipt["recorded"] is None:
                    result["unrecorded_card_ids"].remove(card.id)
                    result["uncertain_card_ids"].append(card.id)
                if not receipt["service_available"]:
                    result["message"] = "Storage error; inspect receipts before continuing."
                    break
            except Exception:
                self.active = None
                result["message"] = "Batch stopped; remaining cards were not attempted."
                break
        if len(result["receipts"]) == len(normalized) and all(
                r["recorded"] is True and r["service_available"] for r in result["receipts"]):
            result["status"] = "recorded" if normalized else "cancelled"
        return result
