# Dấu hiệu văn phong AI trong tiếng Việt: đọc trước khi viết

Đây là tài liệu tham khảo **đọc trước khi soạn bài tiếng Việt**, không phải
sau khi soạn xong. `scripts/ai_structure.py` chỉ đo lại những gì đã lên
trang; tài liệu này giúp không tạo ra các dấu hiệu đó ngay từ đầu, và theo
đúng tinh thần của nguồn tham khảo: bắt lỗi sau khi viết luôn là công cụ yếu
hơn không mắc lỗi ngay từ đầu.

Nguồn tham khảo và bản quyền: các mẫu hình bên dưới được điều chỉnh từ
`humanizer/SKILL.md` (MIT License, Copyright 2025 Siqi Chen,
github.com/blader/humanizer, bản sao tham chiếu đã bị gitignore trong kho
này) và từ danh mục "Signs of AI writing" của Wikipedia
(en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing, do WikiProject AI
Cleanup duy trì, giấy phép CC BY-SA). Mọi ví dụ tiếng Việt dưới đây là văn
bản gốc do người viết tài liệu này soạn, không phải bản dịch từ ví dụ tiếng
Anh trong hai nguồn trên.

**Một dấu hiệu là một tín hiệu, không phải một bản án.** Người đọc phán đoán
văn bản AI "bằng cảm giác" thường không chính xác hơn việc đoán ngẫu nhiên là
bao nhiêu, và văn phong con người cũng đang dần hấp thụ các thói quen của AI.
Chỉ hành động khi nhiều dấu hiệu cùng xuất hiện trong một đoạn.

## 1. Không phải X mà là Y

Công thức này xuất hiện ở mọi ngôn ngữ; áp dụng cùng một cách xử lý.

**Trước:**
> Đây không chỉ là một chiếc bàn phím, mà là cả một trải nghiệm gõ phím
> hoàn toàn khác biệt.

**Sau:**
> Bàn phím cơ gõ êm hơn hẳn so với bàn phím màng cao su tôi dùng trước đó.

Nửa phủ định không sửa một ngộ nhận thật của người đọc, nó chỉ làm nửa khẳng
định nghe to hơn. Giữ cấu trúc này chỉ khi nửa phủ định đính chính một điều
người đọc thực sự tin.

## 2. Câu chốt một dòng lặp lại đoạn trước

**Trước:**
> Việc uống đủ nước giúp da khỏe hơn, tiêu hóa tốt hơn và tinh thần tỉnh táo
> hơn suốt cả ngày.
>
> Đó chính là điều quan trọng nhất.

**Sau:**
> Việc uống đủ nước giúp da khỏe hơn, tiêu hóa tốt hơn và tinh thần tỉnh táo
> hơn suốt cả ngày.

Câu chốt không thêm thông tin gì, chỉ yêu cầu người đọc dừng lại để suy
ngẫm. Cắt bỏ nó nếu nó chỉ nhắc lại ý câu trên; giữ nó chỉ khi nó mang một
sự kiện mới.

## 3. Cụm ba ép buộc

**Trước:**
> Khóa học này phù hợp với người mới bắt đầu, người đã có kinh nghiệm, và
> người muốn nâng cao kỹ năng.

**Sau:**
> Khóa học này phù hợp với người mới bắt đầu. Người đã có kinh nghiệm cũng
> có thể học thêm phần nâng cao ở buổi 5.

Ba vế song song nghe "đầy đủ" nhưng thường chỉ là một ý bị chẻ ba. Kiểm tra
xem mỗi vế có thực sự mang một ý riêng không; nếu không, gộp lại hoặc chọn
vế mạnh nhất để phát triển.

## 4. Mở đầu câu lặp lại liên tục

**Trước:**
> Chị ấy kiểm tra cửa. Chị ấy kiểm tra khóa. Chị ấy kiểm tra luôn cả cửa sổ.

**Sau:**
> Chị ấy kiểm tra cửa, khóa, rồi đến cả cửa sổ trước khi rời khỏi nhà.

Ba câu liên tiếp mở đầu giống hệt nhau là dấu hiệu nhịp điệu bị áp đặt theo
quy tắc thay vì theo tai. Không cấm lặp một chủ ngữ, chỉ cần tránh chuỗi ba
câu trở lên giống hệt nhau ở từ đầu.

