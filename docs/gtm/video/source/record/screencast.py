"""Record the full screen with GNOME Shell's screencast D-Bus API until a stop file appears.

usage: python3 screencast.py OUT STOPFILE [X Y W H]
The recording is bound to this process's D-Bus connection, so the process stays alive while
recording and calls StopScreencast when STOPFILE exists.
"""
import os
import sys

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

out, stop = sys.argv[1], sys.argv[2]
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
proxy = Gio.DBusProxy.new_sync(
    bus, 0, None, "org.gnome.Shell.Screencast", "/org/gnome/Shell/Screencast",
    "org.gnome.Shell.Screencast", None,
)
opts = {"framerate": GLib.Variant("i", 30), "draw-cursor": GLib.Variant("b", os.environ.get("DRAW_CURSOR", "0") == "1")}
if len(sys.argv) > 3:  # area: X Y W H
    x, y, w, h = (int(v) for v in sys.argv[3:7])
    ok, path = proxy.call_sync(
        "ScreencastArea", GLib.Variant("(iiiisa{sv})", (x, y, w, h, out, opts)), 0, -1, None
    ).unpack()
else:
    ok, path = proxy.call_sync("Screencast", GLib.Variant("(sa{sv})", (out, opts)), 0, -1, None).unpack()
print("started", ok, path, flush=True)
loop = GLib.MainLoop()


def check() -> bool:
    if os.path.exists(stop):
        proxy.call_sync("StopScreencast", None, 0, -1, None)
        print("stopped", path, flush=True)
        loop.quit()
        return False
    return True


GLib.timeout_add(250, check)
loop.run()
