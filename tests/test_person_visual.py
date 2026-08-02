from game.person_visual import build_person_visual


def test_person_visual_is_deterministic_and_role_specific():
    first = build_person_visual(
        "resident_settlement_1_01", "farmer", state="resident")
    second = build_person_visual(
        "resident_settlement_1_01", "farmer", state="resident")
    guard = build_person_visual(
        "resident_settlement_1_01", "road_guard", state="resident")

    assert first == second
    assert first["outfit"] == "laborer"
    assert first["headwear"] == "hat"
    assert guard["outfit"] == "guard"
    assert guard["headwear"] == "helmet"


def test_person_visual_uses_age_and_public_condition():
    elder = build_person_visual("person_0042", "scholar", age=72)
    survivor = build_person_visual(
        "person_0042", "scholar", age=34, state="survivor")

    assert elder["age_group"] == "elder"
    assert survivor["age_group"] == "adult"
    assert survivor["expression"] == "weary"
    assert set(survivor) == {
        "version", "seed", "skin_tone", "hair_color", "hair_style",
        "face_shape", "age_group", "outfit", "headwear", "expression",
        "detail", "accent",
    }
