# ClothShop – Omnichannel Retail & Supply Chain trên ERPNext

Hệ thống quản trị chuỗi cung ứng và bán lẻ đa kênh cho chuỗi cửa hàng thời trang, xây trên **ERPNext v15** + **Webshop** + custom app **`omni_retail`**, chạy hoàn toàn bằng Docker Compose.

## Cài đặt trên máy mới (dùng image có sẵn trên Docker Hub)

Chỉ cần Docker và Docker Compose v2, không cần mã nguồn. Máy nên có tối thiểu 4 GB RAM và khoảng 10 GB ổ trống.

```bash
mkdir clothshop && cd clothshop
curl -fsSLO https://raw.githubusercontent.com/vnminh/ClothShop/main/deploy/docker-compose.yml
curl -fsSL  https://raw.githubusercontent.com/vnminh/ClothShop/main/deploy/.env.example -o .env
# sửa .env nếu cần: mật khẩu, cổng, OPENROUTER_API_KEY
docker compose up -d                  # kéo image leevox/clothshop-omni:v15 (~2,8 GB)
docker compose logs -f create-site    # chờ dòng ">>> Hoàn tất"
```

Windows (PowerShell) thay `curl` bằng:

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/vnminh/ClothShop/main/deploy/docker-compose.yml -OutFile docker-compose.yml
Invoke-WebRequest https://raw.githubusercontent.com/vnminh/ClothShop/main/deploy/.env.example -OutFile .env
```

Cập nhật lên bản mới: `docker compose pull && docker compose up -d` (dữ liệu nằm trong Docker volume nên được giữ nguyên; script khởi tạo tự chạy `migrate`).

Truy cập từ máy khác trong mạng LAN: đặt `SITE_NAME` trong `.env` thành địa chỉ bạn sẽ gõ trên trình duyệt (ví dụ IP `192.168.1.10`) **trước lần chạy đầu tiên**, rồi mở `http://192.168.1.10:8080`.

## Chạy từ mã nguồn (phát triển)

```bash
git clone https://github.com/vnminh/ClothShop.git && cd ClothShop
cp .env.example .env        # điền OPENROUTER_API_KEY nếu muốn dùng AI thật
docker compose up -d --build
docker compose logs -f create-site   # chờ dòng ">>> Hoàn tất"
```

Lần đầu mất khoảng 10–15 phút (tạo site, cài app, nạp dữ liệu demo gồm 78 tuần doanh số).

| Địa chỉ | Nội dung |
|---|---|
| http://clothshop.localhost:8080 | Webshop cho khách hàng |
| http://clothshop.localhost:8080/app | Giao diện quản trị (desk) |
| http://clothshop.localhost:8080/shipper | Cổng shipper (dùng tốt trên điện thoại) |
| http://localhost:8025 | Mailpit – xem email hệ thống gửi (email PO cho NCC, thông báo đơn) |

`clothshop.localhost` tự trỏ về máy bạn trên Chrome/Firefox/Edge. Vẫn vào được bằng `http://localhost:8080`, nhưng khi đó thông báo realtime trên desk không hoạt động (Frappe kiểm tra tên site).

### Tài khoản demo

Mật khẩu chung: `ClothShop@2026` (Administrator: theo `ADMIN_PASSWORD` trong `.env`, mặc định `admin`).

| Actor | Tài khoản | Vào đâu |
|---|---|---|
| Quản trị | `Administrator` | `/app` |
| Quản lý điểm bán lẻ | `quanly@clothshop.local` | `/app` → workspace **Điểm bán lẻ** |
| Quản lý kho | `kho@clothshop.local` | `/app` → workspace **Kho & Mua hàng** |
| Nhân viên bán hàng | `banhang@clothshop.local` | `/app` → workspace **Điểm bán lẻ** |
| Shipper | `shipper@clothshop.local` | `/shipper` |
| Khách hàng | `khach@clothshop.local` | Webshop |

## Ánh xạ nghiệp vụ → ERPNext

