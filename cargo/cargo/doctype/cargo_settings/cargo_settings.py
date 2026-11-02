# Copyright (c) 2026, Aradhya-Tripathi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from cargo.image_builder.doctype.pilot_image import intrakore
from cargo.image_builder.doctype.pilot_image.pilot_image import start_base_images


class CargoSettings(Document):
	"""Where Cargo reaches Atlas, Proxy, and Central. Shared by every service."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from cargo.cargo.doctype.frappe_branch.frappe_branch import FrappeBranch
		from cargo.cargo.doctype.intrakore_app_release.intrakore_app_release import IntrakoreAppRelease
		from cargo.cargo.doctype.signup_app.signup_app import SignupApp

		app_source: DF.Literal["Marketplace", "Intrakore"]
		atlas_tenant_id: DF.Int
		atlas_token: DF.Password
		atlas_url: DF.Data
		build_machine_cpu: DF.Int
		build_machine_disk_gb: DF.Int
		build_machine_memory: DF.Int
		build_without_prebuilt_assets: DF.Check
		cargo_url: DF.Data
		central_url: DF.Data
		central_webhook_enabled: DF.Check
		central_webhook_secret: DF.Password
		central_webhook_url: DF.Data | None
		first_storage_disk_growth_percent: DF.Percent
		frappe_branches: DF.Table[FrappeBranch]
		intrakore_apps: DF.Table[IntrakoreAppRelease]
		intrakore_default_branch: DF.Data | None
		intrakore_github_token: DF.Password | None
		intrakore_last_sync: DF.Datetime | None
		intrakore_lock_url: DF.Data | None
		intrakore_manifest_url: DF.Data | None
		intrakore_repository_base: DF.Data | None
		jwks_url: DF.Data
		last_repository_refresh: DF.Datetime | None
		max_auto_retry_count: DF.Int
		max_storage_node_disk: DF.Int
		metadata_snapshot_interval_hours: DF.Float
		one_click_repository_branch: DF.Data | None
		one_click_repository_url: DF.Data | None
		proxy_token: DF.Password
		proxy_url: DF.Data
		region: DF.Data
		region_id: DF.Int
		signup_apps: DF.Table[SignupApp]
		storage_disk_min_hours_between_growth: DF.Float
		storage_disk_predict_hours: DF.Int
		storage_node_spread: DF.Literal["Separate hosts", "Off"]
		storage_node_spread_within: DF.Data | None
		track_pilot_releases: DF.Check
		update_pilot_in_base_image: DF.Check
		wildcard_domain: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		# Every consumer builds a domain from this, so it is canonicalised once, here.
		self.wildcard_domain = (self.wildcard_domain or "").strip().strip(".").lower()
		self.validate_intrakore_github_token()
		for branch in self.frappe_branches:
			if branch.commit and not intrakore.FULL_COMMIT.fullmatch(branch.commit.strip()):
				frappe.throw(frappe._("Pin {0} to a full commit.").format(branch.branch))

	def validate_intrakore_github_token(self) -> None:
		"""A saved token comes back masked, and only a new one is checked."""
		if self.intrakore_github_token and not self.is_dummy_password(self.intrakore_github_token):
			self.intrakore_github_token = self.intrakore_github_token.strip()
			intrakore.validate_github_token(self.intrakore_github_token)

	@frappe.whitelist()
	def build_base_images(self) -> list[str]:
		"""Start a Base image of the newest Pilot release on each Frappe branch head, if it has none."""
		return start_base_images(force=True)

	@frappe.whitelist()
	def sync_intrakore_apps(self, lock: str | None = None, manifest: str | None = None) -> list[str]:
		"""Fill the INTRAKORE App Releases from a pasted lock file, or from the Lock File URL."""
		frappe.only_for("System Manager")
		return intrakore.sync_app_releases(lock, manifest)