## 5. In đậm mang tính trang trí

**Trước:**
> - **Tốc độ:** trang tải nhanh hơn.
> - **Chi phí:** gói cước hợp lý hơn.
> - **Hỗ trợ:** phản hồi trong ngày.

**Sau:**
> Trang tải nhanh hơn, gói cước hợp lý hơn, và đội hỗ trợ phản hồi trong
> ngày.

Nhãn in đậm kèm dấu hai chấm cho từng mục danh sách, lặp lại y hệt nhau,
thường không mang thông tin riêng biệt gì thêm ngoài việc tô đậm. Chuyển
thành văn xuôi khi nhãn không cần thiết cho việc tra cứu.

## 6. Tiêu đề trang trí

Tiếng Việt không có quy ước viết hoa từng chữ cái đầu như tiêu đề tiếng Anh
(Title Case), nên `ai_structure.py` bỏ qua kiểm tra này khi `--lang vi`.
Dấu hiệu tương đương trong tiếng Việt là **tiêu đề viết hoa toàn bộ** hoặc
gắn emoji/mũi tên trang trí lặp lại ở mọi mục.

**Trước:**
> ## 🚀 BÍ QUYẾT TĂNG TỐC ĐỘ TRANG WEB

**Sau:**
> ## Bí quyết tăng tốc độ trang web

## 7. Dấu ngoặc kép cong

**Trước:**
> Anh ấy nói “trang đã chạy ổn” nhưng đồng nghiệp không đồng ý.

**Sau:**
> Anh ấy nói "trang đã chạy ổn" nhưng đồng nghiệp không đồng ý.

Hầu hết trình soạn thảo tự động cong hóa dấu ngoặc kép, nên dấu hiệu này yếu
khi đứng một mình. Chỉ đáng chú ý khi đi cùng nhiều dấu hiệu khác trong cùng
một đoạn.

## 8. Tiêu đề bị lặp lại ngay câu đầu

**Trước:**
> ## Hiệu năng
>
> Hiệu năng rất quan trọng.
>
> Khi trang tải chậm, người dùng rời đi ngay lập tức.

**Sau:**
> ## Hiệu năng
>
> Khi trang tải chậm, người dùng rời đi ngay lập tức.

Câu đầu tiên sau tiêu đề chỉ nhắc lại tiêu đề trước khi vào nội dung thật.
Xóa câu nhắc lại, giữ câu mang thông tin.

## 9. Tàn dư hội thoại chatbot

**Trước:**
> Chắc chắn rồi! Dưới đây là phần tóm tắt bạn cần. Hy vọng bài viết này giúp
> ích cho bạn.

**Sau:**
> (Xóa toàn bộ phần mở đầu và kết thúc kiểu hội thoại; giữ lại nội dung tóm
> tắt thật sự.)

Đây là dấu hiệu chắc chắn nhất trong danh sách. Không cần cân nhắc thêm dấu
hiệu nào khác đi kèm, cắt bỏ ngay khi thấy.

## Dấu gạch ngang: xem `scripts/lint_prose.py`

Dấu gạch ngang dài (U+2014), gạch ngang ngắn (U+2013), và chuỗi ASCII khoảng
trắng-gạch ngang-gạch ngang-khoảng trắng đã bị cấm trong toàn bộ
`docs/`, `skills/`, `agents/`, `scripts/`, `tests/` của kho này. Tài liệu
này không lặp lại quy tắc đó; xem `scripts/lint_prose.py`.

## Những gì không đưa vào đây

Các dấu hiệu mang tính từ vựng của tiếng Việt (ví dụ "trong thời đại số
hóa", "không thể phủ nhận rằng") thuộc phạm vi `vi_profile.py` và
`analyze_blog.py` (G1 đến G3 của Phase G), không thuộc tài liệu này. Tài
liệu này chỉ tập trung vào các mẫu hình **cấu trúc**, độc lập với ngôn ngữ
và từ vựng, giống như cách `humanizer/SKILL.md` phân biệt hai loại dấu
hiệu.

## Công cụ đo lường

Chạy `python3 scripts/ai_structure.py <file> --lang vi` sau khi viết xong để
xem điểm cụm (cluster score): số loại dấu hiệu khác nhau cùng xuất hiện
trong một mục. Một dấu hiệu là nhiễu; bốn dấu hiệu trong cùng một đoạn thì
không.
