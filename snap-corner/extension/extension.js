const { Gio, GLib, Meta, Shell } = imports.gi;
const Main = imports.ui.main;

const LAUNCHER = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'snap-corner']);
const SHORTCUTS = { '<Control><Alt>s': '--area', '<Control><Alt>f': '--screen' };
const IFACE = `<node>
  <interface name="com.anurag.SnapCorner.Shell">
    <method name="ClosePopups"/>
  </interface>
</node>`;

class Extension {
    enable() {
        this._actions = new Map();
        for (const [accelerator, mode] of Object.entries(SHORTCUTS)) {
            const action = global.display.grab_accelerator(accelerator, Meta.KeyBindingFlags.NONE);
            if (action === Meta.KeyBindingAction.NONE) {
                log(`snap-corner: could not grab ${accelerator}`);
                continue;
            }
            Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.ALL);
            this._actions.set(action, mode);
        }
        this._signal = global.display.connect('accelerator-activated', (display, action) => {
            const mode = this._actions.get(action);
            if (mode)
                GLib.spawn_async(null, [LAUNCHER, mode], null, GLib.SpawnFlags.DEFAULT, null);
        });
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, '/com/anurag/SnapCorner');
    }

    disable() {
        global.display.disconnect(this._signal);
        for (const action of this._actions.keys()) {
            Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.NONE);
            global.display.ungrab_accelerator(action);
        }
        this._actions.clear();
        this._dbus.unexport();
        this._dbus = null;
    }

    ClosePopups() {
        const menu = Main.panel.menuManager.activeMenu;
        if (menu)
            menu.close();
    }
}

function init() {
    return new Extension();
}