| Thực thể | DocType |
|---|---|
| Nhà cung cấp | `Supplier` (+ trường *Email nhận đơn đặt hàng*) |
| POS / điểm bán lẻ | `Retail Store` (custom) → tự sinh `Warehouse` con + `POS Profile` |
| Dòng sản phẩm | `Item Group` |
| Sản phẩm | `Item` (sản phẩm mẫu + biến thể Kích cỡ/Màu) |
| Lô sản phẩm | `Batch` (tự tạo khi nhập kho, xuất FIFO) |
| Đơn nhập hàng | `Purchase Order` → `Purchase Receipt` |
| Đơn xuất hàng | `Material Request` → `Stock Entry` (kho trung tâm → điểm bán); `Delivery Note` (xuất cho khách) |
| Khách hàng | `Customer` + `Loyalty Program` |
| Đơn hàng | `Sales Order` (online) / `POS Invoice` (tại quầy) |
| Chương trình khuyến mãi | `Promotional Scheme`, `Pricing Rule`, `Coupon Code`, `Loyalty Program` |
| Kế hoạch mua hàng AI | `Purchase Plan` (custom), `Seasonal Event` (custom) |

Tồn kho: một **Kho trung tâm** nhận hàng từ NCC; mỗi điểm bán là một kho con có tồn riêng. Đơn giao tại nhà xuất từ kho trung tâm, đơn nhận tại điểm bán trừ tồn của điểm bán đó.

## Vòng đời đơn online

```
Giao tại nhà:      Chờ xác nhận → Đang xử lý → Sẵn sàng giao hàng → Đang giao hàng → Thành công → (Đã trả hàng)
                                                                        └→ Giao thất bại → giao lại | Đã hủy
Nhận tại điểm bán: Chờ xác nhận → Đang xử lý → Sẵn sàng nhận tại điểm bán → Thành công | Đã hủy (quá hạn)
```

| Bước | Ai thực hiện | Hệ thống làm gì |
|---|---|---|
| Đặt hàng | Khách (Webshop) | Tạo `Sales Order`, kiểm tồn tại kho xuất, **giữ tồn** (Stock Reservation) |
| → Đang xử lý | Nhân viên | Ghi nhận người tiếp nhận. Đơn chuyển khoản: nút *Xác nhận đã nhận chuyển khoản* tạo `Payment Entry` ứng trước |
| → Sẵn sàng | Nhân viên | Kiểm tồn thực; đơn chuyển khoản bắt buộc đã xác nhận tiền; email khách (đơn nhận tại điểm bán) |
| → Đang giao hàng | Shipper nhận đơn | `Delivery Note` (trừ kho, tự chọn lô FIFO), gán shipper |
| → Thành công | Shipper / nhân viên tại quầy | `Sales Invoice` + `Payment Entry` (thu COD), cộng điểm tích lũy |
| → Giao thất bại | Shipper (bắt buộc lý do) | Phiếu trả hàng nhập lại kho; nhân viên chọn giao lại hoặc hủy |
| → Đã hủy | Khách (chỉ khi *Chờ xác nhận*), nhân viên (trước khi *Đang giao*), hệ thống | Hủy/đóng đơn, trả tồn; đánh dấu *Cần hoàn tiền* nếu đã thanh toán |
| → Đã trả hàng | Nhân viên, trong N ngày | Nhập lại kho + `Credit Note`, đánh dấu *Cần hoàn tiền* |

Đơn nhận tại điểm bán không đến lấy sau N ngày (mặc định 5) sẽ tự hủy bởi job hằng ngày. Các tham số nằm ở **Omni Retail Settings**.

Thao tác của nhân viên nằm trong nhóm nút **Xử lý đơn online** trên form Sales Order; tiến trình và lịch sử hiển thị ngay đầu form. Khách xem tiến trình tại trang đơn hàng trên Webshop.

## AI Agent dự báo nhu cầu & kế hoạch mua hàng

Chạy tự động (mặc định thứ Hai hằng tuần) hoặc bấm **Chạy AI dự báo ngay** trong danh sách *Purchase Plan*.

