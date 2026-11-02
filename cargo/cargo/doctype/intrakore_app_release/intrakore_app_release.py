# Copyright (c) 2026, Aradhya-Tripathi and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class IntrakoreAppRelease(Document):
	"""One INTRAKORE app at the commit the Apps images install."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		app: DF.Data
		branch: DF.Data | None
		commit: DF.Data
		install_order: DF.Int
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		repo: DF.Data | None
		requires: DF.SmallText | None
		version: DF.Data | None
	# end: auto-generated types

	pass
