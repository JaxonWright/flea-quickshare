# flea-quickshare

A [Flea](https://github.com/thisisgm/flea) plugin that sends files to nearby Android devices with Quick Share. Select files, open the file menu, and choose a device under **Quick Share**.

The plugin does no networking itself. It calls the [quickshare](https://github.com/JaxonWright/quickshare) command, the same way Flea's Taildrop row calls `tailscale`. The Quick Share row appears in Flea's window. Flea's terminal interface (`flea --tui`) does not draw plugin send rows yet, so it has no Quick Share row.

## Requirements

- Flea 0.4.0 or newer.
- `quickshare` on `PATH` or in `~/.local/bin`. See its README for building it and for the Pixel Wi-Fi workaround.
- Python 3, which Flea already depends on.

## Install

```sh
flea plugin add https://github.com/JaxonWright/flea-quickshare
flea plugin enable quickshare.send
```

Restart Flea if a window was already open. To update, run `flea plugin update quickshare.send`.

## How it behaves

When the file menu opens, the plugin runs `quickshare browse` for 2 seconds and lists each device it finds. Flea asks again at most once every 10 seconds. The phone appears only while it is visible, which usually means its Quick Share screen is open or its visibility is set to Everyone.

Flea stops a plugin request after 30 seconds, and a Quick Share send waits for the phone's owner to tap Accept before it copies anything. So when you choose a device, the plugin starts a separate process that runs `quickshare send`, and answers Flea at once. That process shows a desktop notification when the send ends. The notification says the files were sent, that the owner declined or cancelled, or why the send failed. It uses `omarchy-notification-send` when Omarchy is installed and `notify-send` otherwise.

The plugin refuses folders, because Quick Share sends files.

## License

GPL-3.0-only, to match quickshare. See `LICENSE`.
