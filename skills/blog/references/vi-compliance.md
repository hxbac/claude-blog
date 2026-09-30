# Vietnamese compliance and E-E-A-T conventions

This is a practical checklist for a content team, not legal advice. It was
assembled from secondary sources listed in the survey
(the hub ecosystem survey (04-ecosystem-survey.md), section 3) and it has not been checked
against the primary legal texts. Wording marked **UNVERIFIED** could not be
sourced from the survey. For a sponsored campaign, a supplement or a property
listing, have the brand's legal or regulatory contact confirm the final text.
The machine checks below catch a missing disclosure; they do not certify that
a post is lawful.

## Frontmatter keys

| Key | Values | Effect |
| --- | --- | --- |
| `sponsored` | `true` | Gate 4 and Gate 5 require a sponsorship disclosure in the body |
| `affiliate` | `true` | Gate 4 and Gate 5 require an affiliate disclosure in the body |
| `topic_class` | `health`, `finance`, `realestate`, `cosmetics`, `general` | `health` plus a functional-food mention requires the disclaimer; every non-`general` class is YMYL |
| `author_credential` | text | Rendered in the author box (YMYL) |
| `reviewed_by` | text | Rendered as "Bài viết được tham vấn bởi ..." |

Posts without these keys are not affected. Set the keys honestly: the check
reads what the frontmatter says, and cannot know that a post is sponsored
when the key is missing.

## 1. Advertising Law amendment (effective 2026-01-01)

Source: Thư Viện Pháp Luật and LuatVietnam, 2025 (via the survey).

- Sponsored and affiliate content must be disclosed to the reader. Penalties
  of up to 80 million VND are reported for non-compliance.
- The survey does not give the amending law's number, article numbers, the
  required wording or which party (advertiser, publisher, creator) is fined.
  **UNVERIFIED**: all of those. Do not cite an article number from this file.
- Practice enforced here:
  - `sponsored: true` needs a visible line near the top saying the post is
    advertising or sponsored, naming the sponsor.
  - `affiliate: true` needs a visible line before the first affiliate link
    saying the post has affiliate links and may earn a commission.
- Sentences the gate suggests (drafting aids, not statutory text):
  - Sponsored: "Bài viết này là nội dung quảng cáo (tài trợ) được thực hiện với sự tài trợ của [tên nhà tài trợ]."
  - Affiliate: "Bài viết này có chứa liên kết tiếp thị (affiliate): chúng tôi có thể nhận hoa hồng khi bạn mua hàng qua các liên kết này, giá bạn trả không thay đổi."
- Recognised phrases (with or without diacritics): "nội dung quảng cáo",
  "bài viết tài trợ", "được tài trợ", "tài trợ bởi", "sponsored", "liên kết
  tiếp thị", "affiliate", "hoa hồng". A bare word such as "quảng cáo" in
  another sentence does not count.

## 2. Decree 147/2024/ND-CP (effective 2024-12-25)

Source: Ministry of Information and Communications, 2024 (via the survey).

- The survey records it only as "publisher responsibility". It governs
  internet services and online information, so whoever publishes the site is
  answerable for what it carries. That is a reason for the checks above to run
  before publishing, not after.
- **UNVERIFIED**: the specific obligations (account verification, content
  takedown times, registration duties). Nothing in the gates depends on them.

## 3. Circular 09/2015/TT-BYT, functional foods

Source: Vietnam Food Administration (VFA), 2015, described in the survey as
still in force.

- A post that advertises or promotes a functional food (thực phẩm chức năng,
  thực phẩm bảo vệ sức khỏe, TPCN) must carry a disclaimer that it is not a
  medicine. The gate requires both ideas: "không phải là thuốc" and "không có
  tác dụng thay thế thuốc chữa bệnh".
- Sentence the gate suggests: "Sản phẩm này không phải là thuốc và không có tác dụng thay thế thuốc chữa bệnh."
  **UNVERIFIED** as a word-for-word quotation of the circular; confirm the
  exact required text with the product's registered advertising dossier.
- Do not use images of doctors, pharmacists or other health workers to
  promote a functional food (the survey: "no doctor imagery"). This is not
  machine-checked; the reviewer checks hero and inline images and alt text.
  **UNVERIFIED**: the article, and whether a real expert quoted as a source
  (not as an endorsement) is treated differently.
- Do not claim a functional food cures, treats or prevents a disease.
  **UNVERIFIED** as to the exact legal basis; it follows from the "not a
  medicine" rule and from YMYL practice.

## 4. YMYL topics for Vietnam

"Your money or your life": Google holds these to a higher E-E-A-T bar, and
here they also carry legal exposure. Set `topic_class` for any of them.

| `topic_class` | Covers |
| --- | --- |
| `health` | Diseases, symptoms, treatment, medicines, supplements and thực phẩm chức năng, nutrition claims, mental health, pregnancy and child health |
| `finance` | Loans, credit, investment, stocks, crypto, insurance, tax, banking |
| `realestate` | Property buying, selling and renting, project reviews, planning and land law, valuation |
| `cosmetics` | Skincare, makeup and cosmetic products, treatments, cosmetic procedures (`mỹ phẩm`, `thẩm mỹ`) |
| `general` | Everything else (default) |

Real estate and cosmetics are listed because a wrong claim there costs the
reader money or health and both are advertising-regulated. The survey does not
cover their sector rules; **UNVERIFIED**: any sector-specific disclosure for
finance, real estate or cosmetics. Only `health` has a machine check today.

## 5. Author box for YMYL

For any non-`general` topic, put these in the frontmatter and let
`blog_render.py` render them:

```yaml
author: Nguyễn Thị Lan
author_credential: Dược sĩ đại học, 8 năm làm việc tại nhà thuốc bệnh viện
reviewed_by: BS. Trần Văn Minh, chuyên khoa Nội tiết
```

Rendered (only the lines whose keys are present, all values HTML-escaped):

> **Nguyễn Thị Lan**, Dược sĩ đại học, 8 năm làm việc tại nhà thuốc bệnh viện.
> Bài viết được tham vấn bởi **BS. Trần Văn Minh, chuyên khoa Nội tiết**.

Rules:

- Use a real person and a credential that can be verified. Never invent a
  reviewer or a title. If nobody reviewed the post, leave `reviewed_by` out.
- The credential is a frontmatter fact, not body prose. The writer must not
  write trust or contact boilerplate inside the body (draft rubric item 11).
- The box also feeds JSON-LD: `author.jobTitle` and `reviewedBy`.
- A reviewer named here is a person on a page. It is not the same as a doctor
  image in a functional-food promotion (section 3).

## What the gates check

| Situation | Where | Result |
| --- | --- | --- |
| `sponsored: true`, no sponsorship disclosure | Gate 4 (P0) and Gate 5 | blocked, message in Vietnamese with the sentence to add |
| `affiliate: true`, no affiliate disclosure | Gate 4 (P0) and Gate 5 | same |
| `topic_class: health`, mentions thực phẩm chức năng, no disclaimer | Gate 4 (P0) and Gate 5 | same |
| None of the keys set | | unaffected |

One implementation, `scripts/vi_compliance.py`, serves both gates.
