import frappe
from frappe.utils import cint

from omni_retail.constants import DELIVERY_HOME, DELIVERY_PICKUP, PAY_COD, PENDING


def sales_order_before_validate(doc, method=None):
	"""Đơn từ Webshop (hoặc đơn nhân viên đánh dấu 'Đơn online') đi theo vòng đời omni."""
	if doc.docstatus != 0:
		return
	if doc.get("order_type") == "Shopping Cart":
		doc.omni_is_online = 1
	if not cint(doc.get("omni_is_online")):
		return

	if not doc.get("omni_status"):
		doc.omni_status = PENDING
	if not doc.get("omni_delivery_method"):
		doc.omni_delivery_method = DELIVERY_HOME
	if not doc.get("omni_payment_method"):
		doc.omni_payment_method = PAY_COD

	if doc.omni_delivery_method == DELIVERY_PICKUP:
		if not doc.get("omni_pickup_store"):
			frappe.throw("Vui lòng chọn điểm bán để nhận hàng.")
		warehouse = frappe.db.get_value("Retail Store", doc.omni_pickup_store, "warehouse")
	else:
		doc.omni_pickup_store = None
		warehouse = frappe.db.get_single_value("Omni Retail Settings", "central_warehouse")

	if warehouse:
		doc.set_warehouse = warehouse
		for row in doc.get("items") or []:
			row.warehouse = warehouse

	# giữ tồn cho đơn online (Stock Reservation) nếu đã bật trong Stock Settings
	if doc.meta.has_field("reserve_stock") and cint(
		frappe.db.get_single_value("Stock Settings", "enable_stock_reservation")
	):
		doc.reserve_stock = 1


def sales_order_on_submit(doc, method=None):
	if not cint(doc.get("omni_is_online")):
		return
	from omni_retail.orders.service import add_log

	# Webshop ghi đơn bằng quyền hệ thống -> hiển thị tên khách thay vì Administrator
	from_webshop = doc.get("order_type") == "Shopping Cart" and frappe.session.user == "Administrator"
	add_log(
		doc.name, None, doc.omni_status or PENDING, "Khách đặt hàng",
		actor_name=f"{doc.customer_name} (khách hàng)" if from_webshop else None,
	)
