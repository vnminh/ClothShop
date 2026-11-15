import frappe
from frappe.model.document import Document


class RetailStore(Document):
	def before_validate(self):
		"""Tạo điểm bán mới chỉ cần nhập tên: tự sinh kho con và POS Profile."""
		from omni_retail.setup import masters

		if not self.warehouse and self.store_name:
			self.warehouse = masters.ensure_warehouse(self.store_name, parent=masters.store_group_warehouse())
		if not self.pos_profile and self.warehouse:
			try:
				self.pos_profile = masters.ensure_pos_profile(self.store_name, self.warehouse)
			except Exception:
				frappe.log_error(title="omni_retail: không tạo được POS Profile")

	def validate(self):
		other = frappe.db.get_value(
			"Retail Store", {"warehouse": self.warehouse, "name": ["!=", self.name]}, "name"
		)
		if other:
			frappe.throw(f"Kho {self.warehouse} đã gắn với điểm bán {other}.")

	def on_update(self):
		# nhân sự của điểm bán được dùng POS Profile tương ứng
		if self.pos_profile and self.manager:
			prof = frappe.get_doc("POS Profile", self.pos_profile)
			if self.manager not in [u.user for u in prof.applicable_for_users]:
				prof.append("applicable_for_users", {"user": self.manager})
				prof.save(ignore_permissions=True)
