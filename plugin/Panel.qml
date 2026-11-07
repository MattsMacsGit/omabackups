import QtQuick
import QtQuick.Controls
import Quickshell
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
  property bool cursorActive: false

  readonly property string defaultPage: !svc.loaded ? "loading"
                                       : !svc.installed ? "missing"
                                       : svc.flow === "not-set-up" ? "first"
                                       : svc.flow === "setting-up" ? "firstBackup"
                                       : "everyday"
  readonly property string shown: page !== "" ? page : defaultPage
  readonly property bool hasRedLine: svc.lines.some(function(l) { return l.colour === "red" })
  // The pages live in the panel's content, built later: reach them through it.
  readonly property var pages: panel.loadedContent ? panel.loadedContent.pages : ({})
  readonly property Item pageItem: ["missing", "first", "where", "server", "disk", "firstBackup"].indexOf(shown) >= 0
                                   ? pages.start || null : shown === "settings" ? pages.settings || null
                                   : ["kept", "changes", "yourBackup"].indexOf(shown) >= 0 ? pages.details || null
                                   : shown === "everyday" ? pages.everyday || null : null
  readonly property var targets: pageItem && pageItem.targets ? pageItem.targets.filter(function(t) { return t && t.visible }) : []
  readonly property Item cursorTarget: cursorActive && targets.length ? targets[Math.min(cursorIndex, targets.length - 1)] : null

  function go(name) { page = name; cursorIndex = 0 }
  function back() {
    if (["kept", "changes", "yourBackup"].indexOf(shown) >= 0) go("settings")
    else if (shown === "settings") go("")
    else if (shown === "server" || shown === "disk") go("where")
    else if (shown === "where") go("")
  }
  function titleFor(name) {
    return ({ settings: "Settings", kept: "Kept restore points", changes: "Your changes to Omarchy",
              yourBackup: "Your backup", where: "Set up backups", server: "Set up backups",
              disk: "Set up backups", firstBackup: "Set up backups" })[name] || "OmaBackups"
  }

  // A finished setup in the terminal moves the panel on by itself.
  Connections {
    target: svc
    function onFlowChanged() { if (["where", "server", "disk"].indexOf(root.page) >= 0) root.go("") }
  }
  onOpenedChanged: { svc.panelOpen = opened; if (opened) svc.refresh() }

  Service { id: svc }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰁯"
    foreground: root.hasRedLine ? svc.colour("red")
                : (svc.flow === "everyday" ? root.barForeground : Qt.darker(root.barForeground, 1.55))
    onPressed: function(code) { if (code === Qt.MiddleButton) svc.backupNow(); else root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(620))

    content: PanelKeyCatcher {
      id: keys
      readonly property var pages: ({ start: startPage, everyday: everydayPage,
                                      settings: settingsPage, details: detailsPage })
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      onMoveRequested: function(dx, dy) {
        if (dx < 0) { root.back(); return }
        if (!root.cursorActive) { root.cursorActive = true; return }
        root.cursorIndex = Math.max(0, Math.min(root.targets.length - 1, root.cursorIndex + dy))
      }
      onActivateRequested: if (root.cursorTarget && root.cursorTarget.activate) root.cursorTarget.activate()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "\b") root.back() }

      Flickable {
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

          PanelHero {
            width: parent.width
            title: root.titleFor(root.shown)
            meta: root.shown === "everyday" && svc.header && svc.header.last_finished
                  ? "Latest backup was " + Model.when(svc.header.last_finished) : ""
            detail: root.shown === "everyday" ? Model.where(svc.header) : ""
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
                visible: root.shown === "everyday" || root.page !== ""
                iconText: root.shown === "everyday" ? "" : ""
                tooltipText: root.shown === "everyday" ? "Settings" : "Back"
                onClicked: root.shown === "everyday" ? root.go("settings") : root.back()
              }
            }
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
          Details { id: detailsPage; visible: root.pageItem === detailsPage; width: parent.width
                    service: svc; panel: root; step: root.shown }
        }
      }
    }
  }
}
