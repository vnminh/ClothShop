"""Hằng số dùng chung. Không import frappe ở đây để unit test thuần chạy được."""

# Vai trò (actor)
ROLE_STORE_MANAGER = "Quản lý điểm bán lẻ"
ROLE_WAREHOUSE_MANAGER = "Quản lý kho"
ROLE_SALES_STAFF = "Nhân viên bán hàng"
ROLE_SHIPPER = "Shipper"
STAFF_ROLES = (ROLE_STORE_MANAGER, ROLE_WAREHOUSE_MANAGER, ROLE_SALES_STAFF, "System Manager")

# Trạng thái đơn online
PENDING = "Chờ xác nhận"
PROCESSING = "Đang xử lý"
READY_SHIP = "Sẵn sàng giao hàng"
READY_PICKUP = "Sẵn sàng nhận tại điểm bán"
SHIPPING = "Đang giao hàng"
DONE = "Thành công"
FAILED = "Giao thất bại"
CANCELLED = "Đã hủy"
RETURNED = "Đã trả hàng"
ALL_STATUSES = (PENDING, PROCESSING, READY_SHIP, READY_PICKUP, SHIPPING, DONE, FAILED, CANCELLED, RETURNED)

# Hình thức nhận hàng
DELIVERY_HOME = "Giao tại nhà"
DELIVERY_PICKUP = "Nhận tại điểm bán"

# Thanh toán
PAY_COD = "Thanh toán khi nhận hàng (COD)"
PAY_TRANSFER = "Chuyển khoản"

# Loại actor trong state machine
ACTOR_STAFF = "staff"
ACTOR_SHIPPER = "shipper"
ACTOR_CUSTOMER = "customer"
ACTOR_SYSTEM = "system"
