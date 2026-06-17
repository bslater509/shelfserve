# CLI | OpenCode

> Source: https://opencode.ai/docs/cli
> Cached: 2026-06-15T14:08:53.271Z

---

# CLI

OpenCode CLI options and commands.

       The OpenCode CLI by default starts the [TUI](/docs/tui) when run without any arguments.

Terminal window```
opencode
```

But it also accepts commands as documented on this page. This allows you to interact with OpenCode programmatically.

Terminal window```
opencode run "Explain how closures work in JavaScript"
```

### [tui](#tui)

Start the OpenCode terminal user interface.

Terminal window```
opencode [project]
```

#### [Flags](#flags)

FlagShortDescription`--continue``-c`Continue the last session`--session``-s`Session ID to continue`--fork`Fork the session when continuing (use with `--continue` or `--session`)`--prompt`Prompt to use`--model``-m`Model to use in the form of provider/model`--agent`Agent to use`--port`Port to listen on`--hostname`Hostname to listen on`--mdns`Enable mDNS discovery`--mdns-domain`Custom mDNS domain name`--cors`Additional browser origin(s) to allow CORS

## [Commands](#commands)

The OpenCode CLI also has the following commands.

### [agent](#agent)

Manage agents for OpenCode.

Terminal window```
opencode agent [command]
```

#### [create](#create)

Create a new agent with custom configuration.

Terminal window```
opencode agent create
```

This command will guide you through creating a new agent with a custom system prompt and permission configuration. Anything you don’t allow is denied in the generated agent’s frontmatter.

#### [Flags](#flags-1)

FlagShortDescription`--path`Directory to write the agent file to (defaults to global or `.opencode/agent` based on the prompt)`--description`What the agent should do`--mode`Agent mode: `all`, `primary`, or `subagent``--permissions`Comma-separated list of permissions to allow (default: all). Available: `bash`, `read`, `edit`, `glob`, `grep`, `webfetch`, `task`, `todowrite`, `websearch`, `lsp`, `skill`. Anything omitted is denied. Alias: `--tools``--model``-m`Model to use, in `provider/model` format
Passing all of `--path`, `--description`, `--mode`, and `--permissions` runs the command non-interactively.

#### [list](#list)

List all available agents.

Terminal window```
opencode agent list
```

### [attach](#attach)

Attach a terminal to an already running OpenCode backend server started via `serve` or `web` commands.

Terminal window```
opencode attach [url]
```

This allows using the TUI with a remote OpenCode backend. For example:

Terminal window```
# Start the backend server for web/mobile accessopencode web --port 4096 --hostname 0.0.0.0
# In another terminal, attach the TUI to the running backendopencode attach http://10.20.30.40:4096
```

#### [Flags](#flags-2)

FlagShortDescription`--dir`Working directory to start TUI in`--continue``-c`Continue the last session`--session``-s`Session ID to continue`--fork`Fork the session when continuing (use with `--continue` or `--session`)`--password``-p`Basic auth password (defaults to `OPENCODE_SERVER_PASSWORD`)`--username``-u`Basic auth username (defaults to `OPENCODE_SERVER_USERNAME` or `opencode`)

### [auth](#auth)

Command to manage credentials and login for providers.

Terminal window```
opencode auth [command]
```

#### [login](#login)

