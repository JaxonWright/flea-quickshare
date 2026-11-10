<img src="assets/header.svg" width="216" height="80" alt="Quick Share + Flea">   
 <a href="https://github.com/tcballard/omarchy-badges"><img src="https://raw.githubusercontent.com/tcballard/omarchy-badges/85f859029e236e784e7b05ada6dbe73506d07a91/badges/v1/built-for-omarchy.svg" alt="Built for Omarchy"></a>
</p>

# flea-quickshare

A plugin for the [Flea](https://github.com/thisisgm/flea) Omarchy File Browser that lets you send files to nearby Android devices with native Android Quick Share. Just right-click the file and select a device under Quick Share.

The plugin uses the [quickshare](https://github.com/JaxonWright/quickshare) command, which is a separate binary that does most of the actual work. That project can be used as a standalone CLI or for your own frontend project similar to Flea.

## Requirements

- Flea 0.4.0 or newer
- Linux on x86_64 or aarch64 with glibc 2.35 or newer. On other architectures, build `quickshare` and put it on `PATH`
- Python 3, which Flea already depends on

## Install

```sh
flea plugin add https://github.com/JaxonWright/flea-quickshare
flea plugin enable quickshare.send
```

Restart Flea if a window was already open. The first time Flea asks for devices, the plugin downloads the [quickshare](https://github.com/JaxonWright/quickshare) release it pins, about 5 MB, into its own `bin/` folder, and checks it against a SHA-256 written in `plugin.py`. A download that fails or does not match shows as one unavailable row in the menu, and the plugin tries again the next time the menu opens.

To update, run `flea plugin update quickshare.send`. A plugin update also moves the pinned quickshare version, so the two always match.

Sending needs no firewall rule, because this computer opens every connection. Only `quickshare receive`, which is not possible within Flea, needs one.

On a Pixel 10 or newer, Wi-Fi may drop when the Quick Share sheet opens. See [the quickshare README](https://github.com/JaxonWright/quickshare#pixel-10-and-newer-drop-wi-fi-when-quick-share-opens) for the fix. To check the setup, run `~/.config/flea/plugins/quickshare.send/bin/quickshare-0.1.0 doctor`.

## Behaviour

When the file menu opens, the plugin runs `quickshare browse` for 2 seconds and lists each device it finds. Flea asks again at most once every 10 seconds. The phone appears only while it is visible, which usually means its Quick Share screen is open or its visibility is set to Everyone.

Flea stops a plugin request after 30 seconds, and a Quick Share send waits for the phone's owner to tap Accept before it copies anything. So when you choose a device, the plugin starts a separate process that runs `quickshare send`, and answers Flea at once. That process shows a desktop notification when the send ends. The notification says the files were sent, that the owner declined or cancelled, or why the send failed. It uses `omarchy-notification-send` when Omarchy is installed and `notify-send` otherwise.

The plugin refuses folders because Quick Share sends files.

## License

GPL-3.0-only, to match `quickshare`.

The Flea mark in `assets/header.svg` is copied from [Flea](https://github.com/thisisgm/flea), Copyright (c) 2026 GM, under the MIT license in `assets/FLEA-LICENSE`. Quick Share is a trademark of Google. The Quick Share mark in `assets/header.svg` and `mark.svg` is a tracing of Google's icon, and this project is not affiliated with Google.
