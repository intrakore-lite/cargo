"""INTRAKORE's own app source: signup apps and their releases come from the devops lock file,
not from Pilot's marketplace registry."""

import ast
import hashlib
import re
from urllib.parse import urlsplit

import frappe
import requests
import yaml
from frappe import _

from cargo.image_builder.doctype.pilot_image.apps import AppRelease

SOURCE = "Intrakore"
DEFAULT_REPOSITORY_BASE = "https://github.com/intrakore-lite"
DEFAULT_BRANCH = "main"
GITHUB_HOSTS = frozenset({"github.com", "api.github.com", "raw.githubusercontent.com"})
RAW_FILE_URL = "https://raw.githubusercontent.com/{repository}/{commit}/{path}"
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
APP_NAME = re.compile(r"[a-z][a-z0-9_]*")
# GitHub tokens, classic and fine-grained, are letters, digits and underscores. Anything else
# would need quoting in the JSON the build machine writes.
GITHUB_TOKEN = re.compile(r"[A-Za-z0-9_]+")
VERSION = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']""", re.MULTILINE)
TIMEOUT = 30
RELEASE_DOCTYPE = "Intrakore App Release"
RELEASE_ROWS = {"parenttype": "Cargo Settings", "parentfield": "intrakore_apps"}


def is_intrakore_source() -> bool:
	return frappe.db.get_single_value("Cargo Settings", "app_source") == SOURCE


def get_github_token() -> str:
	token = frappe.get_cached_doc("Cargo Settings").get_password(
		"intrakore_github_token", raise_exception=False
	)
	return (token or "").strip()


def validate_github_token(token: str | None) -> None:
	if token and not GITHUB_TOKEN.fullmatch(token):
		frappe.throw(_("The GitHub token holds characters a GitHub token does not."))


def get_build_token() -> str:
	"""The token an Apps build fetches private repositories with, if the INTRAKORE source is on."""
	return get_github_token() if is_intrakore_source() else ""


def github_headers(url: str) -> dict[str, str]:
	"""Authorization for a GitHub host only, so the token never travels to another one."""
	token = get_github_token()
	if token and urlsplit(url).hostname in GITHUB_HOSTS:
		return {"Authorization": f"token {token}"}
	return {}


def fetch_text(url: str) -> str:
	response = requests.get(url, headers=github_headers(url), timeout=TIMEOUT)
	response.raise_for_status()
	return response.text


def github_repository(repo: str) -> str:
	"""`owner/name` of a GitHub clone URL."""
	parts = urlsplit(repo)
	path = parts.path.strip("/").removesuffix(".git")
	if parts.hostname != "github.com" or path.count("/") != 1:
		frappe.throw(_("{0} is not a GitHub repository.").format(repo))
	return path


def fetch_repo_file(repo: str, commit: str, path: str) -> str:
	return fetch_text(RAW_FILE_URL.format(repository=github_repository(repo), commit=commit, path=path))


def parse_lock(text: str) -> dict[str, str]:
	"""The commit of each app in a devops lock file: `app<TAB>commit` lines, `#` comments."""
	commits = {}
	for number, line in enumerate(text.splitlines(), start=1):
		line = line.strip()
		if not line or line.startswith("#"):
			continue

		fields = line.split()
		if len(fields) < 2 or not APP_NAME.fullmatch(fields[0]) or not FULL_COMMIT.fullmatch(fields[1]):
			frappe.throw(_("Line {0} of the lock file is not an app and a full commit.").format(number))
		commits[fields[0]] = fields[1]

	if not commits:
		frappe.throw(_("The lock file names no app."))
	return commits


def parse_manifest(text: str) -> dict[str, dict]:
	"""The install order and branch of each app in a devops environment manifest."""
	manifest = yaml.safe_load(text) or {}
	if not isinstance(manifest, dict):
		frappe.throw(_("The manifest is not a mapping."))

	default_branch = manifest.get("default_track")
	return {
		app["name"]: {
			"install_order": int(app.get("order") or 0),
			"branch": app.get("track") or default_branch,
		}
		for app in manifest.get("apps") or []
		if isinstance(app, dict) and app.get("name")
	}


def parse_required_apps(hooks: str) -> tuple[str, ...]:
	"""The `required_apps` of an app's hooks.py, read without running it. Frappe is in every bench."""
	for node in ast.parse(hooks).body:
		if isinstance(node, ast.Assign) and any(
			isinstance(target, ast.Name) and target.id == "required_apps" for target in node.targets
		):
			return tuple(app for app in ast.literal_eval(node.value) if app != "frappe")
	return ()


def parse_version(init: str) -> str | None:
	match = VERSION.search(init)
	return match.group(1) if match else None


def split_apps(text: str | None) -> tuple[str, ...]:
	return tuple(app for app in re.split(r"[\s,]+", text or "") if app)


def get_repository_base() -> str:
	return (
		frappe.get_cached_doc("Cargo Settings").intrakore_repository_base or DEFAULT_REPOSITORY_BASE
	).rstrip("/")


def get_default_branch() -> str:
	return frappe.get_cached_doc("Cargo Settings").intrakore_default_branch or DEFAULT_BRANCH


def get_repo(app: str, repo: str | None = None) -> str:
	return repo or f"{get_repository_base()}/{app}.git"


