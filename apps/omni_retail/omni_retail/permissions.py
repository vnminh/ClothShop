"""Phân quyền bổ sung.

Trang đơn hàng của Webshop đọc điểm tích lũy của khách, việc này yêu cầu quyền đọc DocType Customer.
Ta cấp quyền đọc cho vai trò cổng "Customer" nhưng giới hạn chặt: khách chỉ đọc được hồ sơ của chính mình.
"""

import frappe


def _is_portal_user(user):
	return frappe.get_cached_value("User", user, "user_type") == "Website User"


def _own_customer(user):
	from omni_retail.orders.service import customer_of_user

	return customer_of_user(user)


def customer_query_conditions(user=None):
	user = user or frappe.session.user
	if not _is_portal_user(user):
		return ""
	own = _own_customer(user)
	if not own:
		return "1=0"
	return f"`tabCustomer`.name = {frappe.db.escape(own)}"


def customer_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _is_portal_user(user):
		return None
	if ptype not in (None, "read", "select"):
		return False
	return doc.name == _own_customer(user)
