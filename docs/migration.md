# TUI to web migration

Conversational Chat Storer continues in the same GitHub repository:
<https://github.com/mavenrank/conversational-chat-storer>.
The local development folder is `ccs-web-opus5`; that folder name is independent
of the remote repository name.

## History

The three original commits remain ancestors of the web import. The last TUI
commit is `775b87a03e1ff0a188348ca0149a29354fbda736`, tagged `legacy-tui`.
`fix/windows-perf` remains at that checkpoint and was already merged into the
original `main`. The web migration is developed on `migration/web` and changes
the default branch only when its pull request is merged.

Opus 5 originally had no Git history. Its existing source was captured in one
web import commit, followed by migration validation fixes. Its earlier editing
sessions are described by the existing web changelog rather than reconstructed
as historical commits. The [original TUI changelog](legacy-tui-changelog.md) is
also preserved.

GitHub is the only configured remote, named `github`. It is the default push
destination. The Codeberg-hosted copy was left in place but is no longer tracked
or synchronized by these local checkouts.

## Application layout and commands

| TUI behavior | Web behavior |
| --- | --- |
| Root Python package, `ccs tui` | `backend/ccsweb` API and `frontend` React application |
| `ccs list` and `ccs show` | Browser session list, tabs, transcript and subagent panes |
| `ccs export -f md` | Markdown download through `/api/sessions/{id}/markdown` |
| `ccs export -f json` | Full normalized JSON through `/api/sessions/{id}?full=true`; the schema differs from TUI exports |
| `ccs backup` copies native tool storage | Browser Backup writes normalized snapshots to `~/.ccsweb/archive` |
| `ccs restore` restores native tool directories | No equivalent native-store restore command in the web app |
| Four source readers | Five adapters, including Codex |

Follow the root README to run the backend and frontend. Python 3.11 or newer
is required. Source roots can be overridden with the documented `CCSWEB_*`
environment variables.

The original TUI code and commands can be inspected at
[the legacy checkpoint](https://github.com/mavenrank/conversational-chat-storer/tree/legacy-tui).
For legacy restore operations, use a separate checkout at that tag; keep the
active web checkout on its current branch.

## Chat data and compatibility

This migration changes application source and Git metadata. It does not move
or rewrite the native chat stores, previous TUI backups, or the web archive.
These remain outside Git. Existing native stores are read through the web
adapters; old TUI-exported JSON has no dedicated importer yet.

The web Markdown exporter summarizes file reads by path and byte count while
retaining write and command payloads. The archive stores full normalized
payloads independently of Markdown export.

The following remain separate application work:

- Image attachments and Markdown image rendering.
- Browsing complete transcripts from the archive after the original source has
  disappeared. Archive listing exists, but transcript loading still uses the
  native source adapter.
- Cross-device chat synchronization and authenticated access to a shared backend.
  A browser reads the backend machine's stores, not the browser device's files.
- A packaged production launcher; the current documented startup uses separate
  backend and frontend development servers.

## Validation

```sh
cd backend
uv sync --locked --extra dev
uv run pytest
uv run python scripts/verify_sources.py
```

```sh
cd frontend
bun install --frozen-lockfile
bun run typecheck
bun run build
```

Source verification uses whichever native stores exist on the current machine
and reports skipped sources. Synthetic adapter tests can run without chat data.

Before migration, a complete Git bundle and a source-only Opus snapshot were
saved under the ignored local `.migration/backups/` directory. That directory
is not published to GitHub.
