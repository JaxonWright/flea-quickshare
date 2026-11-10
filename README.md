<p align="center">
  <img src="assets/header.svg" width="216" height="80" alt="Quick Share + Flea">
</p>

# flea-quickshare

A [Flea](https://github.com/thisisgm/flea) plugin that sends files to nearby Android devices with Quick Share. Select files, open the file menu, and choose a device under **Quick Share**.

The plugin does no networking itself. It calls the [quickshare](https://github.com/JaxonWright/quickshare) command, the same way Flea's Taildrop row calls `tailscale`. The Quick Share row appears in Flea's window. Flea's terminal interface (`flea --tui`) does not draw plugin send rows yet, so it has no Quick Share row.

## Requirements

- Flea 0.4.0 or newer.
- Linux on x86_64 or aarch64 with glibc 2.35 or newer. On other architectures, build `quickshare` and put it on `PATH`.
- Python 3, which Flea already depends on.

## Install

```sh
flea plugin add https://github.com/JaxonWright/flea-quickshare
flea plugin enable quickshare.send
```

Restart Flea if a window was already open. That is the whole install. The first time Flea asks for devices, the plugin downloads the [quickshare](https://github.com/JaxonWright/quickshare) release it pins, about 5 MB, into its own `bin/` folder, and checks it against a SHA-256 written in `plugin.py`. A download that fails or does not match shows as one unavailable row in the menu, and the plugin tries again the next time the menu opens.

To update, run `flea plugin update quickshare.send`. A plugin update also moves the pinned quickshare version, so the two always match.

Sending needs no firewall rule, because this computer opens every connection. Only `quickshare receive`, which runs outside Flea, needs one.

On a Pixel 10 or newer, Wi-Fi may drop when the Quick Share sheet opens. See [the quickshare README](https://github.com/JaxonWright/quickshare#pixel-10-and-newer-drop-wi-fi-when-quick-share-opens) for the fix. To check the setup, run `~/.config/flea/plugins/quickshare.send/bin/quickshare-0.1.0 doctor`.

## How it behaves

When the file menu opens, the plugin runs `quickshare browse` for 2 seconds and lists each device it finds. Flea asks again at most once every 10 seconds. The phone appears only while it is visible, which usually means its Quick Share screen is open or its visibility is set to Everyone.

Flea stops a plugin request after 30 seconds, and a Quick Share send waits for the phone's owner to tap Accept before it copies anything. So when you choose a device, the plugin starts a separate process that runs `quickshare send`, and answers Flea at once. That process shows a desktop notification when the send ends. The notification says the files were sent, that the owner declined or cancelled, or why the send failed. It uses `omarchy-notification-send` when Omarchy is installed and `notify-send` otherwise.

The plugin refuses folders, because Quick Share sends files.

## License

GPL-3.0-only, to match quickshare. See `LICENSE`.

The Flea mark in `assets/header.svg` is copied from [Flea](https://github.com/thisisgm/flea), Copyright (c) 2026 GM, under the MIT license in `assets/FLEA-LICENSE`. Quick Share is a trademark of Google. The Quick Share mark in `assets/header.svg` and `mark.svg` is a tracing of Google's icon, and this project is not affiliated with Google.
