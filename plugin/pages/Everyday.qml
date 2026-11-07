import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// The everyday panel (BUILD 6.1 D, 7.1): the header, the lines
// that appear only when true, Back up now (or progress and Stop), and the
// restore points, a few then More.
Column {
  id: page
  property var service: null
  property var panel: null
  property bool showAll: false
  spacing: Style.space(10)

  readonly property var shownPoints: service ? (showAll ? service.points : service.points.slice(0, 5)) : []
  readonly property var targets: {
    var out = []
    for (var i = 0; i < lineRepeater.count; i++) out.push(lineRepeater.itemAt(i))
    out.push(service && service.running ? stopButton : backupButton)
    if (service && service.points.length > 5) out.push(moreButton)
    return out
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }

  Repeater {
    id: lineRepeater
    model: page.service ? page.service.lines : []
    StatusLine {
      required property var modelData
      item: modelData
      service: page.service
      hasCursorHere: page.cursorOn(this)
      onActivated: {
        if (modelData.action === "rescue") page.panel.go("settings")
        else if (modelData.kind === "failed" || modelData.kind === "unreachable") page.service.backupNow()
      }
      ActionButton {
        visible: modelData.kind === "waiting-network"
        text: "Back up now"
        onClicked: page.service.awayAnswer(true)
      }
      ActionButton {
        visible: modelData.kind === "waiting-network"
        text: "Wait until I'm on a known network"
        onClicked: page.service.awayAnswer(false)
      }
    }
  }

  ActionButton {
    id: backupButton
    visible: !(page.service && page.service.running)
    width: parent.width
    text: "Back up now"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.backupNow()
  }

  // While a backup runs: what it's doing, one step at a time, and Stop.
  Column {
    visible: !!(page.service && page.service.running)
    width: parent.width
    spacing: Style.space(6)
    Prose { width: parent.width; text: Model.doing(page.service ? page.service.running : null) }
    Rectangle {
      width: parent.width
      height: Style.space(4)
      radius: height / 2
      color: Qt.darker(Commons.Color.foreground, 3)
      Rectangle {
        id: sweep
        width: parent.width / 4
        height: parent.height
        radius: parent.radius
        color: page.service ? page.service.colour("blue") : Commons.Color.accent
        SequentialAnimation on x {
          running: !!(page.service && page.service.running)
          loops: Animation.Infinite
          NumberAnimation { from: 0; to: sweep.parent.width - sweep.width; duration: 1200 }
          NumberAnimation { from: sweep.parent.width - sweep.width; to: 0; duration: 1200 }
        }
      }
    }
    ActionButton {
      id: stopButton
      text: "Stop"
      hasCursorHere: page.cursorOn(this)
      onClicked: page.service.stop()
    }
    Prose { width: parent.width; dim: true; text: "Stopping is safe: the next backup picks up where this one stopped." }
  }

  PanelSeparator {}

  PanelSectionHeader { text: "Restore points" }

  Prose {
    visible: !page.service || page.service.points.length === 0
    width: parent.width
    dim: true
    text: "None yet: your first backup makes the first one."
  }

  Repeater {
    model: page.shownPoints
    Item {
      required property var modelData
      width: page.width
      implicitHeight: label.implicitHeight + Style.space(6)
      Prose {
        id: label
        anchors.left: parent.left
        anchors.right: tag.left
        text: Model.capital(Model.when(modelData.when))
        wrapMode: Text.NoWrap
        elide: Text.ElideRight
      }
      Prose {
        id: tag
        anchors.right: parent.right
        dim: true
        wrapMode: Text.NoWrap
        text: modelData.return_point ? "Return point" : (modelData.kept ? "kept" : "")
      }
    }
  }

  ActionButton {
    id: moreButton
    visible: !!(page.service && page.service.points.length > 5)
    text: page.showAll ? "Show fewer" : "More · " + (page.service ? page.service.points.length - 5 : 0)
    hasCursorHere: page.cursorOn(this)
    onClicked: page.showAll = !page.showAll
  }
}
