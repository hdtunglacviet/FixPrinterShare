# 🖨️ PrinterShare Setup

Công cụ cấu hình chia sẻ máy in qua mạng LAN trên Windows 11, kèm bộ fix lỗi máy in thường gặp. Giao diện đồ họa Python/Tkinter, chạy một lần trên máy chủ là xong.

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|---|---|
| Hệ điều hành | Windows 10 / 11 (Pro, Home, Enterprise) |
| Python | 3.8 trở lên |
| Quyền | Administrator (tự động xin UAC khi chạy) |
| Thư viện | Chỉ dùng thư viện chuẩn — không cần `pip install` |

---

## Cài đặt & Chạy

```bash
# Clone hoặc tải file về
git clone https://github.com/yourname/printshare
cd printshare

# Chạy trực tiếp (tự động xin quyền Admin qua UAC)
python printshare.py
```

> **Lưu ý:** Nếu Python chưa được thêm vào PATH, chuột phải vào `printshare.py` → *Open with* → *Python*.

---

## Tính năng

### Tab 1 — Setup Chia Sẻ

Hiển thị thông tin hệ thống thực tế và thực hiện 8 bước cấu hình tự động:

**Thông tin hiển thị:**
- Tên OS, Build, Edition (cảnh báo nếu là Win11 Home)
- Computer name, Workgroup
- Máy in mặc định, danh sách máy in đang được share
- Trạng thái **File & Printer Sharing** và **Password Protected Sharing**

**8 bước setup tự động sau khi nhấn *Chạy Setup*:**

| Bước | Nội dung |
|---|---|
| 1 | Tạo Local User với username/password nhập vào |
| 2 | Thêm user vào nhóm **Users** (đủ quyền truy cập máy in) |
| 3 | Đặt *Deny log on locally* — user không thể đăng nhập trực tiếp vào máy chủ |
| 4 | Chuyển profile mạng sang **Private** nếu đang ở Public |
| 5 | Bật Network Discovery và File & Printer Sharing |
| 6 | Bật **Password Protected Sharing** cho All Networks |
| 7 | Kích hoạt Firewall rules và ổn định Print Spooler |
| 8 | Chạy `gpupdate /force` — áp dụng ngay, không cần khởi động lại |

**Sau khi chạy xong**, máy con kết nối bằng:
```
\\<TEN_MAY_CHU>
Username: <username vừa tạo>
Password: <password vừa tạo>
```

**Hỗ trợ Win11 Home:** Bước 3 dùng `SpecialAccounts` registry thay vì `secedit` (không có trên Home edition).

---

### Tab 2 — Fix Lỗi Máy In

Bộ 17 fix lỗi máy in thường gặp, mỗi fix chạy PowerShell trong thread riêng và hiển thị log real-time.

#### Lỗi kết nối mạng

| Lỗi | Nguyên nhân | Cách fix |
|---|---|---|
| `0x0000007c` | RpcAuthnLevel — thường xuất hiện sau Windows Update | Tắt `RpcAuthnLevelPrivacyEnabled` |
| `0x0000011b` | RPC Authentication bị chặn | Tắt RpcAuthnLevel + bật RpcOverNamedPipes/Tcp |
| `0x00000040` | Firewall chặn File & Printer Sharing | Bật lại rule Firewall |
| `0x00000bc4` | Không thấy máy in trên mạng | Cấu hình RpcOverTcp + RpcOverNamedPipes (2 tùy chọn) |
| `0x000006d9` | Windows Firewall service bị tắt | Khởi động lại `MpsSvc` |
| `0x00000012` | Máy in offline / lỗi RPC | Reset RPC + Spooler |
| **Printer Cannot Connect** | Lỗi tổng hợp kết nối mạng | 7 bước: Firewall + RPC + mscms.dll + Services |

#### Lỗi cài đặt & driver

| Lỗi | Nguyên nhân | Cách fix |
|---|---|---|
| `0x00000709` | Không đặt được máy in mặc định | Reset registry Devices + bật Internet Printing |
| `0x000003eb` | Driver không khớp | Xóa spool queue + reset RpcAuthnLevel |
| `0x00000771` | Registry Devices/Printers bị hỏng | Xóa toàn bộ registry máy in của user |
| **Canon Communication Error** | Lỗi USB Canon LBP2900/3300 | Xóa USB Monitor registry + reset Spooler |

#### Tiện ích

| Tính năng | Mô tả |
|---|---|
| Xóa hàng đợi in | Xóa tất cả print job đang kẹt |
| Restart Print Spooler | Khởi động lại dịch vụ Spooler |
| Reset USB Monitor | Xóa registry USB Monitor (fix máy in USB không nhận) |
| **FULL CLEAN DriverStore** | Xóa toàn bộ driver máy in khỏi DriverStore *(không thể hoàn tác — có hộp xác nhận)* |

---

## Ghi chú kỹ thuật

### Phát hiện trạng thái PPS

Password Protected Sharing trên **Windows 11 24H2** không còn lưu vào registry. Trạng thái được đọc qua SMB CIM layer:

```powershell
(Get-SmbServerConfiguration).EnableAuthenticateUserSharing
# True  = PPS ON
# False = PPS OFF
```

Và được bật bằng:

```powershell
Set-SmbServerConfiguration -EnableAuthenticateUserSharing $true -Force
```

> Registry `ForceGuest` / `AllowInsecureGuestAuth` vẫn được ghi thêm để tương thích với các build Windows cũ hơn.

### Phát hiện trạng thái FPS

File & Printer Sharing được kiểm tra bằng cách đếm số Firewall rule `SMB-In` đang `Enabled`, kết hợp kiểm tra service `LanmanServer` đang chạy — tránh lỗi false-positive do Windows tạo rule riêng cho mỗi network profile.

### Deny Logon locally

| Edition | Phương pháp |
|---|---|
| Pro / Enterprise | `secedit` → `SeDenyInteractiveLogonRight` |
| Home | `SpecialAccounts\UserList` — ẩn user khỏi màn hình đăng nhập |

---

## Cấu trúc file

```
printshare/
├── printshare.py      # Toàn bộ ứng dụng (single-file)
└── README.md
```

---

## Build thành .exe (tùy chọn)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=printer.ico printshare.py
# Output: dist\printshare.exe
```

---

## License

MIT License — Huỳnh Đức Tùng
