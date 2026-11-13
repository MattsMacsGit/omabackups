import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "parts"
import "pages"
import "Model.js" as Model

// OmaBackups on the bar (BUILD 5.5, 7.1).
// One page at a time, chosen by where the flow is (D10); every page works with
// the keyboard (↑↓ move, Enter/Space press, ← or Backspace back, Esc close).
Panel {
  id: root
  moduleName: "omabackups"
  ipcTarget: "omabackups"
  // The bar gives the widget only the room it asks for.
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  property string page: ""               // "" = the page for where the flow is
  property int cursorIndex: 0
  property bool migrateMode: false         // the Where and server screens, for Migrate
  property bool cursorActive: false
  property bool ctrlHeld: false            // Ctrl down (Back up anyway lights up while it is)

  readonly property string defaultPage: !svc.loaded ? "loading"
                                       : !svc.installed ? "missing"
                                       : svc.flow === "not-set-up" ? "first"
                                       : svc.flow === "migrating" ? "migrating"
                                       : svc.flow === "restore-files" ? "finish"
                                       : svc.flow === "setting-up" ? "firstBackup"
                                       : "everyday"
  readonly property string shown: page !== "" ? page : defaultPage
  readonly property bool hasRedLine: svc.lines.some(function(l) { return l.colour === "red" })
  // The pages live in the panel's content, built later: reach them through it.
  readonly property var pages: panel.loadedContent ? panel.loadedContent.pages : ({})
  readonly property Item pageItem: ["missing", "first", "where", "server", "disk", "firstBackup"].indexOf(shown) >= 0
                                   ? pages.start || null : shown === "settings" ? pages.settings || null
                                   : ["kept", "yourBackup"].indexOf(shown) >= 0 ? pages.details || null
                                   : shown === "everyday" ? pages.everyday || null
                                   : ["migrating", "finish"].indexOf(shown) >= 0 ? pages.migrate || null : null
  // The header's own button (gear or back) comes first, where it sits on screen.
  readonly property bool heroButtonShown: shown === "everyday" || page !== ""
  readonly property var targets: (heroButtonShown ? [heroTarget] : []).concat(
      pageItem && pageItem.targets ? pageItem.targets.filter(function(t) { return t && t.visible }) : [])
  // The cursor starts on the page's first item, not on the header's button.
  readonly property int firstIndex: heroButtonShown && targets.length > 1 ? 1 : 0
  readonly property var cursorTarget: cursorActive && targets.length ? targets[Math.min(cursorIndex, targets.length - 1)] : null
  // The cursor stays on the same item when the list changes (a line appears,
  // the Browsing bar opens above it). By position alone it slid onto a
  // restore point, and the next Enter opened one nobody asked for.
  property var heldTarget: null
  onCursorIndexChanged: heldTarget = targets.length ? targets[Math.min(cursorIndex, targets.length - 1)] : null
  onTargetsChanged: {
    var at = heldTarget ? targets.indexOf(heldTarget) : -1
    if (at >= 0 && at !== cursorIndex) cursorIndex = at
  }

  // Back puts the cursor on the row you left from.
  property var placeOn: ({})
  function go(name, returning) {
    placeOn[shown] = cursorIndex
    page = name
    var place = placeOn[name !== "" ? name : defaultPage]
    cursorIndex = returning && place !== undefined ? place : firstIndex
  }
  // The mouse moves the same cursor the keys do: one highlight, always (D32).
  function pointAt(from, x, y) {
    for (var i = 0; i < targets.length; i++) {
      var t = targets[i]
      if (!t || !t.mapFromItem || !t.visible) continue
      var p = t.mapFromItem(from, x, y)
      if (p.x >= 0 && p.y >= 0 && p.x < t.width && p.y < t.height) {
        cursorActive = true
        cursorIndex = i
        return
      }
    }
  }
  function heroPressed() { shown === "everyday" ? go("settings") : back() }

  QtObject {
    id: heroTarget
    readonly property bool visible: true
    function activate() { root.heroPressed() }
  }
  function back() {
    if (["kept", "yourBackup"].indexOf(shown) >= 0) go("settings", true)
    else if (shown === "settings") go("", true)
    else if (shown === "server" || shown === "disk") go("where", true)
    else if (shown === "where") go("", true)
  }
  function titleFor(name) {
    if (migrateMode && ["where", "server", "disk"].indexOf(name) >= 0) return "Migrate"
    return ({ settings: "Settings", kept: "Restore points",
              yourBackup: "Your backup", where: "Set up backups", server: "Set up backups",
              disk: "Set up backups", firstBackup: "Set up backups", migrating: "Migrate",
              // After a Rescue USB, the same computer is back: it's a restore, not a Migrate.
              finish: svc.status.migrate && svc.status.migrate.rescued ? "Finish restore" : "Finish Migrate"
            })[name] || "OmaBackups"
  }

  // A finished setup in the terminal moves the panel on by itself.
  Connections {
    target: svc
    function onFlowChanged() { if (["where", "server", "disk"].indexOf(root.page) >= 0) root.go("") }
  }
  // Keep the keyboard cursor in view on a page taller than the panel.
  onCursorTargetChanged: {
    var f = panel.loadedContent ? panel.loadedContent.flick : null
    var t = cursorTarget && cursorTarget.mapToItem ? cursorTarget : (cursorTarget === heroTarget ? null : undefined)
    if (!f || t === undefined) return
    if (t === null) { f.contentY = 0; return }
    var y = t.mapToItem(f.contentItem, 0, 0).y
    if (y < f.contentY) f.contentY = Math.max(0, y - Style.space(8))
    else if (y + t.height > f.contentY + f.height)
      f.contentY = Math.min(f.contentHeight - f.height, y + t.height - f.height + Style.space(8))
  }
  onOpenedChanged: {
    svc.panelOpen = opened
    if (opened) svc.refresh()
    // Opened by a click, the pointer is on the bar icon, not the card: the
    // keyboard stays with your window until the pointer comes onto the card.
    if (opened) { panel.pointerAway = root.pressedOpen; root.pressedOpen = false }
    if (opened) idleReset.stop(); else idleReset.restart()
  }

  // Closed for 30 seconds, it opens on its first page again (it opened on
  // whatever page was left, Settings say). Pages in the middle of setting up
  // keep their place, so nothing typed there is lost.
  Timer {
    id: idleReset
    interval: 30000
    onTriggered: {
      if (root.opened || ["settings", "kept", "yourBackup"].indexOf(root.shown) < 0) return
      root.placeOn = ({})
      root.page = ""
      root.cursorActive = false
      root.cursorIndex = root.firstIndex
      if (panel.loadedContent) panel.loadedContent.flick.contentY = 0
    }
  }

  // The keyboard follows the pointer: away from the card it goes back to the
  // window you were in, so typing lands there while the panel stays up; back
  // on the card, the panel takes it again (Omarchy's brief prime, then OnDemand).
  property bool pressedOpen: false
  function pointerOnCard(on) {
    if (!panel.open) return
    if (!on) { panel.pointerAway = true; return }
    if (!panel.pointerAway) return
    panel.pointerAway = false
    panel.focusPrimed = false
    panel.beginFocusPrime()
    Qt.callLater(function() { if (panel.open && panel.focusTarget) panel.focusTarget.forceActiveFocus() })
  }

  Service { id: svc }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰁯"
    foreground: root.hasRedLine ? svc.colour("red")
                : (svc.flow === "everyday" ? root.barForeground : Qt.darker(root.barForeground, 1.55))
    onPressed: function(code) {
      if (code === Qt.MiddleButton) { svc.backupNow(); return }
      root.pressedOpen = !root.opened
      root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    // Omarchy's KeyboardPanel keeps the keyboard while open; this panel lets it
    // go while the pointer is away from the card (see pointerOnCard).
    property bool pointerAway: false
    WlrLayershell.keyboardFocus: !open || pointerAway ? WlrKeyboardFocus.None
                                 : (focusPrimed ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.Exclusive)
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(620))

    content: PanelKeyCatcher {
      id: keys
      readonly property Item flick: flick
      readonly property var pages: ({ start: startPage, everyday: everydayPage,
                                      settings: settingsPage, details: detailsPage, migrate: migratePage })
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      HoverHandler { onHoveredChanged: { if (!hovered) root.ctrlHeld = false; root.pointerOnCard(hovered) } }
      // Ctrl on its own reaches no signal of the key catcher: watch it here too.
      Keys.onPressed: function(event) { if (event.key === Qt.Key_Control) root.ctrlHeld = true }
      Keys.onReleased: function(event) { if (event.key === Qt.Key_Control) root.ctrlHeld = false }
      onMoveRequested: function(dx, dy) {
        if (dx < 0) { root.back(); return }
        if (dx > 0) { if (root.cursorTarget && root.cursorTarget.openOptions) root.cursorTarget.openOptions(); return }
        if (!root.cursorActive) { root.cursorActive = true; root.cursorIndex = root.firstIndex; return }
        root.cursorIndex = Math.max(0, Math.min(root.targets.length - 1, root.cursorIndex + dy))
      }
      onActivateRequested: if (root.cursorTarget && root.cursorTarget.activate) root.cursorTarget.activate()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "\b") root.back() }

      Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: parent.width
          spacing: Style.space(12)

          HoverHandler {
            onPointChanged: if (hovered) root.pointAt(column, point.position.x, point.position.y)
          }

          PanelHero {
            width: parent.width
            title: root.titleFor(root.shown)
            meta: root.shown === "everyday" && svc.header && svc.header.last_finished
                  ? "Latest backup was " + Model.when(svc.header.last_finished) : ""
            detail: root.shown === "everyday" ? Model.free(svc.header) : ""
            iconComponent: Component {
              Text {
                textFormat: Text.PlainText
                text: "󰁯"
                font.family: Style.font.family
                font.pixelSize: Style.font.display
                color: Commons.Color.foreground
              }
            }
            trailingControl: Component {
              PanelActionButton {
                visible: root.heroButtonShown
                hasCursor: root.cursorTarget === heroTarget
                iconText: root.shown === "everyday" ? "" : ""
                tooltipText: root.shown === "everyday" ? "Settings" : "Back"
                onClicked: root.heroPressed()
              }
            }
          }

          Prose {
            visible: root.shown === "everyday" && text !== ""
            width: parent.width
            dim: true
            text: Model.where(svc.header)
          }

          Prose {
            visible: svc.notice !== ""
            width: parent.width
            text: svc.notice
            color: svc.colour("yellow")
          }

          Prose { visible: root.shown === "loading"; width: parent.width; dim: true; text: "Looking…" }

          Start { id: startPage; visible: root.pageItem === startPage; width: parent.width
                  service: svc; panel: root; step: root.shown }
          Everyday { id: everydayPage; visible: root.pageItem === everydayPage; width: parent.width
                     service: svc; panel: root }
          SettingsPage { id: settingsPage; visible: root.pageItem === settingsPage; width: parent.width
                         service: svc; panel: root }
          MigratePage { id: migratePage; visible: root.pageItem === migratePage; width: parent.width
                        service: svc; panel: root; step: root.shown }
          Details { id: detailsPage; visible: root.pageItem === detailsPage; width: parent.width
                    service: svc; panel: root; step: root.shown }
        }
      }
    }
  }
}
