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
    if (browseBar.visible) out.push(doneButton)
    if (restoreBox.visible && restoreStop.visible) out.push(restoreStop)
    for (var i = 0; i < lineRepeater.count; i++) {
      var line = lineRepeater.itemAt(i)
      var own = line ? Array.prototype.filter.call(line.buttonItems, function(b) { return b.visible }) : []
      if (own.length) own.forEach(function(b) { out.push(b) })
      else out.push(line)
    }
    out.push(service && service.running ? stopButton : backupButton)
    for (var j = 0; j < pointRepeater.count; j++) out.push(pointRepeater.itemAt(j))
    if (service && service.points.length > 5) out.push(moreButton)
    return out
  }
  function whenOf(name) {
    var found = (service ? service.points : []).filter(function(p) { return p.name === name })
    return found.length ? Model.capital(Model.when(found[0].when)) : name
  }

  // --- Browsing (D37, as 1.x): what's open, and Done ------------------------------------
  CursorSurface {
    id: browseBar
    visible: !!(page.service && (page.service.browsing || page.service.opening !== ""))
    width: parent.width
    bordered: true
    implicitHeight: Math.max(browseText.implicitHeight, doneButton.implicitHeight) + Style.space(12)
    Prose {
      id: browseText
      anchors.left: parent.left
      anchors.right: doneButton.left
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      text: !page.service ? "" : page.service.browsing
            ? "Browsing " + page.whenOf(page.service.browsing.point) + " · read-only"
            : "Opening " + page.whenOf(page.service.opening) + "… this can take a few seconds."
    }
    ActionButton {
      id: doneButton
      visible: !!(page.service && page.service.browsing)
      anchors.right: parent.right
      anchors.rightMargin: Style.space(6)
      anchors.verticalCenter: parent.verticalCenter
      text: "Done"
      tooltipText: "Close it and lock your backup again"
      hasCursorHere: page.cursorOn(this)
      onClicked: page.service.browseDone()
    }
  }

  // --- Restore my files: how it's going (D37) --------------------------------------------
  Column {
    id: restoreBox
    readonly property var r: page.service ? page.service.restoring : null
    visible: !!(r && (r.running || r.error))
    width: parent.width
    spacing: Style.space(6)
    Prose {
      width: parent.width
      color: restoreBox.r && restoreBox.r.error ? page.service.colour("red") : Commons.Color.foreground
      text: !restoreBox.r ? "" : restoreBox.r.error
            ? restoreBox.r.error.what + " " + (restoreBox.r.error.todo || "")
            : "Bringing back your files · " + (restoreBox.r.percent || 0) + "%"
    }
    ActionButton {
      id: restoreStop
      visible: !!(restoreBox.r && restoreBox.r.running)
      width: parent.width
      text: "Stop (carry on later)"
      hasCursorHere: page.cursorOn(this)
      onClicked: page.service.restoreStop()
    }
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
        if (modelData.action === "rescue") page.service.rescueMake()
        else if (modelData.action === "pick") page.service.pickAgain()
        else if (modelData.kind === "failed" || modelData.kind === "unreachable") page.service.backupOrResume()
      }
      // In the line's own button row, under its text (they sat on top of it, garbled).
      buttons: [
        ActionButton {
          visible: modelData.kind === "waiting-network"
          text: "Back up now"
          hasCursorHere: page.cursorOn(this)
          onClicked: page.service.awayAnswer(true)
        },
        ActionButton {
          visible: modelData.kind === "waiting-network"
          text: "Wait until I'm on a known network"
          hasCursorHere: page.cursorOn(this)
          onClicked: page.service.awayAnswer(false)
        }
      ]
    }
  }

  ActionButton {
    id: backupButton
    visible: !(page.service && page.service.running)
    width: parent.width
    // D49: a stopped or cut-off backup carries on from where it got to.
    readonly property bool resumes: !!(page.service && page.service.status.unfinished)
    text: resumes ? "Resume backup" : "Back up now"
    hasCursorHere: page.cursorOn(this)
    onClicked: resumes ? page.service.resume() : page.service.backupNow()
  }

  // While a backup runs: what it's doing, one step at a time, and Stop.
  Column {
    visible: !!(page.service && page.service.running)
    width: parent.width
    spacing: Style.space(6)
    BackupProgress {
      width: parent.width
      running: page.service ? page.service.running : null
      barColour: page.service ? page.service.colour("blue") : Commons.Color.accent
    }
    ActionButton {
      id: stopButton
      readonly property bool stopping: !!(page.service && page.service.running && page.service.running.stopping)
      text: stopping ? "Stopping…" : "Stop"
      enabled: !stopping
      hasCursorHere: page.cursorOn(this)
      onClicked: if (!stopping) page.service.stop()
    }
    Prose { width: parent.width; dim: true; text: "Stopping is safe: Resume backup carries on from where it got to." }
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
    id: pointRepeater
    model: page.shownPoints
    PointRow {
      required property var modelData
      title: Model.capital(Model.when(modelData.when))
      tag: page.service && page.service.opening === modelData.name ? "Opening…"
           : page.service && page.service.browsing && page.service.browsing.point === modelData.name ? "Open"
           : modelData.kept_by ? "★ kept " + modelData.kept_by : (modelData.kept ? "★ kept" : "")
      hasCursorHere: page.cursorOn(this)
      onActivated: page.service.browse(modelData.name)
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
