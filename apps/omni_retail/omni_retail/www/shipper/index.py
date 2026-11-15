import frappe

from omni_retail.constants import ROLE_SHIPPER

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/shipper"
		raise frappe.Redirect
	roles = frappe.get_roles()
	if ROLE_SHIPPER not in roles and "System Manager" not in roles:
		frappe.throw("Trang này chỉ dành cho shipper.", frappe.PermissionError)
	context.no_cache = 1
	context.show_sidebar = False
	context.title = "Giao hàng"
	context.shipper_name = frappe.utils.get_fullname()
