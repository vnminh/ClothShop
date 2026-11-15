"""Thực thi chuyển trạng thái đơn online + tác động kho/kế toán trên ERPNext."""

from contextlib import contextmanager

import frappe
from frappe.utils import cint, flt, now_datetime, nowdate

from omni_retail.constants import (
	ACTOR_CUSTOMER,
	ACTOR_SHIPPER,
	ACTOR_STAFF,
	ACTOR_SYSTEM,
	CANCELLED,
	DELIVERY_PICKUP,
	DONE,
	FAILED,
	PAY_TRANSFER,
	PROCESSING,
	READY_PICKUP,
	READY_SHIP,
	RETURNED,
	ROLE_SHIPPER,
	SHIPPING,
	STAFF_ROLES,
)
from omni_retail.orders.state_machine import TransitionError, check_transition, next_statuses


@contextmanager
def as_system():
	"""Chạy tác động chứng từ bằng quyền hệ thống (quyền nghiệp vụ đã kiểm ở state machine)."""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


def settings():
	return frappe.get_cached_doc("Omni Retail Settings")


def add_log(sales_order, from_status, to_status, note=None, actor=None, actor_name=None):
	actor = actor or frappe.session.user
	frappe.get_doc(
		{
			"doctype": "Order Status Log",
			"sales_order": sales_order,
			"from_status": from_status,
			"to_status": to_status,
			"actor": actor if frappe.db.exists("User", actor) else None,
			"actor_name": actor_name or frappe.utils.get_fullname(actor),
			"log_time": now_datetime(),
			"note": note,
		}
	).insert(ignore_permissions=True)


def customer_of_user(user=None):
	user = user or frappe.session.user
	if user in ("Guest", "Administrator"):
		return None
	contact = frappe.db.get_value("Contact", {"user": user}, "name") or frappe.db.get_value(
		"Contact", {"email_id": user}, "name"
	)
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name",
	)


def actor_kinds(so, user=None, system=False):
	"""Người dùng hiện tại đóng những vai nào đối với đơn `so`."""
	user = user or frappe.session.user
	kinds = set()
	if system:
		kinds.add(ACTOR_SYSTEM)
	roles = set(frappe.get_roles(user))
	if roles.intersection(STAFF_ROLES):
		kinds.add(ACTOR_STAFF)
	if "System Manager" in roles:
		kinds.add(ACTOR_SHIPPER)
	if ROLE_SHIPPER in roles:
		# shipper chỉ thao tác được đơn chưa ai nhận hoặc đơn của chính mình
		if not so.get("omni_shipper") or so.omni_shipper == user:
			kinds.add(ACTOR_SHIPPER)
	if so.customer and customer_of_user(user) == so.customer:
		kinds.add(ACTOR_CUSTOMER)
	return kinds


def allowed_actions(so, user=None):
	if not cint(so.get("omni_is_online")) or so.docstatus == 0:
		return []
	return next_statuses(so.omni_status, so.omni_delivery_method, actor_kinds(so, user))


def transition(sales_order, to_status, note=None, system=False):
	so = frappe.get_doc("Sales Order", sales_order, for_update=True)
	if not cint(so.get("omni_is_online")):
		frappe.throw("Đơn này không phải đơn online.")
	if so.docstatus != 1:
		frappe.throw("Đơn hàng chưa được ghi nhận hoặc đã hủy.")

	current = so.omni_status
	try:
		check_transition(current, to_status, so.omni_delivery_method, actor_kinds(so, system=system))
	except TransitionError as e:
		frappe.throw(str(e), frappe.PermissionError)

	actor = frappe.session.user
	updates = _run_effects(so, current, to_status, note, actor)

	updates["omni_status"] = to_status
	for field, value in updates.items():
		frappe.db.set_value("Sales Order", so.name, field, value, update_modified=False)
	frappe.db.set_value("Sales Order", so.name, "modified", now_datetime(), update_modified=False)

	add_log(so.name, current, to_status, note, actor=actor)
	_notify_customer(so, to_status, note)
	return {"sales_order": so.name, "status": to_status}


# ----------------------------------------------------------------------------
# Tác động theo từng bước
# ----------------------------------------------------------------------------