def read_release(app: str, repo: str, commit: str) -> dict:
	"""What an app declares at a commit: the apps it requires and its version."""
	requires = parse_required_apps(fetch_repo_file(repo, commit, f"{app}/hooks.py"))
	try:
		version = parse_version(fetch_repo_file(repo, commit, f"{app}/__init__.py"))
	except requests.HTTPError:
		version = None
	return {"requires": "\n".join(requires), "version": version or commit[:7]}


def sync_app_releases(lock: str | None = None, manifest: str | None = None) -> list[str]:
	"""Replace the INTRAKORE App Releases with the apps of the lock file, pasted or read from
	Cargo Settings. Returns the apps whose commit changed. An app keeps what it requires and its
	version while its commit stays, so a sync reads GitHub only for the apps that moved."""
	lock_url = frappe.db.get_single_value("Cargo Settings", "intrakore_lock_url")
	manifest_url = frappe.db.get_single_value("Cargo Settings", "intrakore_manifest_url")
	lock = lock or (lock_url and fetch_text(lock_url))
	if not lock:
		frappe.throw(_("Paste a lock file or set the Lock File URL in Cargo Settings."))
	if not manifest and manifest_url:
		manifest = fetch_text(manifest_url)

	commits = parse_lock(lock)
	entries = parse_manifest(manifest) if manifest else {}
	existing = {row.app: row for row in frappe.get_doc("Cargo Settings").intrakore_apps}
	releases, changed = [], []
	for app, commit in commits.items():
		row = existing.get(app)
		entry = entries.get(app, {})
		release = {
			"app": app,
			"commit": commit,
			"repo": row.repo if row else None,
			"branch": entry.get("branch") or (row and row.branch) or get_default_branch(),
			"install_order": entry.get("install_order", row.install_order if row else 0),
		}
		if row and row.commit == commit:
			release.update(requires=row.requires, version=row.version)
		else:
			release.update(read_release(app, get_repo(app, release["repo"]), commit))
			changed.append(app)
		releases.append(release)

	releases.sort(key=lambda release: (release["install_order"], release["app"]))
	write_app_releases(releases)
	return changed


def write_app_releases(releases: list[dict]) -> None:
	"""Replace the table rows alone: saving the whole Single would validate every other setting."""
	frappe.db.delete(RELEASE_DOCTYPE, RELEASE_ROWS)
	for index, release in enumerate(releases, start=1):
		frappe.get_doc(
			{"doctype": RELEASE_DOCTYPE, **RELEASE_ROWS, "parent": "Cargo Settings", "idx": index, **release}
		).db_insert()

	frappe.db.set_single_value("Cargo Settings", "intrakore_last_sync", frappe.utils.now_datetime())
	frappe.clear_document_cache("Cargo Settings", "Cargo Settings")


def sync_scheduled() -> None:
	"""Follow the lock file while the INTRAKORE source is on and its URL is set."""
	if is_intrakore_source() and frappe.db.get_single_value("Cargo Settings", "intrakore_lock_url"):
		sync_app_releases()


def get_app_releases() -> dict[str, tuple[int, AppRelease]]:
	"""Each INTRAKORE App Release by app, with its place in the install order."""
	settings = frappe.get_cached_doc("Cargo Settings")
	prebuilt_assets = not settings.build_without_prebuilt_assets
	return {
		row.app: (
			(row.install_order or 0, row.idx),
			AppRelease(
				name=row.app,
				version=row.version or row.commit[:7],
				repo=get_repo(row.app, row.repo),
				commit=row.commit,
				branch=row.branch or get_default_branch(),
				requires=split_apps(row.requires),
				prebuilt_assets=prebuilt_assets,
			),
		)
		for row in settings.intrakore_apps
	}


def get_also_installs(signup_app: str) -> tuple[str, ...]:
	"""The apps a signup app's image installs with it, such as the other half of a bundle."""
	return split_apps(
		frappe.db.get_value(
			"Signup App",
			{"parenttype": "Cargo Settings", "parentfield": "signup_apps", "app": signup_app},
			"also_installs",
		)
	)


def get_install_order(signup_app: str) -> list[AppRelease]:
	"""The signup app, the apps it installs with, and all they require, each after what it
	requires. Of the apps free to install, the lowest install order goes first, as on the benches."""
	releases = get_app_releases()
	needed: list[str] = []

	def visit(app: str, path: tuple[str, ...]) -> None:
		if app in path:
			frappe.throw(_("{0} require each other.").format(" -> ".join((*path, app))))
		if app in needed:
			return
		if app not in releases:
			if path:
				frappe.throw(_("{0} requires {1}, which has no INTRAKORE App Release.").format(path[-1], app))
			frappe.throw(_("{0} has no INTRAKORE App Release.").format(app))
		for requirement in releases[app][1].requires:
			visit(requirement, (*path, app))
		needed.append(app)

	for app in (signup_app, *get_also_installs(signup_app)):
		visit(app, ())

	install_order, remaining = [], set(needed)
	while remaining:
		ready = [app for app in remaining if not remaining.intersection(releases[app][1].requires)]
		app = min(ready, key=lambda app: releases[app][0])
		install_order.append(releases[app][1])
		remaining.remove(app)
	return install_order


def get_release_set_id(install_order: list[AppRelease]) -> str:
	"""Names an Apps image's whole install set, so a move of any app in it is a new build. It fits
	`app_commit`, which holds 40 characters."""
	return hashlib.sha256("\n".join(f"{app.name} {app.commit}" for app in install_order).encode()).hexdigest()[:40]
