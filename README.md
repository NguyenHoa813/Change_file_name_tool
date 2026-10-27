# Đổi tên tệp tự động

Chạy chương trình:

```powershell
python file_renamer.py
```

Trong giao diện, công thức được chia theo các tab `Filename`, `Number`, `Data`, `File info` và `Time`. Đặt con trỏ vào thanh mẫu tên rồi nhấp một công thức để chèn công thức tại đúng vị trí đó.

Để chỉ mở giao diện và không mở cửa sổ terminal trên Windows, hãy nhấn đúp vào [file_renamer.pyw](./file_renamer.pyw). File `.pyw` chạy bằng `pythonw.exe`; file `.py` phía trên chỉ dùng khi cần chạy/debug từ terminal.

Ứng dụng chỉ dùng thư viện chuẩn Python nên không cần cài thêm package.

## Cú pháp mẫu

- `<name>`: tên tệp không có phần mở rộng.
- `<ext>`: phần mở rộng không có dấu chấm.
- `<date:yyyy-MM-dd>`: ngày hiện tại; cũng hỗ trợ `HH`, `mm`, `ss`.
- `<Inc Nr:001>`: số thứ tự, bắt đầu từ 001 sau mỗi lần bấm **Bắt đầu**.
- `<Inc Nr:0001>` và `<Inc Nr:00001>`: số thứ tự có độ rộng cố định.
- Ô **Số bắt đầu đếm** cho phép chọn số đầu tiên; dừng hoặc đổi mẫu tên sẽ reset bộ đếm.

Ví dụ: `TaiLieu_<date:yyyy-MM-dd>_<Inc Nr:001>`.

Khi bấm **Bắt đầu**, các tệp đã có sẵn được ghi nhận và bỏ qua. Chỉ tệp xuất hiện sau đó mới được xử lý. Log được ghi vào `rename_log.txt` trong thư mục theo dõi.

## Hướng dẫn sử dụng file EXE

### 1. Mở ứng dụng

Nhấn đúp vào [AutoFileRenamer.exe](./dist/AutoFileRenamer.exe). File EXE đã đóng gói sẵn Python và thư viện cần thiết, không cần cài Python hoặc chạy terminal.

Nếu Windows hiện cảnh báo SmartScreen, chọn **More info** rồi **Run anyway** nếu bạn tin cậy file EXE và file được lấy từ nguồn của bạn.

### 2. Chọn thư mục theo dõi

1. Nhấn nút **Chọn...**.
2. Chọn thư mục sẽ nhận các file mới.
3. Chỉ những file được đưa vào sau khi nhấn **Bắt đầu** mới được xử lý.

Các file đã có sẵn trước thời điểm bắt đầu sẽ không bị đổi tên.

### 3. Chọn loại file

Có thể chọn các phần mở rộng có sẵn:

- `.png`
- `.tif`
- `.pdf`
- `.docx`

Bạn cũng có thể:

- Chọn **Mọi loại tệp** để xử lý tất cả phần mở rộng.
- Nhập phần mở rộng khác, ví dụ: `jpg, jpeg, xlsx`.

### 4. Tạo mẫu tên

Đặt con trỏ vào ô **Mẫu tên**, sau đó nhấp vào một công thức trong các tab. Công thức sẽ được chèn ngay tại vị trí con trỏ.

Các nhóm công thức gồm:

- `Filename`: tên file, phần mở rộng, thư mục chứa.
- `Number`: số thứ tự, chữ cái, số Hex, số La Mã.
- `Data`: ngày hiện tại.
- `File info`: kích thước và thông tin file.
- `Time`: thời gian hiện tại.

Ví dụ:

```text
TaiLieu_<date:yyyy-MM-dd>_<Inc Nr:0001>
```

Kết quả có thể là:

```text
TaiLieu_2026-10-27_0001.pdf
TaiLieu_2026-10-27_0002.pdf
```

### 5. Chọn số bắt đầu

Trong phần **Công thức**, nhập số vào ô **Số bắt đầu đếm**.

Ví dụ:

- Số bắt đầu `100` + `<Inc Nr:0001>` → `0100`, `0101`, `0102`.
- Số bắt đầu `100` + `<Inc Nr:00001>` → `00100`, `00101`, `00102`.

Bộ đếm sẽ quay lại số bắt đầu khi:

- Nhấn **Dừng** rồi nhấn **Bắt đầu** lại.
- Thay đổi mẫu tên.
- Nhấn **Bắt đầu** lại sau khi đã dừng.

### 6. Bắt đầu và dừng

1. Kiểm tra thư mục, loại file và mẫu tên.
2. Nhấn **Bắt đầu**.
3. Đưa file mới vào thư mục đã chọn.
4. Chương trình sẽ chờ file ghi xong rồi tự đổi tên.
5. Nhấn **Dừng** khi không muốn theo dõi nữa.

Thanh nút **Bắt đầu**, **Dừng** và trạng thái luôn nằm ở cuối cửa sổ. Nếu cửa sổ thấp, phần cấu hình phía trên có thể cuộn bằng thanh cuộn hoặc con lăn chuột.

### 7. File log và lỗi trùng tên

Ứng dụng tạo file `rename_log.txt` trong thư mục được theo dõi. Log ghi lại thời gian bắt đầu, dừng, file đã đổi tên và lỗi phát sinh.

Nếu tên mới đã tồn tại, ứng dụng sẽ:

- Hiện thông báo lỗi.
- Không ghi đè file đang tồn tại.
- Ghi lỗi vào `rename_log.txt`.
