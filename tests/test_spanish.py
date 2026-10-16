from anki_review.review import ReviewService, SPANISH_A1, create_demo


def test_spanish_deck_has_two_directions_for_each_word(tmp_path):
    path = tmp_path / "collection.anki2"
    info = create_demo(path, spanish=True)
    assert info["notes"] == 20
    assert info["cards"] == 40
    service = ReviewService(path)
    try:
        notes = service.col.find_notes("")
        assert len(notes) == 20
        expected = set(SPANISH_A1)
        for note_id in notes:
            note = service.col.get_note(note_id)
            assert (note["Front"], note["Back"]) in expected
            cards = note.cards()
            assert {card.ord for card in cards} == {0, 1}
            for card in cards:
                prompt = note["Front"] if card.ord == 0 else note["Back"]
                assert prompt in card.question()
        assert service.col.db.scalar("select count(*) from revlog") == 0
    finally:
        service.close()
