import frappe
from frappe.utils import add_days, cint, now_datetime

from omni_retail.constants import CANCELLED, READY_PICKUP


def expire_pickup_orders():
	"""Hủy đơn nhận tại điểm bán mà khách không đến lấy sau N ngày, trả lại tồn."""
	from omni_retail.orders import service

	days = cint(frappe.db.get_single_value("Omni Retail Settings", "pickup_expiry_days")) or 5
	cutoff = add_days(now_datetime(), -days)
	names = frappe.get_all(
		"Sales Order",
		filters={"docstatus": 1, "omni_is_online": 1, "omni_status": READY_PICKUP, "omni_ready_at": ["<", cutoff]},
		pluck="name",
	)
	for name in names:
		try:
			service.transition(name, CANCELLED, f"Tự động hủy: quá {days} ngày không đến nhận hàng", system=True)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"omni_retail: không hủy được đơn quá hạn {name}")
	return names