def _run_effects(so, current, target, note, actor):
	updates = {}
	if target == PROCESSING:
		updates["omni_handled_by"] = actor

	elif target in (READY_SHIP, READY_PICKUP):
		if so.omni_payment_method == PAY_TRANSFER and not cint(so.omni_payment_confirmed):
			frappe.throw("Đơn chuyển khoản: cần xác nhận đã nhận tiền trước khi báo sẵn sàng.")
		_check_stock(so)
		updates["omni_ready_at"] = now_datetime()
		if target == READY_SHIP:
			updates["omni_shipper"] = None

	elif target == SHIPPING:
		with as_system():
			_make_delivery_note(so)
		updates["omni_shipper"] = actor
		updates["omni_delivery_attempts"] = cint(so.omni_delivery_attempts) + 1

	elif target == DONE:
		with as_system():
			if so.omni_delivery_method == DELIVERY_PICKUP:
				_make_delivery_note(so)
			_invoice_and_collect(so)
		updates["omni_delivered_at"] = now_datetime()
		updates["omni_payment_confirmed"] = 1

	elif target == FAILED:
		if not (note or "").strip():
			frappe.throw("Vui lòng nhập lý do giao thất bại.")
		with as_system():
			_return_delivery(so)

	elif target == RETURNED:
		days = cint(settings().return_window_days) or 7
		delivered_at = so.get("omni_delivered_at")
		if delivered_at and frappe.utils.date_diff(nowdate(), delivered_at) > days:
			frappe.throw(f"Đã quá thời hạn trả hàng ({days} ngày).")
		with as_system():
			_return_delivery(so)
			_credit_note(so)
			# hàng đã nhập lại kho: đóng đơn để không còn giữ tồn / chờ giao
			frappe.get_doc("Sales Order", so.name).update_status("Closed")
		updates["omni_refund_required"] = 1

	elif target == CANCELLED:
		with as_system():
			_cancel_order(so)
		if cint(so.omni_payment_confirmed):
			updates["omni_refund_required"] = 1

	return updates


def available_qty(item_code, warehouse):
	"""Tồn khả dụng = tồn thực - đã giữ cho đơn bán khác."""
	row = frappe.db.get_value(
		"Bin", {"item_code": item_code, "warehouse": warehouse}, ["actual_qty", "reserved_qty"], as_dict=True
	)
	if not row:
		return 0.0
	return flt(row.actual_qty) - flt(row.reserved_qty)


def _check_stock(so):
	"""Trước khi báo sẵn sàng: tồn thực tại kho xuất phải đủ cho đơn."""
	for row in so.items:
		if not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		pending = flt(row.stock_qty) - flt(row.delivered_qty) * flt(row.conversion_factor or 1)
		actual = flt(
			frappe.db.get_value("Bin", {"item_code": row.item_code, "warehouse": row.warehouse}, "actual_qty")
		)
		if pending > actual:
			frappe.throw(
				f"Không đủ tồn {row.item_code} tại {row.warehouse}: cần {pending:g}, còn {actual:g}. "
				"Hãy chuyển hàng về kho này trước."
			)


def _make_delivery_note(so):
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	if not dn.get("items"):
		frappe.throw("Không còn mặt hàng nào cần giao cho đơn này.")
	dn.flags.ignore_permissions = True
	dn.insert()
	dn.submit()
	return dn


def _delivery_notes(so_name, is_return=0):
	return frappe.db.sql_list(
		"""select distinct dn.name from `tabDelivery Note` dn
		join `tabDelivery Note Item` dni on dni.parent = dn.name
		where dni.against_sales_order = %s and dn.docstatus = 1 and dn.is_return = %s
		order by dn.creation""",
		(so_name, is_return),
	)


def _return_delivery(so):
	"""Nhập lại kho toàn bộ hàng của phiếu giao gần nhất chưa bị trả."""
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

	returned_against = set(
		frappe.get_all(
			"Delivery Note",
			filters={"docstatus": 1, "is_return": 1, "return_against": ["in", _delivery_notes(so.name) or [""]]},
			pluck="return_against",
		)
	)
	open_dns = [d for d in _delivery_notes(so.name) if d not in returned_against]
	if not open_dns:
		frappe.throw("Không tìm thấy phiếu giao hàng để nhập trả.")
	ret = make_sales_return(open_dns[-1])
	ret.flags.ignore_permissions = True
	ret.insert()
	ret.submit()
	return ret


def mode_of_payment_for(so):
	s = settings()
	if so.omni_payment_method == PAY_TRANSFER:
		return s.transfer_mode_of_payment or s.cod_mode_of_payment
	return s.cod_mode_of_payment


