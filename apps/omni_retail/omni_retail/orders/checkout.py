"""Checkout mở rộng cho Webshop: chọn hình thức nhận hàng + thanh toán."""

import frappe
from frappe.utils import cint, flt

from omni_retail.constants import DELIVERY_HOME, DELIVERY_PICKUP, PAY_COD, PAY_TRANSFER
from omni_retail.orders.service import available_qty, settings


def _cart():
	from webshop.webshop.shopping_cart.cart import _get_cart_quotation

	return _get_cart_quotation()


def _shortages(quotation, warehouse):
	"""Danh sách mặt hàng trong giỏ không đủ tồn khả dụng tại `warehouse`."""
	out = []
	for row in quotation.get("items") or []:
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		have = available_qty(row.item_code, warehouse) if warehouse else 0
		if flt(row.qty) > have:
			out.append({"item_code": row.item_code, "item_name": row.item_name, "need": row.qty, "have": max(have, 0)})
	return out


@frappe.whitelist()
def get_checkout_options():
	quotation = _cart()
	s = settings()
	stores = []
	for st in frappe.get_all(
		"Retail Store",
		filters={"is_active": 1, "allow_pickup": 1},
		fields=["name", "store_name", "address", "phone", "warehouse"],
		order_by="store_name",
	):
		short = _shortages(quotation, st.warehouse)
		stores.append(
			{
				"name": st.name,
				"store_name": st.store_name,
				"address": st.address,
				"phone": st.phone,
				"in_stock": not short,
				"shortages": short,
			}
		)
	return {
		"delivery_methods": [DELIVERY_HOME, DELIVERY_PICKUP],
		"payment_methods": [PAY_COD, PAY_TRANSFER],
		"stores": stores,
		"home_shortages": _shortages(quotation, s.central_warehouse),
		"bank_transfer_info": s.bank_transfer_info,
		"pickup_expiry_days": cint(s.pickup_expiry_days) or 5,
		"selected": {
			"delivery_method": quotation.get("omni_delivery_method") or DELIVERY_HOME,
			"pickup_store": quotation.get("omni_pickup_store"),
			"payment_method": quotation.get("omni_payment_method") or PAY_COD,
		},
	}


@frappe.whitelist()
def place_order(delivery_method=None, pickup_store=None, payment_method=None):
	"""Thay cho webshop.place_order: kiểm tồn theo kho xuất thực tế của đơn."""
	from webshop.webshop.shopping_cart.cart import _make_sales_order, system_permissions

	delivery_method = delivery_method or DELIVERY_HOME
	payment_method = payment_method or PAY_COD
	if delivery_method not in (DELIVERY_HOME, DELIVERY_PICKUP):
		frappe.throw("Hình thức nhận hàng không hợp lệ.")
	if payment_method not in (PAY_COD, PAY_TRANSFER):
		frappe.throw("Hình thức thanh toán không hợp lệ.")

	quotation = _cart()
	if not quotation.get("items"):
		frappe.throw("Giỏ hàng đang trống.")

	if delivery_method == DELIVERY_PICKUP:
		store = frappe.db.get_value(
			"Retail Store",
			{"name": pickup_store, "is_active": 1, "allow_pickup": 1},
			["name", "store_name", "warehouse"],
			as_dict=True,
		)
		if not store:
			frappe.throw("Vui lòng chọn điểm bán để nhận hàng.")
		warehouse, where = store.warehouse, store.store_name
	else:
		pickup_store = None
		warehouse, where = settings().central_warehouse, "kho giao hàng"
		if not (quotation.shipping_address_name or quotation.customer_address):
			frappe.throw("Vui lòng thêm địa chỉ giao hàng.")

	short = _shortages(quotation, warehouse)
	if short:
		lines = "<br>".join(f"{d['item_name']}: cần {d['need']:g}, còn {d['have']:g}" for d in short)
		frappe.throw(f"Không đủ hàng tại {where}:<br>{lines}")

	cart_settings = frappe.get_cached_doc("Webshop Settings")
	quotation.company = cart_settings.company
	quotation.omni_delivery_method = delivery_method
	quotation.omni_pickup_store = pickup_store
	quotation.omni_payment_method = payment_method
	quotation.flags.ignore_permissions = True
	with system_permissions():
		quotation.submit()

	if quotation.quotation_to == "Lead" and quotation.party_name:
		frappe.defaults.set_user_default("company", quotation.company)

	with system_permissions():
		sales_order = frappe.get_doc(_make_sales_order(quotation.name, ignore_permissions=True))
	sales_order.payment_schedule = []
	sales_order.omni_is_online = 1
	sales_order.omni_delivery_method = delivery_method
	sales_order.omni_pickup_store = pickup_store
	sales_order.omni_payment_method = payment_method
	sales_order.flags.ignore_permissions = True
	with system_permissions():
		sales_order.insert()
		sales_order.submit()

	if hasattr(frappe.local, "cookie_manager"):
		frappe.local.cookie_manager.delete_cookie("cart_count")
	return sales_order.name