OpenCode is powered by the provider list at [Models.dev](https://models.dev), so you can use `opencode auth login` to configure API keys for any provider you’d like to use. This is stored in `~/.local/share/opencode/auth.json`.

Terminal window```
opencode auth login
```

When OpenCode starts up it loads the providers from the credentials file. And if there are any keys defined in your environments or a `.env` file in your project.

##### [Flags](#flags-3)

FlagShortDescription`--provider``-p`Provider ID or name to log in to`--method``-m`Login method label to use, skipping method selection

#### [list](#list-1)

Lists all the authenticated providers as stored in the credentials file.

Terminal window```
opencode auth list
```

Or the short version.

Terminal window```
opencode auth ls
```

#### [logout](#logout)

Logs you out of a provider by clearing it from the credentials file.

Terminal window```
opencode auth logout
```

### [github](#github)

Manage the GitHub agent for repository automation.

Terminal window```
opencode github [command]
```

#### [install](#install)

Install the GitHub agent in your repository.

Terminal window```
opencode github install
```

This sets up the necessary GitHub Actions workflow and guides you through the configuration process. [Learn more](/docs/github).

#### [run](#run)

Run the GitHub agent. This is typically used in GitHub Actions.

Terminal window```
opencode github run
```

##### [Flags](#flags-4)

FlagDescription`--event`GitHub mock event to run the agent for`--token`GitHub personal access token

### [mcp](#mcp)

Manage Model Context Protocol servers.

Terminal window```
opencode mcp [command]
```

#### [add](#add)

Add an MCP server to your configuration.

Terminal window```
opencode mcp add
```

This command will guide you through adding either a local or remote MCP server.

#### [list](#list-2)

List all configured MCP servers and their connection status.

Terminal window```
opencode mcp list
```

Or use the short version.

Terminal window```
opencode mcp ls
```

#### [auth](#auth-1)

Authenticate with an OAuth-enabled MCP server.

Terminal window```
opencode mcp auth [name]
```

If you don’t provide a server name, you’ll be prompted to select from available OAuth-capable servers.

You can also list OAuth-capable servers and their authentication status.

Terminal window```
opencode mcp auth list
```

Or use the short version.

Terminal window```
opencode mcp auth ls
```

#### [logout](#logout-1)

Remove OAuth credentials for an MCP server.

Terminal window```
opencode mcp logout [name]
```

#### [debug](#debug)

Debug OAuth connection issues for an MCP server.

Terminal window```
opencode mcp debug &#x3C;name>
```

">

### [models](#models)

List all available models from configured providers.

Terminal window```
opencode models [provider]
```

This command displays all models available across your configured providers in the format `provider/model`.

This is useful for figuring out the exact model name to use in [your config](/docs/config/).

You can optionally pass a provider ID to filter models by that provider.

Terminal window```
opencode models anthropic
```

#### [Flags](#flags-5)

FlagDescription`--refresh`Refresh the models cache from models.dev`--verbose`Use more verbose model output (includes metadata like costs)
Use the `--refresh` flag to update the cached model list. This is useful when new models have been added to a provider and you want to see them in OpenCode.

Terminal window```
opencode models --refresh
```

### [run](#run-1)

Run opencode in non-interactive mode by passing a prompt directly.

Terminal window```
opencode run [message..]
```

This is useful for scripting, automation, or when you want a quick answer without launching the full TUI. For example.

Terminal window```
opencode run Explain the use of context in Go
```

You can also attach to a running `opencode serve` instance to avoid MCP server cold boot times on every run:

Terminal window```
# Start a headless server in one terminalopencode serve
# In another terminal, run commands that attach to itopencode run --attach http://localhost:4096 "Explain async/await in JavaScript"
```

#### [Flags](#flags-6)

FlagShortDescription`--command`The command to run, use message for args`--continue``-c`Continue the last session`--session``-s`Session ID to continue`--fork`Fork the session when continuing (use with `--continue` or `--session`)`--share`Share the session`--model``-m`Model to use in the form of provider/model`--agent`Agent to use`--file``-f`File(s) to attach to message`--format`Format: default (formatted) or json (raw JSON events)`--title`Title for the session (uses truncated prompt if no value provided)`--attach`Attach to a running opencode server (e.g., [http://localhost:4096](http://localhost:4096))`--password``-p`Basic auth password (defaults to `OPENCODE_SERVER_PASSWORD`)`--username``-u`Basic auth username (defaults to `OPENCODE_SERVER_USERNAME` or `opencode`)`--dir`Directory to run in, or path on the remote server when attaching`--port`Port for the local server (defaults to random port)`--variant`Model variant (provider-specific reasoning effort)`--thinking`Show thinking blocks`--dangerously-skip-permissions`Auto-approve permissions that are not explicitly denied (dangerous!)

### [serve](#serve)

Start a headless OpenCode server for API access. Check out the [server docs](/docs/server) for the full HTTP interface.

Terminal window```
opencode serve
```

This starts an HTTP server that provides API access to opencode functionality without the TUI interface. Set `OPENCODE_SERVER_PASSWORD` to enable HTTP basic auth (username defaults to `opencode`).

#### [Flags](#flags-7)

FlagDescription`--port`Port to listen on`--hostname`Hostname to listen on`--mdns`Enable mDNS discovery`--mdns-domain`Custom mDNS domain name`--cors`Additional browser origin(s) to allow CORS

### [session](#session)

Manage OpenCode sessions.

Terminal window```
opencode session [command]
```

#### [list](#list-3)

List all OpenCode sessions.

Terminal window```
opencode session list
```

##### [Flags](#flags-8)

FlagShortDescription`--max-count``-n`Limit to N most recent sessions`--format`Output format: table or json (table)

#### [delete](#delete)

Delete an OpenCode session.

Terminal window```
opencode session delete &#x3C;sessionID>
```

">

### [stats](#stats)

Show token usage and cost statistics for your OpenCode sessions.

Terminal window```
opencode stats
```

#### [Flags](#flags-9)

FlagDescription`--days`Show stats for the last N days (all time)`--tools`Number of tools to show (all)`--models`Show model usage breakdown (hidden by default). Pass a number to show top N`--project`Filter by project (all projects, empty string: current project)

### [export](#export)

Export session data as JSON.

Terminal window```
opencode export [sessionID]
```

If you don’t provide a session ID, you’ll be prompted to select from available sessions.

#### [Flags](#flags-10)

FlagDescription`--sanitize`Redact sensitive transcript/file data

### [import](#import)

Import session data from a JSON file or OpenCode share URL.

Terminal window```
opencode import &#x3C;file>
```

">
You can import from a local file or an OpenCode share URL.

Terminal window```
opencode import session.jsonopencode import https://opncd.ai/s/abc123
```

### [web](#web)

Start a headless OpenCode server with a web interface.

Terminal window```
opencode web
```

This starts an HTTP server and opens a web browser to access OpenCode through a web interface. Set `OPENCODE_SERVER_PASSWORD` to enable HTTP basic auth (username defaults to `opencode`).

#### [Flags](#flags-11)

FlagDescription`--port`Port to listen on`--hostname`Hostname to listen on`--mdns`Enable mDNS discovery`--mdns-domain`Custom mDNS domain name`--cors`Additional browser origin(s) to allow CORS

### [acp](#acp)

Start an ACP (Agent Client Protocol) server.

Terminal window```
opencode acp
```

This command starts an ACP server that communicates via stdin/stdout using nd-JSON.

#### [Flags](#flags-12)

FlagDescription`--cwd`Working directory`--port`Port to listen on`--hostname`Hostname to listen on`--mdns`Enable mDNS discovery`--mdns-domain`Custom mDNS domain name`--cors`Additional browser origin(s) to allow CORS

### [plugin](#plugin)

Install a plugin and update your config.

Terminal window```
opencode plugin &#x3C;module>
```

">
Or use the alias.

Terminal window```
opencode plug &#x3C;module>
```

">
#### [Flags](#flags-13)

FlagShortDescription`--global``-g`Install in global config`--force``-f`Replace existing plugin version

### [pr](#pr)

Fetch and checkout a GitHub PR branch, then run OpenCode.

Terminal window```
opencode pr &#x3C;number>
```

">

### [db](#db)

Database tools.

Terminal window```
opencode db [query]
```

#### [Flags](#flags-14)

FlagDescription`--format`Output format: `json` or `tsv`

#### [path](#path)

Print the database path.

Terminal window```
opencode db path
```

### [debug](#debug-1)

Debugging and troubleshooting tools.

Terminal window```
opencode debug [command]
```

### [uninstall](#uninstall)

Uninstall OpenCode and remove all related files.

Terminal window```
opencode uninstall
```

#### [Flags](#flags-15)

FlagShortDescription`--keep-config``-c`Keep configuration files`--keep-data``-d`Keep session data and snapshots`--dry-run`Show what would be removed without removing`--force``-f`Skip confirmation prompts

### [upgrade](#upgrade)

Updates opencode to the latest version or a specific version.

Terminal window```
opencode upgrade [target]
```

To upgrade to the latest version.

Terminal window```
opencode upgrade
```

To upgrade to a specific version.

Terminal window```
opencode upgrade v0.1.48
```

#### [Flags](#flags-16)

FlagShortDescription`--method``-m`The installation method that was used; curl, npm, pnpm, bun, brew

## [Global Flags](#global-flags)

The opencode CLI takes the following global flags.

FlagShortDescription`--help``-h`Display help`--version``-v`Print version number`--print-logs`Print logs to stderr`--log-level`Log level (DEBUG, INFO, WARN, ERROR)`--pure`Run without external plugins

## [Environment variables](#environment-variables)

OpenCode can be configured using environment variables.

VariableTypeDescription`OPENCODE_AUTO_SHARE`booleanAutomatically share sessions`OPENCODE_GIT_BASH_PATH`stringPath to Git Bash executable on Windows`OPENCODE_CONFIG`stringPath to config file`OPENCODE_TUI_CONFIG`stringPath to TUI config file`OPENCODE_CONFIG_DIR`stringPath to config directory`OPENCODE_CONFIG_CONTENT`stringInline json config content`OPENCODE_DISABLE_AUTOUPDATE`booleanDisable automatic update checks`OPENCODE_DISABLE_PRUNE`booleanDisable pruning of old data`OPENCODE_DISABLE_TERMINAL_TITLE`booleanDisable automatic terminal title updates`OPENCODE_PERMISSION`stringInlined json permissions config`OPENCODE_DISABLE_DEFAULT_PLUGINS`booleanDisable default plugins`OPENCODE_DISABLE_LSP_DOWNLOAD`booleanDisable automatic LSP server downloads`OPENCODE_ENABLE_EXPERIMENTAL_MODELS`booleanEnable experimental models`OPENCODE_DISABLE_AUTOCOMPACT`booleanDisable automatic context compaction`OPENCODE_DISABLE_CLAUDE_CODE`booleanDisable reading from `.claude` (prompt + skills)`OPENCODE_DISABLE_CLAUDE_CODE_PROMPT`booleanDisable reading `~/.claude/CLAUDE.md``OPENCODE_DISABLE_CLAUDE_CODE_SKILLS`booleanDisable loading `.claude/skills``OPENCODE_DISABLE_MODELS_FETCH`booleanDisable fetching models from remote sources`OPENCODE_DISABLE_MOUSE`booleanDisable mouse capture in the TUI`OPENCODE_FAKE_VCS`stringFake VCS provider for testing purposes`OPENCODE_CLIENT`stringClient identifier (defaults to `cli`)`OPENCODE_ENABLE_EXA`booleanEnable Exa web search tools`OPENCODE_SERVER_PASSWORD`stringEnable basic auth for `serve`/`web``OPENCODE_SERVER_US

... [Content truncated]