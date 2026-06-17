# App configuration | Home Assistant Developer Docs

> Source: https://developers.home-assistant.io/docs/add-ons/configuration
> Cached: 2026-06-13T20:04:30.322Z

---

- [](/)
- App configuration

On this page# App configuration

Each app (formerly known as an add-on) is stored in a folder. The file structure looks like this:

```
addon_name/
  translations/
    en.yaml
  apparmor.txt
  CHANGELOG.md
  config.yaml
  DOCS.md
  Dockerfile
  icon.png
  logo.png
  README.md
  run.sh

```

noteTranslation files and `config` support `.json`, `.yml` and `.yaml` as the file type.

To keep it simple all examples use `.yaml`

## App script[​](#app-script)

As with every Docker container, you will need a script to run when the container is started. A user might run many apps, so it is encouraged to try to stick to Bash scripts if you&#x27;re doing simple things.

All our images also have [bashio](https://github.com/hassio-addons/bashio) installed. It contains a set of commonly used operations and can be used to be included in apps to reduce code duplication across apps, therefore making it easier to develop and maintain apps.

When developing your script:

- `/data` is a volume for persistent storage.

- `/data/options.json` contains the user configuration. You can use Bashio to parse this data.

```
CONFIG_PATH=/data/options.json

TARGET="$(bashio::config &#x27;target&#x27;)"

```

So if your `options` contain

```
{ "target": "beer" }

```

then there will be a variable `TARGET` containing `beer` in the environment of your bash file afterwards.

## App Dockerfile[​](#app-dockerfile)

Most of the apps (formerly known as add-ons) are based on the latest Alpine Linux image. Add `tzdata` if you need to run in a different timezone. `tzdata` is already added to our base images.

```
FROM ghcr.io/home-assistant/base:latest

# Install requirements for app
RUN \
  apk add --no-cache \
    example_alpine_package

# Copy data for app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

```

noteWhen Supervisor built an app with no `build.yaml`, it previously passed `BUILD_FROM=ghcr.io/home-assistant/base:latest` automatically. Since Supervisor 2026.04.0 that fallback is no longer applied, make sure your Dockerfile doesn&#x27;t rely on externally provided base image through the default `BUILD_FROM` argument.

If you are not using Home Assistant GitHub builder actions (see [Publishing your app](/docs/apps/publishing)), make sure that the Dockerfile also has a set of labels that include:

```
LABEL \
  io.hass.version="VERSION" \
  io.hass.type="app" \
  io.hass.arch="aarch64|amd64"

```

### Build args[​](#build-args)

We support the following build arguments by default:

ARGDescription`BUILD_VERSION`App version (read from `config.yaml`).`BUILD_ARCH`Holds the current build arch inside.
noteSince Supervisor 2026.04.0, the `BUILD_FROM` argument is no longer provided by default. Use explicit `FROM ghcr.io/home-assistant/base:latest` in your Dockerfile to achieve the same build result as before. Using a pinned version of the base image is recommended for better build stability.

## App configuration[​](#app-configuration)

The configuration for an app (formerly known as an add-on) is stored in `config.yaml`.

```
name: "Hello world"
version: "1.1.0"
slug: folder
description: >-
  "Long description"
arch:
  - amd64
url: "website with more information about the app (e.g., a forum thread for support)"
ports:
  123/tcp: 123
map:
  - type: share
    read_only: False
  - type: ssl
  - type: homeassistant_config
    read_only: False
    path: /custom/config/path
image: ghcr.io/my-org/my-app

```

noteAvoid using `config.yaml` as filename in your app for anything other than the app configuration. The Supervisor does recursively search for `config.yaml` in the app repository.

### Required configuration options[​](#required-configuration-options)

KeyTypeDescription`name`stringThe name of the app.`version`stringVersion of the app. If you are using a docker image with the `image` option, this needs to match the tag of the image that will be used.`slug`stringSlug of the app. This needs to be unique in the scope of the [repository](/docs/apps/repository) that the app is published in and URI friendly.`description`stringDescription of the app.`arch`listA list of supported architectures: `aarch64`, `amd64`.
### Optional configuration options[​](#optional-configuration-options)

KeyTypeDefaultDescription`machine`listDefault is support of all machine types. You can configure the app to only run on specific machines. You can use `!` before a machine type to negate it.`url`urlHomepage of the app. Here you can explain the app and options.`startup`string`application``initialize` will start the app on setup of Home Assistant. `system` is for things like databases and not dependent on other things. `services` will start before Home Assistant, while `application` is started afterwards. Finally `once` is for applications that don&#x27;t run as a daemon.`webui`stringA URL for the web interface of this app. Like `http://[HOST]:[PORT:2839]/dashboard`, the port needs the internal port, which will be replaced with the effective port. It is also possible to bind the protocol part to a configuration option with: `[PROTO:option_name]://[HOST]:[PORT:2839]/dashboard` and it&#x27;s looked up if it is `true` and it&#x27;s going to `https`.`boot`string`auto``auto` start at boot is controlled by the system and `manual` configures the app to only be started manually. If addon should never be started at boot automatically, use `manual_only` to prevent users from changing it.`ports`dictNetwork ports to expose from the container. Format is `"container-port/type": host-port`. If the host port is `null` then the mapping is disabled.`ports_description`dictNetwork ports description mapping. Format is `"container-port/type": "description of this port"`. Alternatively use [Port description translations](#port-description-translations).`host_network`bool`false`If `true`, the app runs on the host network.`host_ipc`bool`false`Allow the IPC namespace to be shared with others.`host_dbus`bool`false`Map the host D-Bus service into the app.`host_pid`bool`false`Allow the container to run on the host PID namespace. Works only for not protected apps. **Warning:** Does not work with S6 Overlay. If need this to be `true` and you use the normal app base image you disable S6 by overriding `/init`. Or use an alternate base image.`host_uts`bool`false`Use the hosts UTS namespace.`devices`listDevice list to map into the app. Format is: `<path_on_host>`. E.g., `/dev/ttyAMA0``homeassistant`stringPin a minimum required Home Assistant Core version for the app. Value is a version string like `2022.10.5`.`hassio_role`str`default`Role-based access to Supervisor API. Available: `default`, `homeassistant`, `backup`, `manager` or `admin``hassio_api`bool`false`This app can access the Supervisor&#x27;s REST API. Use `http://supervisor`.`homeassistant_api`bool`false`This app can access the Home Assistant REST API proxy. Use `http://supervisor/core/api`.`docker_api`bool`false`Allow read-only access to the Docker API for the app. Works only for not protected apps.`privileged`listPrivilege for access to hardware/system. Available access: `BPF`, `CHECKPOINT_RESTORE`, `DAC_READ_SEARCH`, `IPC_LOCK`, `NET_ADMIN`, `NET_RAW`, `PERFMON`, `SYS_ADMIN`, `SYS_MODULE`, `SYS_NICE`, `SYS_PTRACE`, `SYS_RAWIO`, `SYS_RESOURCE` or `SYS_TIME`.`full_access`bool`false`Give full access to hardware like the privileged mode in Docker. Works only for not protected apps. Consider using other app options instead of this, like `devices`. If you enable this option, don&#x27;t add `devices`, `uart`, `usb` or `gpio` as this is not needed.`apparmor`bool/string`true`Enable or disable AppArmor support. If it is enabled, you can also use custom profiles with the name of the profile.`map`listList of Home Assistant directory types to bind mount into your container. Possible values: `homeassistant_config`, `addon_config`, `ssl`, `addons`, `backup`, `share`, `media`, `all_addon_configs`, and `data`. Defaults to read-only, which you can change by adding the property `read_only: false`. By default, all paths map to `/<type-name>` inside the addon container, but an optional `path` property can also be supplied to configure the path (Example: `path: /custom/config/path`). If used, the path must not be empty, unique from any other path defined for the addon, and not the root path. Note that the `data` directory is always mapped and writable, but the `path` property can be set using the same conventions.`environment`dictA dictionary of environment variables to run the app with.`audio`bool`false`Mark this app to use the internal audio system. We map a working PulseAudio setup into the container. If your application does not support PulseAudio, you may need to install: Alpine Linux `alsa-plugins-pulse` or Debian/Ubuntu `libasound2-plugins`.`video`bool`false`Mark this app to use the internal video system. All available devices will be mapped into the app.`gpio`bool`false`If this is set to `true`, `/sys/class/gpio` will map into the app for access to the GPIO interface from the kernel. Some libraries also need  `/dev/mem` and `SYS_RAWIO` for read/write access to this device. On systems with AppArmor enabled, you need to disable AppArmor or provide your own profile for the app, which is better for security.`usb`bool`false`If this is set to `true`, it would map the raw USB access `/dev/bus/usb` into the app with plug&play support.`uart`bool`false`Default `false`. Auto mapping all UART/serial devices from the host into the app.`udev`bool`false`Default `false`. Setting this to `true` gets the host udev database read-only mounted into the app.`devicetree`bool`false`If this is set to `true`, `/device-tree` will map into the app.`kernel_modules`bool`false`Map host kernel modules and config into the app (readonly) and give you `SYS_MODULE` permission.`stdin`bool`false`If enabled, you can use the STDIN with Home Assistant API.`legacy`bool`false`If the Docker image has no `hass.io` labels, you can enable the legacy mode to use the config data.`options`dictDefault options value of the app.`schema`dictSchema for options value of the app. It can be `false` to disable schema validation and options.`image`stringFor use with container registries. Set this to the generic (multi-arch) image name, e.g. `ghcr.io/my-org/my-app`. The `{arch}` placeholder is still supported as a compatibility fallback for per-architecture image names (e.g. `ghcr.io/my-org/{arch}-my-app`). If you use this option, set the active Docker tag using the `version` option.`timeout`integer10Default 10 (seconds). The timeout to wait until the Docker daemon is done or will be killed.`tmpfs`bool`false`If this is set to `true`, the containers `/tmp` uses tmpfs, a memory file system.`discovery`listA list of services that this app provides for Home Assistant.`services`listA list of services that will be provided or consumed with this app. Format is `service`:`function` and functions are: `provide` (this app can provide this service), `want` (this app can use this service) or `need` (this app needs this service to work correctly).`auth_api`bool`false`Allow access to Home Assistant user backend.`ingress`bool`false`Enable the ingress feature for the app.`ingress_port`integer`8099`For apps that run on the host network, you can use `0` and read the port later via the API.`ingress_entry`string`/`Modify the URL entry point.`ingress_stream`bool`false`When enabled, requests to the app are streamed`panel_icon`string`mdi:puzzle`[MDI icon](https://materialdesignicons.com/) for the menu panel integration.`panel_title`stringDefaults to the app name, but can be modified with this option.`panel_admin`bool`true`Make the menu entry only available to users in the admin group.`backup`string`hot``hot` or `cold`. If `cold`, the supervisor turns the app off before taking a backup (the `pre/post` options are ignored when `cold` is used).`backup_pre`stringCommand to execute in the context of the app before the backup is taken.`backup_post`stringCommand to execute in the context of the app after the backup was taken.`backup_exclude`listList of files/paths (with glob support) that are excluded from backups.`stage`string`stable`Flag the app with one of the following attributes to give users an idea of its place in the development lifecycle: `stable`, `experimental` or `deprecated`.`init`bool`true`Set this to `false` to disable the Docker default system init. Use this if the image has its own init system (Like [s6-overlay](https://github.com/just-containers/s6-overlay)). *Note: Starting in V3 of S6 setting this to `false` is required or the addon won&#x27;t start, see [here](https://developers.home-assistant.io/blog/2022/05/12/s6-overlay-base-images) for more information.*`watchdog`stringA URL for monitoring the app health. Like `http://[HOST]:[PORT:2839]/dashboard`, the port needs the internal port, which will be replaced with the effective port. It is also possible to bind the protocol part to a configuration option with: `[PROTO:option_name]://[HOST]:[PORT:2839]/dashboard` and it&#x27;s looked up if it is `true` and it&#x27;s going to `https`. For simple TCP port monitoring you can use `tcp://[HOST]:[PORT:80]`. It works for apps on the host or internal network.`realtime`bool`false`Give app access to host schedule including `SYS_NICE` for change execution time/priority.`journald`bool`false`If set to `true`, the host&#x27;s system journal will be mapped read-only into the app. Most of the time the journal will be in `/var/log/journal` however on some hosts you will find it in `/run/log/journal`. Apps relying on this capability should check if the directory `/var/log/journal` is populated and fallback on `/run/log/journal` if not.`breaking_versions`listList of breaking versions of the addon. A manual update will always be required if the update is to a breaking version or would cross a breaking version, even if users have auto-update enabled for the addon.`ulimits`dictDictionary of resource limit (ulimit) settings for the app container. Each limit can be either a plain integer value or a dictionary with the keys `soft` and `hard`, each taking a plain integer for fine-grained control. Individual values must not be larger than the host&#x27;s hard limit (inspectable by `ulimit -Ha`; e.g. 524288 in case of the `nofile` limit in the Home Assistant Operating System).
### Options / Schema[​](#options--schema)

The `options` dictionary contains all available options and their default value. Set the default value to `null` or define the data type in the `schema` dictionary to make an option mandatory. This way, the option needs to be given by the user before the app (formerly known as an add-on) can start. Nested arrays and dictionaries are supported with a maximum depth of two.

To make an option truly optional (without default value), the `schema` dictionary needs to be used. Put a `?` at the end of the data type and *do not* define any default value in the `options` dictionary. If any default value is given, the opti

... [Content truncated]