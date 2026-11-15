import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class SeasonalEvent(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw("«Đến ngày» phải sau «Từ ngày».")
