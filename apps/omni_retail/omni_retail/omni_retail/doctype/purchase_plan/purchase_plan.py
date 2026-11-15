import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, now_datetime, nowdate

from omni_retail.constants import ROLE_WAREHOUSE_MANAGER


class PurchasePlan(Document):
	def validate(self):
		total = 0
		for row in self.items:
			row.amount = flt(row.approved_qty) * flt(row.rate)
			total += row.amount
		self.total_amount = total

	def _require_manager(self):
		roles = frappe.get_roles()
		if ROLE_WAREHOUSE_MANAGER not in roles and "System Manager" not in roles:
			frappe.throw("Chỉ Quản lý kho mới được duyệt kế hoạch mua hàng.", frappe.PermissionError)

	def _po_names(self):
		return [n for n in (self.purchase_orders or "").split("\n") if n.strip()]

	@frappe.whitelist()
	def approve_and_create_pos(self):
		"""Duyệt kế hoạch -> sinh Purchase Order nháp, mỗi nhà cung cấp một đơn."""
		self._require_manager()
		if self.status != "Chờ duyệt":
			frappe.throw("Chỉ duyệt được kế hoạch đang ở trạng thái «Chờ duyệt».")
		rows = [r for r in self.items if flt(r.approved_qty) > 0]
		if not rows:
			frappe.throw("Không có dòng nào có số lượng duyệt mua lớn hơn 0.")
		missing = [r.item_code for r in rows if not r.supplier]
		if missing:
			frappe.throw("Chưa chọn nhà cung cấp cho: " + ", ".join(missing[:10]))

		warehouse = frappe.db.get_single_value("Omni Retail Settings", "central_warehouse")
		by_supplier = {}
		for r in rows:
			by_supplier.setdefault(r.supplier, []).append(r)

		names = []
		for supplier, lines in by_supplier.items():
			lead = max(cint(r.lead_time_days) for r in lines) or 7
			schedule_date = add_days(nowdate(), lead)
			po = frappe.get_doc(
				{
					"doctype": "Purchase Order",
					"supplier": supplier,
					"company": self.company or frappe.defaults.get_global_default("company"),
					"transaction_date": nowdate(),
					"schedule_date": schedule_date,
					"set_warehouse": warehouse,
					"omni_purchase_plan": self.name,
					"items": [
						{
							"item_code": r.item_code,
							"qty": flt(r.approved_qty),
							"rate": flt(r.rate),
							"schedule_date": schedule_date,
							"warehouse": warehouse,
						}
						for r in lines
					],
				}
			)
			po.insert()
			names.append(po.name)

		self.purchase_orders = "\n".join(names)
		self.status = "Đã tạo PO"
		self.approved_by = frappe.session.user
		self.approved_on = now_datetime()
		self.save()
		return names

	@frappe.whitelist()
	def send_to_suppliers(self):
		"""Xác nhận các PO và gửi email (kèm PDF) cho từng nhà cung cấp."""
		self._require_manager()
		if self.status != "Đã tạo PO":
			frappe.throw("Cần duyệt và tạo PO trước khi gửi nhà cung cấp.")
		sent, no_email = [], []
		for name in self._po_names():
			if not frappe.db.exists("Purchase Order", name):
				continue
			po = frappe.get_doc("Purchase Order", name)
			if po.docstatus == 2:
				continue
			if po.docstatus == 0:
				po.submit()
			email = frappe.db.get_value("Supplier", po.supplier, "omni_order_email") or frappe.db.get_value(
				"Supplier", po.supplier, "email_id"
			)
			if not email:
				no_email.append(po.supplier)
				continue
			rows = "".join(
				f"<tr><td>{frappe.utils.escape_html(d.item_code)}</td><td>{frappe.utils.escape_html(d.item_name or '')}</td>"
				f"<td align='right'>{d.qty:g}</td><td align='right'>{d.get_formatted('rate')}</td>"
				f"<td align='right'>{d.get_formatted('amount')}</td></tr>"
				for d in po.items
			)
			try:
				attachments = [frappe.attach_print("Purchase Order", po.name, file_name=po.name)]
			except Exception:
				# không tạo được PDF (wkhtmltopdf) thì vẫn gửi đơn, chi tiết nằm trong nội dung email
				frappe.log_error(title=f"omni_retail: không tạo được PDF cho {po.name}")
				attachments = []
			frappe.sendmail(
				recipients=[email],
				subject=f"Đơn đặt hàng {po.name}",
				message=(
					f"<p>Kính gửi {frappe.utils.escape_html(po.supplier_name or po.supplier)},</p>"
					f"<p>Chúng tôi gửi đơn đặt hàng <b>{po.name}</b>, "
					f"tổng giá trị <b>{po.get_formatted('grand_total')}</b>, "
					f"ngày cần hàng <b>{frappe.utils.formatdate(po.schedule_date)}</b>.</p>"
					"<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-size:13px'>"
					"<tr><th>Mã hàng</th><th>Tên hàng</th><th>Số lượng</th><th>Đơn giá</th><th>Thành tiền</th></tr>"
					f"{rows}</table>"
					"<p>Vui lòng xác nhận khả năng cung ứng và thời gian giao hàng.</p><p>Trân trọng.</p>"
				),
				attachments=attachments,
				reference_doctype="Purchase Order",
				reference_name=po.name,
				now=True,
			)
			sent.append(po.name)
		self.status = "Đã gửi NCC"
		self.save()
		return {"sent": sent, "no_email": no_email}

	@frappe.whitelist()
	def reject(self):
		self._require_manager()
		if self.status != "Chờ duyệt":
			frappe.throw("Chỉ từ chối được kế hoạch đang «Chờ duyệt».")
		self.status = "Từ chối"
		self.save()