def _payment_entry(dt, dn, company, mode_of_payment, reference):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

	pe = get_payment_entry(dt, dn)
	if mode_of_payment:
		pe.mode_of_payment = mode_of_payment
		account = (get_bank_cash_account(mode_of_payment, company) or {}).get("account")
		if account:
			pe.paid_to = account
	pe.reference_no = reference
	pe.reference_date = nowdate()
	pe.flags.ignore_permissions = True
	pe.insert()
	pe.submit()
	return pe


def _invoice_and_collect(so):
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	si = make_sales_invoice(so.name, ignore_permissions=True)
	si.allocate_advances_automatically = 1
	si.flags.ignore_permissions = True
	si.insert()
	si.submit()
	outstanding = flt(frappe.db.get_value("Sales Invoice", si.name, "outstanding_amount"))
	if outstanding > 0:
		_payment_entry("Sales Invoice", si.name, so.company, mode_of_payment_for(so), so.name)
	return si


def _credit_note(so):
	from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

	invoices = frappe.db.sql_list(
		"""select distinct si.name from `tabSales Invoice` si
		join `tabSales Invoice Item` sii on sii.parent = si.name
		where sii.sales_order = %s and si.docstatus = 1 and si.is_return = 0""",
		so.name,
	)
	for name in invoices:
		if frappe.db.exists("Sales Invoice", {"return_against": name, "docstatus": 1}):
			continue
		cn = make_sales_return(name)
		cn.update_stock = 0
		cn.flags.ignore_permissions = True
		cn.insert()
		cn.submit()


def _cancel_order(so):
	if _delivery_notes(so.name) or _delivery_notes(so.name, is_return=1):
		# đã từng xuất kho (giao thất bại) -> không hủy chứng từ được, đóng đơn
		doc = frappe.get_doc("Sales Order", so.name)
		doc.update_status("Closed")
	else:
		doc = frappe.get_doc("Sales Order", so.name)
		doc.flags.ignore_permissions = True
		doc.cancel()


def confirm_payment(sales_order, reference=None):
	"""Nhân viên xác nhận đã nhận chuyển khoản -> ghi nhận tiền ứng trước cho đơn."""
	so = frappe.get_doc("Sales Order", sales_order, for_update=True)
	if ACTOR_STAFF not in actor_kinds(so):
		frappe.throw("Bạn không có quyền xác nhận thanh toán.", frappe.PermissionError)
	if so.docstatus != 1 or so.omni_status in (CANCELLED, RETURNED, DONE):
		frappe.throw("Không thể xác nhận thanh toán cho đơn ở trạng thái này.")
	if cint(so.omni_payment_confirmed):
		frappe.throw("Đơn đã được xác nhận thanh toán.")
	actor = frappe.session.user
	with as_system():
		pe = _payment_entry(
			"Sales Order", so.name, so.company, settings().transfer_mode_of_payment, reference or so.name
		)
	frappe.db.set_value("Sales Order", so.name, "omni_payment_confirmed", 1)
	add_log(so.name, so.omni_status, so.omni_status, f"Xác nhận đã nhận chuyển khoản ({pe.name})", actor=actor)
	return pe.name


def _notify_customer(so, status, note=None):
	try:
		email = so.get("contact_email") or frappe.db.get_value("Customer", so.customer, "email_id")
		if not email:
			return
		host = frappe.utils.get_url()
		extra = ""
		if status == READY_PICKUP and so.get("omni_pickup_store"):
			store = frappe.db.get_value("Retail Store", so.omni_pickup_store, ["store_name", "address"], as_dict=True)
			days = cint(settings().pickup_expiry_days) or 5
			extra = (
				f"<p>Mời bạn đến nhận hàng tại <b>{store.store_name}</b> ({store.address or ''}) "
				f"trong vòng {days} ngày.</p>"
			)
		if note and status in (FAILED, CANCELLED):
			extra += f"<p>Ghi chú: {frappe.utils.escape_html(note)}</p>"
		frappe.sendmail(
			recipients=[email],
			subject=f"Đơn hàng {so.name}: {status}",
			message=(
				f"<p>Xin chào {frappe.utils.escape_html(so.customer_name or '')},</p>"
				f"<p>Đơn hàng <b>{so.name}</b> của bạn đã chuyển sang trạng thái: <b>{status}</b>.</p>"
				f"{extra}<p><a href='{host}/orders/{so.name}'>Xem chi tiết đơn hàng</a></p>"
			),
			reference_doctype="Sales Order",
			reference_name=so.name,
		)
	except Exception:
		frappe.log_error(title="omni_retail: gửi email trạng thái đơn thất bại")