1. **Tổng hợp dữ liệu**: doanh số theo tuần của từng SKU (78 tuần), tồn toàn hệ thống, hàng đang về, sự kiện/mùa vụ (`Seasonal Event`) và khuyến mãi còn hiệu lực trong kỳ dự báo.
2. **Dự báo nền (thống kê)**: tốc độ bán 8 tuần gần nhất có trọng số × hệ số mùa vụ cùng kỳ năm trước.
3. **AI điều chỉnh**: gửi dữ liệu cho DeepSeek qua OpenRouter; AI trả hệ số điều chỉnh + lý do cho từng sản phẩm và nhận định tổng quan. Kết quả được kiểm tra và chặn biên (mặc định 0.3×–3×).
4. **Số lượng đề xuất** = nhu cầu trong (lead time + kỳ phủ + tồn an toàn) − tồn − đang về, làm tròn theo số lượng đặt tối thiểu.
5. **Duyệt**: Quản lý kho sửa *SL duyệt mua* → **Duyệt & tạo đơn mua hàng** (mỗi NCC một `Purchase Order` nháp) → **Xác nhận PO & gửi email nhà cung cấp** (kèm PDF).

Không có API key hoặc API lỗi thì hệ thống vẫn lập kế hoạch từ dự báo nền và ghi rõ điều đó trên chứng từ.

Cấu hình: `.env` (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`) hoặc **Omni Retail Settings** trên desk.

## Lệnh thường dùng

```bash
make up          # build + chạy
make logs        # theo dõi khởi tạo
make seed-demo   # nạp lại dữ liệu demo (bỏ qua phần đã có)
make forecast    # chạy AI dự báo ngay
make test        # unit test
make restart     # nạp lại code Python sau khi sửa apps/omni_retail
make migrate     # sau khi sửa DocType / custom field
make clean       # XÓA toàn bộ dữ liệu
```

`apps/omni_retail` và `docker/init-site.sh` được mount vào container nên sửa code không cần build lại image.

### Build và đẩy image

Dockerfile **clone mã nguồn từ GitHub** (`REPO_URL`, mặc định repo này) thay vì copy từ máy build, nên phải `git push` trước rồi mới build:

```bash
git push origin main
docker login
make push        # build từ commit mới nhất của nhánh main, gắn tag v15, latest và mã commit, rồi đẩy lên Docker Hub
```

Đổi tên image bằng `make push IMAGE=tenban/clothshop-omni`. Mã commit đã build nằm trong image tại `/home/frappe/frappe-bench/CLOTHSHOP_COMMIT`.

## Cấu trúc mã nguồn

```
docker-compose.yml, .env.example, Makefile   chạy từ mã nguồn
deploy/                 docker-compose.yml + .env.example để cài từ image Docker Hub
docker/                 Dockerfile (clone repo), init-site.sh (tạo site, cài app, thiết lập, nạp demo)
apps/omni_retail/omni_retail/
  hooks.py
  constants.py          vai trò, trạng thái đơn
  orders/               state_machine.py (thuần), service.py (tác động kho/kế toán), api.py, checkout.py, tasks.py
  forecasting/          baseline.py (thuần), data.py, llm.py (OpenRouter), planner.py, tasks.py
  omni_retail/doctype/  Retail Store, Purchase Plan (+Item), Seasonal Event, Omni Retail Settings, Order Status Log
  setup/                install.py (thiết lập nền), demo.py (dữ liệu demo), masters.py
  public/               sales_order.js (desk), omni_web.js + css (Webshop)
  www/shipper/          cổng shipper
  tests/test_pure.py    unit test state machine, dự báo, parse kết quả AI
```

## Giới hạn hiện tại

- **AI thật chưa được gọi thử**: chưa có `OPENROUTER_API_KEY` nên đường gọi DeepSeek mới được kiểm chứng với một máy chủ giả lập cùng định dạng OpenRouter. Điền key vào `.env`, chạy `docker compose up -d` rồi `make forecast` để thử thật.
- **Phân quyền theo từng cửa hàng** chưa giới hạn dữ liệu: quản lý/nhân viên điểm bán nhìn thấy đơn của mọi cửa hàng. Có thể thêm bằng `User Permission` trên `Retail Store`.
- **Trả hàng** là trả toàn bộ đơn; hệ thống đánh dấu *Cần hoàn tiền* và tạo Credit Note, việc chi tiền hoàn do kế toán thực hiện.
- **Tồn POS** chỉ trừ kho khi đóng ca (hành vi chuẩn của ERPNext POS).
- Lịch sử bán demo là 78 hóa đơn tổng hợp theo tuần, không tách theo cửa hàng.
- Một số nhãn của Webshop/ERPNext chưa có bản dịch tiếng Việt.
