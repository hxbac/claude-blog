"""Phase N: Vietnamese repurpose scaffolds keep one register (vi_register)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import repurpose_vi
import vi_register

FIELDS = dict(
    title="Cách chọn máy pha cà phê cho gian bếp nhỏ",
    hook="Máy pha giá hai triệu và máy pha giá mười triệu khác nhau ở đâu.",
    points=["Áp suất ổn định quyết định vị của ly cà phê.",
            "Bình chứa nhỏ hợp căn hộ, bình lớn hợp văn phòng.",
            "Bộ phận xay rời dễ vệ sinh hơn bộ xay liền."],
    cta="Lưu bài này lại để đối chiếu khi đi mua máy.",
    link="https://example.vn/chon-may-pha-ca-phe",
    hashtags=["caphe", "maypha"],
)
OTHERS = {"peer": ("polite", "formal"), "polite": ("peer", "formal"), "formal": ("peer", "polite")}


@pytest.mark.parametrize("channel", repurpose_vi.CHANNELS)
@pytest.mark.parametrize("register", list(repurpose_vi.REGISTERS))
def test_scaffold_keeps_one_register(channel, register):
    text = repurpose_vi.render(channel, register, **FIELDS)
    result = vi_register.analyze_register(text)
    assert result["dominant_register"] == register
    assert result["consistent"] is True
    assert result["off_register"] == []
    assert result["tolerated"] == []
    for other in OTHERS[register]:
        assert result["sentence_counts"][other] == 0, (channel, register, other)


@pytest.mark.parametrize("channel", repurpose_vi.CHANNELS)
def test_scaffold_has_no_ai_tells(channel):
    for register in repurpose_vi.REGISTERS:
        report = repurpose_vi.check(repurpose_vi.render(channel, register, **FIELDS))
        assert report["ai_tell_count"] == 0, (channel, register, report["findings"])


def test_check_catches_a_field_that_switches_register():
    drifting = dict(FIELDS, hook="Bạn hỏi mình nhiều về chuyện này. Bạn cứ yên tâm.", points=[
        "Quý khách nên xem kỹ thông số trước khi mua.",
        "Quý khách cũng nên hỏi về chế độ bảo hành.",
        "Quý khách có thể đổi trả trong bảy ngày.",
    ])
    text = repurpose_vi.render("zalo_oa", "peer", **drifting)
    report = repurpose_vi.check(text)
    assert report["register"]["consistent"] is False
    assert any(f["type"] == "register_drift" for f in report["findings"])


def test_channel_structure():
    fb = repurpose_vi.render("facebook", "peer", **FIELDS)
    assert "125 ký tự" in fb and "Hashtag: #caphe #maypha" in fb
    tt = repurpose_vi.render("tiktok", "peer", **FIELDS)
    assert "0 đến 3 giây" in tt and "Ý 3:" in tt
    zl = repurpose_vi.render("zalo_oa", "formal", **FIELDS)
    assert zl.splitlines()[0].startswith("# Zalo OA") and "Kính chào quý khách" in zl


def test_rejects_unknown_channel_and_register():
    with pytest.raises(ValueError):
        repurpose_vi.render("myspace", "peer", **FIELDS)
    with pytest.raises(ValueError):
        repurpose_vi.render("facebook", "gen-z", **FIELDS)
