from app.services.doubao import parse_refinement


def test_model_feedback_is_split_into_overall_then_focus():
    refinement = parse_refinement(
        '{"overall":"整体节奏跟上了，但动作还不够稳。",'
        '"focus":"重点看右脚：听到重拍再落地，先连做三次。"}'
    )

    assert refinement.overall == "整体节奏跟上了，但动作还不够稳。"
    assert refinement.focus == "重点看右脚：听到重拍再落地，先连做三次。"


def test_plain_model_feedback_remains_a_focus_fallback():
    refinement = parse_refinement("右脚像赶末班车，等重拍再落地。")

    assert refinement.overall is None
    assert refinement.focus == "右脚像赶末班车，等重拍再落地。"
