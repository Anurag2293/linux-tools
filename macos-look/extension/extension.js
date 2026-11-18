const { Clutter } = imports.gi;
const Main = imports.ui.main;

let sessionId = 0;

function moveClockTo(box, index) {
    const container = Main.panel.statusArea.dateMenu.container;
    const parent = container.get_parent();
    if (parent === box)
        return;
    if (parent)
        parent.remove_child(container);
    box.insert_child_at_index(container, index);
}

function placeClockRight() {
    moveClockTo(Main.panel._rightBox, -1);
}

function init() {
}

function enable() {
    placeClockRight();
    Main.messageTray._bannerBin.x_align = Clutter.ActorAlign.END;
    sessionId = Main.sessionMode.connect('updated', placeClockRight);
}

function disable() {
    if (sessionId)
        Main.sessionMode.disconnect(sessionId);
    sessionId = 0;
    moveClockTo(Main.panel._centerBox, 0);
    Main.messageTray._bannerBin.x_align = Clutter.ActorAlign.CENTER;
}
