import frappe
from frappe.utils import getdate

from omni_retail.constants import ROLE_WAREHOUSE_MANAGER


def scheduled_run():
	"""Chạy hằng ngày bởi scheduler; quyết định có lập kế hoạch hay không theo cấu hình."""
	schedule = frappe.db.get_single_value("Omni Retail Settings", "schedule") or ""
	if schedule.startswith("Tắt"):
		return
	if schedule.startswith("Hằng tuần") and getdate().weekday() != 0:
		return
	frappe.enqueue(
		"omni_retail.forecasting.tasks.run_job", queue="long", timeout=3600, triggered_by="Lịch tự động"
	)


def run_job(triggered_by=None, notify_user=None):
	from omni_retail.forecasting import planner

	try:
		name = planner.run(triggered_by=triggered_by)
		message = f"Đã lập xong kế hoạch mua hàng <a href='/app/purchase-plan/{name}'>{name}</a>."
	except Exception as e:
		name = None
		message = f"Lập kế hoạch mua hàng thất bại: {str(e)[:300]}"
	if notify_user:
		frappe.publish_realtime("msgprint", {"message": message, "title": "AI dự báo nhu cầu"}, user=notify_user)
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": notify_user,
				"type": "Alert",
				"subject": frappe.utils.strip_html(message),
				"document_type": "Purchase Plan" if name else None,
				"document_name": name,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	return name


@frappe.whitelist()
def run_now():
	"""Nút 'Chạy AI dự báo ngay'."""
	roles = frappe.get_roles()
	if ROLE_WAREHOUSE_MANAGER not in roles and "System Manager" not in roles:
		frappe.throw("Chỉ Quản lý kho mới được chạy dự báo.", frappe.PermissionError)
	frappe.enqueue(
		"omni_retail.forecasting.tasks.run_job",
		queue="long",
		timeout=3600,
		triggered_by=frappe.utils.get_fullname(),
		notify_user=frappe.session.user,
	)
	return "queued"
