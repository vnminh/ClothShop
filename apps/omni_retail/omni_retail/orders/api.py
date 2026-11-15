"""API whitelisted cho desk, webshop và cổng shipper."""

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from omni_retail.constants import (
	ACTOR_CUSTOMER,
	ACTOR_SHIPPER,
	ACTOR_STAFF,
	CANCELLED,
	DELIVERY_PICKUP,
	DONE,
	FAILED,
	PAY_TRANSFER,
	PENDING,
	PROCESSING,
	READY_PICKUP,
	READY_SHIP,
	RETURNED,
	ROLE_SHIPPER,
	SHIPPING,
)
from omni_retail.orders import service


@frappe.whitelist()
def transition(sales_order, to_status, note=None):
	return service.transition(sales_order, to_status, note)


@frappe.whitelist()
def confirm_payment(sales_order, reference=None):
	return service.confirm_payment(sales_order, reference)


@frappe.whitelist()
def cancel_my_order(sales_order, note=None):
	return service.transition(sales_order, CANCELLED, note or "Khách hàng hủy đơn")


@frappe.whitelist()
def get_order_tracking(sales_order):
	"""Thông tin theo dõi đơn: trạng thái, timeline, thao tác được phép với người gọi."""
	so = frappe.get_doc("Sales Order", sales_order)
	if not cint(so.get("omni_is_online")):
		return None
	kinds = service.actor_kinds(so)
	is_staff = ACTOR_STAFF in kinds
	if not (is_staff or ACTOR_CUSTOMER in kinds or so.get("omni_shipper") == frappe.session.user):
		frappe.throw("Không có quyền xem đơn này.", frappe.PermissionError)

	logs = frappe.get_all(
		"Order Status Log",
		filters={"sales_order": so.name},
		fields=["from_status", "to_status", "log_time", "note", "actor_name"],
		order_by="log_time asc, creation asc",
	)
	if not is_staff:
		for row in logs:
			row.pop("actor_name", None)

	if so.omni_delivery_method == DELIVERY_PICKUP:
		steps = [PENDING, PROCESSING, READY_PICKUP, DONE]
	else:
		steps = [PENDING, PROCESSING, READY_SHIP, SHIPPING, DONE]

	store = None
	if so.get("omni_pickup_store"):
		store = frappe.db.get_value(
			"Retail Store", so.omni_pickup_store, ["store_name", "address", "phone"], as_dict=True
		)
	s = service.settings()
	return {
		"name": so.name,
		"status": so.omni_status,
		"steps": steps,
		"delivery_method": so.omni_delivery_method,
		"payment_method": so.omni_payment_method,
		"payment_confirmed": cint(so.omni_payment_confirmed),
		"refund_required": cint(so.get("omni_refund_required")),
		"bank_transfer_info": s.bank_transfer_info
		if so.omni_payment_method == PAY_TRANSFER and not cint(so.omni_payment_confirmed)
		else None,
		"store": store,
		"shipper": frappe.utils.get_fullname(so.omni_shipper) if so.get("omni_shipper") else None,
		"logs": logs,
		"actions": service.allowed_actions(so),
		"is_staff": is_staff,
		"can_confirm_payment": bool(
			is_staff
			and so.omni_payment_method == PAY_TRANSFER
			and not cint(so.omni_payment_confirmed)
			and so.omni_status not in (CANCELLED, RETURNED, DONE)
			and so.docstatus == 1
		),
	}


# ----------------------------------------------------------------------------
# Shipper
# ----------------------------------------------------------------------------


def _require_shipper():
	roles = frappe.get_roles()
	if ROLE_SHIPPER not in roles and "System Manager" not in roles:
		frappe.throw("Chỉ dành cho shipper.", frappe.PermissionError)


def _order_card(name):
	so = frappe.get_doc("Sales Order", name)
	collect = 0 if cint(so.omni_payment_confirmed) else max(flt(so.rounded_total or so.grand_total) - flt(so.advance_paid), 0)
	addr_name = so.get("shipping_address_name") or so.get("customer_address")
	address, addr_phone = "", ""
	if addr_name:
		a = frappe.db.get_value(
			"Address", addr_name, ["address_line1", "address_line2", "city", "state", "phone"], as_dict=True
		)
		if a:
			address = ", ".join(x.strip() for x in (a.address_line1, a.address_line2, a.city, a.state) if x and x.strip())
			addr_phone = a.phone or ""
	return {
		"name": so.name,
		"status": so.omni_status,
		"customer_name": so.customer_name,
		"phone": so.get("contact_mobile") or so.get("contact_phone") or addr_phone,
		"address": address,
		"grand_total": flt(so.rounded_total or so.grand_total),
		"collect_amount": collect,
		"payment_method": so.omni_payment_method,
		"attempts": cint(so.omni_delivery_attempts),
		"items": [
			{"item_name": d.item_name + (" (quà tặng)" if cint(d.get("is_free_item")) else ""), "qty": d.qty}
			for d in so.items
		],
		"modified": so.modified,
	}


@frappe.whitelist()
def shipper_board():
	_require_shipper()
	user = frappe.session.user
	base = {"docstatus": 1, "omni_is_online": 1}
	available = frappe.get_all(
		"Sales Order", filters={**base, "omni_status": READY_SHIP}, pluck="name", order_by="omni_ready_at asc"
	)
	mine = frappe.get_all(
		"Sales Order",
		filters={**base, "omni_status": SHIPPING, "omni_shipper": user},
		pluck="name",
		order_by="modified asc",
	)
	history = frappe.get_all(
		"Sales Order",
		filters={"omni_is_online": 1, "omni_status": ["in", [DONE, FAILED]], "omni_shipper": user},
		pluck="name",
		order_by="modified desc",
		limit=15,
	)
	return {
		"user": frappe.utils.get_fullname(user),
		"available": [_order_card(n) for n in available],
		"mine": [_order_card(n) for n in mine],
		"history": [_order_card(n) for n in history],
	}


@frappe.whitelist()
def shipper_action(sales_order, action, note=None):
	_require_shipper()
	target = {"pickup": SHIPPING, "delivered": DONE, "failed": FAILED}.get(action)
	if not target:
		frappe.throw("Thao tác không hợp lệ.")
	return service.transition(sales_order, target, note)
